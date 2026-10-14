"""Reads of billing: the rule in force, the policy, ERPlora's identity, the VIES log, the payer of a
business, and the operation ``billing.tax.preview``.

Only this module and ``services.py`` touch the ORM: the VAT engine (``billing.vat``) reads the table and the
policy through the functions below. Nothing here asks VIES nor writes: a query runs READ ONLY.
"""

import logging
from dataclasses import dataclass
from datetime import date

from django.db import DatabaseError, transaction
from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from billing import vat, vies
from billing.models import (
    GENERIC_CATEGORY,
    CompanyConfig,
    FiscalPolicy,
    TaxRule,
    VatCheck,
)
from billing.money import from_cents, to_cents
from billing.schemas import TaxPreviewIn, TaxPreviewOut

logger = logging.getLogger("billing.queries")

#: The category of what a preview prices.
CATEGORY_KEYS = {
    "plan": vat.SAAS_SUBSCRIPTION_CATEGORY,
    "module": vat.SOFTWARE_LICENSE_CATEGORY,
}


# --- The rate table and the policy -----------------------------------------------------------------


def tax_rule(
    *,
    country_code: str,
    category_key: str = GENERIC_CATEGORY,
    region_code: str = "",
    on_date: date | None = None,
) -> TaxRule | None:
    """The rule in force for a territory and what is sold, or ``None`` if the territory is not in the table.

    Precedence: region+category > region+generic > country+category > country+generic. The most specific
    wins, and the generic category is the net that saves replicating 27 countries per new service. Among
    rules in force at once, the one that started later.
    """
    on_date = on_date or timezone.localdate()
    in_force = (
        TaxRule.objects.filter(
            country_code=(country_code or "").strip().upper(),
            is_active=True,
            valid_from__lte=on_date,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on_date))
        .order_by("-valid_from", "-id")
    )
    region = (region_code or "").strip().upper()
    regions = [region, ""] if region else [""]
    categories = (
        [category_key, GENERIC_CATEGORY]
        if category_key != GENERIC_CATEGORY
        else [GENERIC_CATEGORY]
    )
    for candidate_region in regions:
        for key in categories:
            rule = in_force.filter(
                region_code=candidate_region, category_id=key
            ).first()
            if rule is not None:
                return rule
    return None


def fiscal_policy() -> FiscalPolicy:
    """The policy on file, or the defaults (Spain, in the ROI, no OSS) without writing them: a READ ONLY
    query reads it too. The migration seeds the row; the admin edits it."""
    return FiscalPolicy.objects.first() or FiscalPolicy()


def cross_border_b2c_cents(policy: FiscalPolicy, year: int) -> int:
    """The tax base of the year's intra-EU B2C distance sales, in integer cents (the OSS threshold).

    The sales to consumers of OTHER member states (no VIES-verified VAT number) invoiced outside this
    SaaS —the old one—, carried by hand in ``FiscalPolicy`` for ``oss_carried_year`` and the year before,
    plus ERPlora's paid invoices here, which are ``billing.Invoice`` (lot L3-C): until that model exists
    the new SaaS has issued none (``test_the_threshold_counts_the_invoices_the_day_they_exist`` fails the
    day it lands). Lot L2-B must not sell through this SaaS before the sum is real, old SaaS included.
    """
    carried_year = policy.oss_carried_year
    if carried_year is None:
        return 0
    if year == carried_year:
        return int(policy.oss_carried_current_cents)
    if year == carried_year - 1:
        return int(policy.oss_carried_previous_cents)
    return 0


def oss_total_is_known(policy: FiscalPolicy, year: int) -> bool:
    """Whether the year's cross-border B2C total is a fact or an assumption: while nothing was carried
    for ``year`` (and there are no invoices here yet) a 0 is not a fact, and the admin says «unknown»."""
    return policy.oss_carried_year == year


def destination_rate_applies(
    policy: FiscalPolicy, *, year: int | None = None, pending_cents: int = 0
) -> bool:
    """Does the customer's country rate (OSS) apply instead of the issuer's? A failed query raises.

    Destination applies with the voluntary OSS registration (it binds two calendar years, art. 59c(3)
    Directive 2006/112/EC); when the previous year closed above the threshold (the whole year is
    destination, art. 73 LIVA); or when this year's sales PLUS the sale being priced (its base,
    ``pending_cents``) exceed it — art. 59c(2): the very sale that crosses goes to destination.
    """
    if policy.oss_registered:
        return True
    year = year or timezone.localdate().year
    threshold_cents = to_cents(policy.oss_threshold)
    if cross_border_b2c_cents(policy, year - 1) > threshold_cents:
        return True
    return cross_border_b2c_cents(policy, year) + int(pending_cents) > threshold_cents


def uses_destination_rate(
    policy: FiscalPolicy, *, year: int | None = None, pending_cents: int = 0
) -> bool:
    """``destination_rate_applies`` for PRICING: a database error prices at origin and is logged as an
    ERROR, so a sale is not refused because the year's total could not be summed. Whoever ACTS on «the
    year is back to origin» asks ``destination_rate_applies``, which raises."""
    try:
        # A savepoint: a failed sum must not abort the transaction of the operation that prices.
        with transaction.atomic():
            return destination_rate_applies(
                policy, year=year, pending_cents=pending_cents
            )
    except DatabaseError:
        logger.exception(
            "[FISCAL] Could not compute the OSS threshold total: the issuer's rate applies"
        )
        return False


