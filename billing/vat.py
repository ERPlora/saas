"""The VAT of a sale: how it is qualified, at which rate, and how a charged amount splits.

No ORM here: the rule in force and the policy are read through ``billing.queries``.

The amount charged rules — the breakdown never alters it. Where the quota comes from depends on
how the price is announced:

* **Plans — NET price**. Stripe's ``Price`` is the base and OUR engine resolves the rate, sent
  with the sale (``default_tax_rates``). Stripe adds it on top and the invoice only collects it
  (``tax_included=False``) — **except a ZERO tax on a charge we qualified as subject**: reconciled as
  VAT-inclusive and reported, because a zero there is a misconfiguration (the rate
  mirrored in Stripe is not ours, or a VAT id Stripe accepted by its format and VIES did not confirm).
* **Modules — price with the VAT inside** (``tax_included=True``, the default): the quota is split out.

Four treatments, deduced from who the customer is and where the sale is located (``resolve_vat``):

* ``domestic`` — Spanish VAT is charged. General regime, S1.
* ``oss`` — One-Stop Shop: the customer's country VAT. Regime 17, N2.
* ``reverse_charge`` — intra-EU B2B: not subject by the location rules (art. 69.Uno.1º LIVA), the customer
  declares it. N2, WITHOUT rate nor quota.
* ``not_subject`` — outside the scope of VAT: third countries (the UK since Brexit) and the excluded
  territories of a member state (Canary Islands, Ceuta, Melilla). N2, without rate nor quota.

A fifth, ``exempt`` (subject but exempt, art. 20 LIVA), is never returned here: it depends on WHAT is sold,
not on the customer, and is stamped by hand on a line.

The rules, in this order:

1. **Intra-EU B2B** with a VAT number of another member state, VERIFIED in VIES, and ERPlora in the ROI
   (``FiscalPolicy.intra_eu_reverse_charge``) → reverse charge. Without both, Spanish VAT: invoicing at 0 %
   without them ends in an assessment against US. When in doubt, charge — that is recoverable.
2. **Territory without VAT** (a rule with ``is_subject=False``) → not subject.
3. **The OSS threshold**: while the cross-border B2C sales stay at or under €10,000 a year —and without the
   voluntary OSS registration— the ISSUER's VAT is charged, not the customer's country's.
4. **The rest** → the rate of the country that has the taxing right.

The RATE comes from ``TaxRule`` (editable in the admin, by country/region/category and validity).
``EU_VAT_RATES`` is a backstop for a member state whose rule was deleted, never for a region: there the
absence is «I don't know» and the sale is refused, because guessing the rate of an excluded territory is
charging Las Palmas 21 % it does not owe.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from decimal import Decimal

from billing.money import to_cents
from billing.payer import Payer
from billing.vat_breakdown import (
    DOMESTIC,
    NOT_SUBJECT,
    OSS,
    REVERSE_CHARGE,
    VatBreakdown,
    _breakdown,
    _effective_rate,
    _q,
    _Qualification,
    add_vat,
)
from billing.vat_countries import EU_VAT_RATES, spanish_region_for_postal_code

logger = logging.getLogger("billing.vat")

DEFAULT_ISSUER_COUNTRY = "ES"
GENERIC_CATEGORY = "service.generic"
#: What the plans of a business and the paid modules are, as ``TaxCategory`` keys: the SAME keys their
#: invoices use, so the rate that priced a sale and the one on its invoice come from one rule.
SAAS_SUBSCRIPTION_CATEGORY = "service.saas_subscription"
SOFTWARE_LICENSE_CATEGORY = "service.software_license"


def reverse_charge_applies(*, customer_country: str, verified: bool) -> bool:
    """Is a sale to a business of ``customer_country`` with a VIES-``verified`` VAT number reverse charged?

    The one rule, for the engine (``_qualify``) and for what the panel tells the buyer: ERPlora in the ROI
    (``FiscalPolicy.intra_eu_reverse_charge``), a member state that is not the issuer's, a country at all,
    and the proof. Without any of them the VAT is charged.
    """
    policy = _policy()
    country = (customer_country or "").strip().upper()
    return bool(
        verified
        and country in EU_VAT_RATES
        and country != _issuer_country(policy)
        and policy.intra_eu_reverse_charge
    )


def vat_rate_for(
    *,
    country: str,
    region: str = "",
    category_key: str = GENERIC_CATEGORY,
) -> Decimal | None:
    """The rate of a territory, or ``None`` if it charges no VAT (NOT SUBJECT, which is not a 0 % rate)."""
    return _lookup_rate(
        (country or "").strip().upper(),
        (region or "").strip().upper(),
        category_key,
    )[0]


def _policy():
    from billing import queries

    return queries.fiscal_policy()


def _issuer_country(policy) -> str:
    return (policy.issuer_country or DEFAULT_ISSUER_COUNTRY).strip().upper()


def _lookup_rate(
    country: str, region: str, category_key: str
) -> tuple[Decimal | None, bool]:
    """``(rate, do we know?)``. ``(None, True)`` is NOT SUBJECT (a rule says no VAT there); ``(None, False)``
    is «I don't know»: no rule and no backstop for that territory — nor when the question was about a
    REGION and the answer came from the country's rule (``queries.tax_rule`` falls from one to the other).

    Both collapse into «no quota» to INVOICE what was charged, but not to SELL: Las Palmas is sold without
    VAT because a rule says so, while a territory we know nothing about is not sold to.
    """
    from billing import queries

    rule = queries.tax_rule(
        country_code=country,
        region_code=region,
        category_key=category_key,
    )
    if rule is not None and region and rule.region_code.upper() != region:
        # The only regions here are the three territories OUTSIDE VAT: falling to the country's 21 % is
        # charging a Canarian what they do not owe. The rule is one click away in the admin; asked about a
        # region that is not in the table, this answers «I don't know» and the sale is refused.
        logger.error(
            "[VAT] No rule for the region %s/%s: the table fell back to the country's (%s), which in a "
            "territory outside VAT overcharges. Not guessing: add the rule %s/%s in the admin",
            country,
            region,
            rule,
            country,
            region,
            extra={
                "event": "fiscal.vat.region_rule_missing",
                "country": country,
                "region": region,
                "category_key": category_key,
                "fell_back_to": str(rule),
            },
        )
        return None, False
    if rule is not None:
        return (_q(rule.rate_pct) if rule.is_subject else None), True

    # No rule in the table: the backstop covers a member state's general rate only, never a region.
    if not region and country in EU_VAT_RATES:
        logger.warning(
            "[VAT] No rule for %s/%s; the backstop general rate applies",
            country,
            category_key,
        )
        return _q(EU_VAT_RATES[country]), True
    return None, False


def _customer_place(payer: Payer, issuer: str, *, selling: bool) -> tuple[str, str] | None:
    """The country and the region the customer is in.

    A Spanish place without a real postal code is «I don't know» when SELLING (``None``: the sale door asks
    for the address), and the mainland when invoicing what was already charged (the VAT is charged rather
    than a 0 % guessed).
    """
    country = (payer.country or "").strip().upper()
    if not country:
        # Stripe does not always send a country; a sale without one cannot go out without VAT.
        logger.info("[VAT] No customer country; the issuer's (%s) applies", issuer)
        country = issuer
    if country != "ES":
        return country, ""

    region = spanish_region_for_postal_code(payer.postal_code)
    if region is None:
        if selling:
            return None
        logger.warning(
            "[VAT] %r is not a Spanish postal code: the sale is taxed as on the mainland",
            payer.postal_code,
        )
        region = ""
    return country, region


def _taxed_in(
    country: str, region: str, category_key: str, *, customer_country: str
) -> _Qualification | None:
    """The sale taxed at the rate of a territory, not subject where there is no VAT; ``None`` without a rule."""
    rate, known = _lookup_rate(country, region, category_key)
    if not known:
        return None
    if rate is None:
        # Outside the scope of VAT: not subject, and no jurisdiction to declare (``tax_country`` empty).
        return _Qualification(NOT_SUBJECT, None, "", "", customer_country=customer_country)
    return _Qualification(DOMESTIC, rate, country, region, customer_country=customer_country)


def _taxed_at_destination(
    policy,
    rate: Decimal,
    issuer_rate: Decimal | None,
    *,
    charged_rate: Decimal | None,
    pending_base_cents: int,
) -> bool:
    """Is a sale to another member state taxed at its ``rate`` rather than at the issuer's?

    The charged rate is the evidence, both ways. When both rates are the same figure (NL, BE, CZ, LV, LT
    share the Spanish 21 %) the money proves nothing and the One-Stop Shop threshold decides.
    """
    from billing import queries

    destination_charged = charged_rate == rate
    issuer_charged = issuer_rate is not None and charged_rate == issuer_rate
    if destination_charged != issuer_charged:
        return destination_charged
    return queries.uses_destination_rate(policy, pending_cents=pending_base_cents)


def _qualify(
    payer: Payer,
    *,
    category_key: str,
    charged_rate: Decimal | None = None,
    pending_base_cents: int = 0,
    selling: bool = False,
) -> _Qualification | None:
    """The qualification of the sale, or ``None`` when its territory has no rule («I don't know»).

    ``charged_rate`` is the one fact that depends on the amount: the rate the gateway already charged, which
    rules over the policy in both directions. ``pending_base_cents`` is the base of the sale being priced: the
    OSS threshold is crossed BY a sale, and that sale already goes to destination. ``selling``: what
    ``_customer_place`` does not know is not guessed.
    """
    policy = _policy()
    issuer = _issuer_country(policy)
    place = _customer_place(payer, issuer, selling=selling)
    if place is None:
        return None
    country, region = place

    if payer.has_eu_vat_number and reverse_charge_applies(
        customer_country=country, verified=payer.tax_id_verified
    ):
        return _Qualification(
            REVERSE_CHARGE, None, country, region, customer_country=country
        )

    destination = _taxed_in(country, region, category_key, customer_country=country)
    if destination is None or destination.rate is None:
        return destination
    if country == issuer or country not in EU_VAT_RATES:
        # A third country with a rate of its own in the table (a registration there) is charged that rate,
        # never through the One-Stop Shop.
        return destination

    # Another member state: its rate through the One-Stop Shop, or the issuer's while it does not rule.
    issuer_region = (policy.issuer_region or "").strip().upper()
    origin = _taxed_in(issuer, issuer_region, category_key, customer_country=country)
    if _taxed_at_destination(
        policy,
        destination.rate,
        origin.rate if origin else None,
        charged_rate=charged_rate,
        pending_base_cents=pending_base_cents,
    ):
        return replace(destination, treatment=OSS)
    return origin


def quote_vat(
    net: Decimal, payer: Payer, *, category_key: str = GENERIC_CATEGORY
) -> VatBreakdown | None:
    """The tax to ADD to a net price, or ``None`` when it cannot be resolved — the answer that REFUSES the
    sale: without a rule the rate would be a guess and the price is net.

    Different from a NOT SUBJECT breakdown, which IS an answer (the Canaries pay the net, not a cent more).
    Same qualification as the invoice (``_qualify``), so what is charged and what is declared agree.
    """
    net = _q(Decimal(net))
    sale = _qualify(
        payer, category_key=category_key, pending_base_cents=to_cents(net), selling=True
    )
    if sale is None:
        # A WARNING: the place may be what a person typed in a form; the door that refuses a sale logs
        # its own ERROR (``billing.services.sale_tax.sale_quote``).
        logger.warning(
            "[VAT] No tax rule for %s/%s (postal code %r): the sale cannot be priced",
            (payer.country or "?").strip().upper(),
            category_key,
            payer.postal_code,
            extra={
                "event": "fiscal.vat.rate_not_resolvable",
                "customer_country": (payer.country or "").strip().upper(),
                "customer_postal_code": payer.postal_code,
                "category_key": category_key,
            },
        )
        return None

    if sale.rate is None:
        # Not subject or reverse charge: the net is charged, and that is all.
        return sale.breakdown(net, Decimal("0.00"), Decimal("0.00"))
    return sale.breakdown(net, add_vat(net, sale.rate) - net, sale.rate)


def resolve_vat(
    gross: Decimal,
    payer: Payer,
    *,
    category_key: str = GENERIC_CATEGORY,
    tax_cents: int = 0,
    tax_included: bool = True,
) -> VatBreakdown:
    """Split base and quota of a CHARGED amount and qualify the sale.

    Without ``payer.tax_id_verified`` (the VAT number proved in VIES,
    ``services.vat_clearance.clear_tax_id_for_stripe``) there is no reverse charge, however ``eu_vat`` the
    type. ``tax_cents``: the quota Stripe already computed; it rules the amounts, never the qualification,
    which is ours. ``tax_included``: the tax is INSIDE ``gross`` (modules) or Stripe ADDED it to a net price
    (plans).
    """
    gross = _q(Decimal(gross))
    sale = _qualify(
        payer,
        category_key=category_key,
        # The invoice describes the money really charged: the rate Stripe charged is the evidence.
        charged_rate=_effective_rate(gross, tax_cents) if tax_cents else None,
    )
    if sale is None:
        # A territory without a rule: to INVOICE what was charged it is indistinguishable from not subject
        # (both without quota) and the amount charged rules. To SELL it is not (``quote_vat``).
        sale = _Qualification(NOT_SUBJECT, None, "", "")
    return _breakdown(gross, sale, tax_cents=tax_cents, tax_included=tax_included)
