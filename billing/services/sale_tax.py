"""The tax of a sale: what refuses it before charging, and the rates Stripe charges on top of its net price.

Nothing here blocks a sale for VIES: without a proven verdict the customer pays the VAT, which is the
recoverable outcome. What refuses a sale (409) is not knowing where the payer is
(``billing.billing_location_required``), a payer outside the countries ERPlora sells to
(``billing.country_not_sold``), a consumer in the Canary Islands, Ceuta or Melilla (``billing.business_required``),
a consumer in the UK (``billing.uk_business_required``) or a territory without a rule
(``billing.tax_engine_missing``).
"""

import logging
from decimal import Decimal
from typing import Literal

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.errors import Conflict

from billing import queries, vat
from billing.money import to_cents
from billing.services.vat_clearance import clear_tax_id_for_stripe
from billing.stripe_tax_rates import TaxRateSpec, tax_rate_specs_for

logger = logging.getLogger("billing.services")

#: What is sold: each with its whole sentence, so the buyer's language gets a sentence, not a glued noun.
Sold = Literal["sale", "plan", "module"]
_CANNOT_BE_PRICED = {
    "sale": gettext_lazy(
        "We cannot work out the tax for this billing address, so this sale cannot be made. Contact support."
    ),
    "plan": gettext_lazy(
        "We cannot work out the tax for this billing address, so this plan cannot be sold to it. Contact support."
    ),
    "module": gettext_lazy(
        "We cannot work out the tax for this billing address, so this module cannot be sold to it. Contact support."
    ),
}


def reverse_charge_cleared(tax_id: str, country: str) -> bool:
    """Whether VIES proved this VAT id: asked here, never trusted from the profile, because a number that
    only looks right buys a sale tax free."""
    if not tax_id:
        return False
    return clear_tax_id_for_stripe(tax_id, customer_country=country).verified


def require_billing_location(
    hub, *, price: Decimal | None = None, what: Sold = "sale"
) -> None:
    """Refuse to sell before knowing WHERE the payer is: the 409 ``billing.billing_location_required``.

    The postal code is the only thing that tells the Canary Islands, Ceuta and Melilla (outside VAT) from
    the mainland, and only a real one («3500» is Benidorm without its 0, not Las Palmas).
    Charging first leaves two wrong outcomes. A free sale is never refused.
    """
    if price is not None and not to_cents(price):
        return None
    if queries.payer_of(hub).has_location:
        return None
    logger.error(
        "[FISCAL] Refusing a %s: the payer's country and postal code are not on file, or the postal code is "
        "not one of its country, so the sale cannot be priced before charging (hub=%s)",
        what,
        getattr(hub, "id", None),
    )
    raise Conflict(
        _(
            "We need the billing country and postal code before the payment, because they decide the tax on this sale."
        ),
        code="billing.billing_location_required",
    )


def require_sold_to(hub, payer: queries.Payer, what: Sold = "sale") -> None:
    """Refuse a new sale to a payer ERPlora does not sell to: another country (409 ``billing.country_not_sold``),
    or a consumer in the Canary Islands, Ceuta or Melilla (409 ``billing.business_required``)."""
    if not vat.sells_to(payer.country):
        logger.info(
            "[FISCAL] Refusing a %s: ERPlora does not sell to payers in %s (hub=%s)",
            what,
            payer.country,
            getattr(hub, "id", None),
        )
        raise Conflict(
            _("For now ERPlora only sells to payers billed in Spain: change the billing details."),
            code="billing.country_not_sold",
        )
    region = vat.spanish_region_for_postal_code(payer.postal_code) if payer.country == "ES" else ""
    if region in vat.BUSINESS_ONLY_REGIONS and not payer.tax_id:
        logger.info(
            "[FISCAL] Refusing a %s: the payer is a consumer in %s (hub=%s)",
            what,
            region,
            getattr(hub, "id", None),
        )
        raise Conflict(
            _(
                "In the Canary Islands, Ceuta and Melilla we only sell to businesses and professionals: add the tax ID "
                "of the payer."
            ),
            code="billing.business_required",
        )
    return None


def sale_quote(
    hub, *, category_key: str, price: Decimal | None, what: Sold = "sale", renewing: bool = False
) -> vat.VatBreakdown:
    """The tax of selling ``price`` (net) of ``category_key`` to the payer of ``hub``; ``None`` = there IS
    something to charge, but the amount is not this question's business (the rate never depends on it).

    Refused (409) without a valid billing location, to a payer ERPlora does not sell to (``require_sold_to``;
    ``renewing`` = what is already paid, which keeps renewing), to a consumer in the UK (the terms sell to UK
    businesses only: a UK consumer owes UK VAT that only a supplier registered with HMRC may charge),
    and when no rule resolves the territory (the rate would be a guess and the price is net:
    refusing is loud and reversible; a sale charged wrong is neither).
    """
    require_billing_location(hub, price=price, what=what)
    payer = queries.payer_of(hub)
    if not renewing:
        require_sold_to(hub, payer, what)
    if payer.country == "GB" and not payer.tax_id:
        logger.info(
            "[FISCAL] Refusing a %s: the payer is a consumer in the UK (hub=%s)",
            what,
            getattr(hub, "id", None),
        )
        raise Conflict(
            _(
                "We only sell to businesses in the United Kingdom: add the UK VAT number of the payer."
            ),
            code="billing.uk_business_required",
        )
    quote = vat.quote_vat(
        price if price is not None else Decimal("0"),
        customer_country=payer.country,
        customer_postal_code=payer.postal_code,
        customer_tax_id=payer.tax_id,
        customer_tax_id_type=payer.tax_id_type,
        customer_tax_id_verified=reverse_charge_cleared(payer.tax_id, payer.country),
        category_key=category_key,
    )
    if quote is None:
        logger.error(
            "[FISCAL] Refusing a %s: no tax rule resolves for %s %s, so the rate would be a guess and the price "
            "is net (hub=%s)",
            what,
            payer.country or "?",
            payer.postal_code or "?",
            getattr(hub, "id", None),
        )
        raise Conflict(str(_CANNOT_BE_PRICED[what]), code="billing.tax_engine_missing")
    return quote


def sale_tax_rates(
    hub, *, category_key: str, price: Decimal | None = None, what: Sold = "sale"
) -> list[TaxRateSpec]:
    """The rates Stripe must charge on top of this sale's net price (mirrored into Stripe ``TaxRate``
    ids), for every door that sells: the plan and the module price the same buyer the same way.

    An EMPTY list is an answer, not a failure: the Canaries are outside VAT and the reverse charge is the
    customer's. ``price`` €0.00 is never refused (21 % of nothing is nothing, and the Free plan is the way
    in); ``None`` = an amount that is not this function's business: the rate never depends on it.
    """
    if price is not None and not to_cents(price):
        return []
    quote = sale_quote(
        hub,
        category_key=category_key,
        price=price,
        what=what,
    )
    return tax_rate_specs_for(quote)