# --- ERPlora's identity and the VIES log -----------------------------------------------------------


def vies_requester() -> tuple[str, str] | None:
    """ERPlora's own VAT number split into member state and number: who asks VIES. ``None`` without it."""
    company = CompanyConfig.objects.first()
    if company is None:
        return None
    country = (company.country or "").strip().upper()
    tax_id = vies.normalise(company.tax_id)
    if (
        len(country) == 2
        and tax_id.startswith(vies.vies_prefix(country))
        and len(tax_id) > 2
    ):
        tax_id = tax_id[2:]
    if not tax_id or len(country) != 2:
        return None
    return vies.vies_prefix(country), tax_id


def latest_vat_check(vat_number: str) -> VatCheck | None:
    """The verdict in force for a number: its most recent query."""
    return (
        VatCheck.objects.filter(vat_number=vies.normalise(vat_number))
        .order_by("-requested_at")
        .first()
    )


# --- The payer of a business -----------------------------------------------------------------------


@dataclass(frozen=True)
class Payer:
    """Where the payer of a business is and its VAT number, as every door that sells reads them."""

    country: str
    postal_code: str
    #: Empty when there is none, or when its country has no Stripe tax id type (a wrong type makes Stripe
    #: reject the whole number, so an unknown country's id is not guessed).
    tax_id: str
    tax_id_type: str

    @property
    def has_location(self) -> bool:
        """Both halves on file, the postal code of its country's shape: a country alone prices Madrid and
        Las Palmas the same (saas#1972), and «3500» is not Las Palmas (``vat.postal_code_is_valid``)."""
        return vat.postal_code_is_valid(self.country, self.postal_code)


def payer_of(hub) -> Payer:
    """The payer of ``hub`` (``hubs.BillingProfile``, the fact typed in OUR form), read on every sale."""
    profile = getattr(hub, "billing_profile", None) if hub is not None else None
    if profile is None:
        return Payer("", "", "", "")
    country = (profile.billing_country or "").strip().upper()
    postal_code = (profile.billing_postal_code or "").strip().upper()
    tax_id = vies.normalise(profile.tax_id)
    tax_id_type = vat.tax_id_type_for(country) if tax_id else ""
    if tax_id and not tax_id_type:
        logger.info(
            "[BILLING] The payer of hub %s has a tax id but no Stripe type for country %r: it stays off the sale",
            getattr(hub, "slug", "?"),
            country,
        )
        tax_id = ""
    return Payer(country, postal_code, tax_id, tax_id_type)


# --- Operations ------------------------------------------------------------------------------------


def _vat_status_on_file(vat_number: str, country: str) -> str:
    """What the log says of a number, without asking VIES (a query never does)."""
    if not vat_number:
        return "absent"
    if vies.is_uk_vat_number(vat_number) or country in vies.UK_PREFIXES:
        return "outside_vies"
    if vies.is_domestic_vat_number(
        vat_number,
        issuer_country=fiscal_policy().issuer_country,
        customer_country=country,
    ):
        return "national"
    check = latest_vat_check(vat_number)
    if check is None or not check.is_current:
        # An expired verdict proves nothing any more: the next sale asks VIES again.
        return "unchecked"
    if check.grants_reverse_charge:
        return "verified"
    return "invalid" if check.status == VatCheck.INVALID else "unavailable"


@operation(
    "billing.tax.preview",
    kind="query",
    permission="billing.view",
    input=TaxPreviewIn,
    output=TaxPreviewOut,
)
def tax_preview(ctx: OperationContext, params: TaxPreviewIn) -> dict:
    """The tax a sale to this payer carries, with the same engine the checkout charges with: «€29.99 + 21 %
    VAT — €36.29» or «reverse charge: no VAT». The VIES verdict is the one on file: the form asks
    ``billing.vat_check.run`` first."""
    vat_number = vies.with_country_prefix(
        params.vat_number, params.country, issuer_country=fiscal_policy().issuer_country
    )
    vat_status = _vat_status_on_file(vat_number, params.country)
    quote = vat.quote_vat(
        params.net,
        customer_country=params.country,
        customer_postal_code=params.postal_code,
        customer_tax_id=vat_number,
        customer_tax_id_type=vat.tax_id_type_for(params.country) if vat_number else "",
        customer_tax_id_verified=vat_status == "verified",
        category_key=CATEGORY_KEYS[params.category],
    )
    answer = {
        "country": params.country,
        "resolvable": quote is not None,
        "treatment": None,
        "tax_country": "",
        "rate": None,
        "net": from_cents(to_cents(params.net)),
        "tax": None,
        "total": None,
        "b2b": bool(vat_number),
        "vat_status": vat_status,
        "reverse_charge": False,
    }
    if quote is not None:
        answer.update(
            treatment=quote.treatment,
            tax_country=quote.tax_country,
            rate=quote.rate,
            tax=quote.tax,
            total=quote.base + quote.tax,
            reverse_charge=quote.is_reverse_charge,
        )
    return answer
