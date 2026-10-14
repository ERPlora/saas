"""The VAT of a sale: how it is qualified, at which rate, and how a charged amount splits.

Ported from ERPlora/saas ``apps/dashboard/fiscal/vat.py`` (origin/develop). No ORM here: the rule in force
and the policy are read through ``billing.queries`` (only ``services.py`` and ``queries.py`` touch the ORM).

The amount charged rules — the breakdown never alters it (saas#1051). Where the quota comes from depends on
how the price is announced:

* **Plans — NET price** (saas#1098). Stripe's ``Price`` is the base and OUR engine resolves the rate, sent
  with the sale (``default_tax_rates``, lot L2-B). Stripe adds it on top and the invoice only collects it
  (``tax_included=False``) — **except a ZERO on a sale we qualified as subject**: that is reconciled as
  VAT-inclusive and reported (saas#1478, saas#1479), because a zero there is a misconfiguration (the rate
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
charging Las Palmas 21 % it does not owe (ADR-0190).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from billing.money import to_cents

logger = logging.getLogger("billing.vat")

#: General VAT rate of each EU-27 member state — the backstop, not the source (the source is ``TaxRule``).
EU_VAT_RATES: dict[str, Decimal] = {
    "AT": Decimal("20"),
    "BE": Decimal("21"),
    "BG": Decimal("20"),
    "CY": Decimal("19"),
    "CZ": Decimal("21"),
    "DE": Decimal("19"),
    "DK": Decimal("25"),
    "EE": Decimal("24"),
    "ES": Decimal("21"),
    "FI": Decimal("25.5"),
    "FR": Decimal("20"),
    "GR": Decimal("24"),
    "HR": Decimal("25"),
    "HU": Decimal("27"),
    "IE": Decimal("23"),
    "IT": Decimal("22"),
    "LT": Decimal("21"),
    "LU": Decimal("17"),
    "LV": Decimal("21"),
    "MT": Decimal("18"),
    "NL": Decimal("21"),
    "PL": Decimal("23"),
    "PT": Decimal("23"),
    "RO": Decimal("21"),
    "SE": Decimal("25"),
    "SI": Decimal("22"),
    "SK": Decimal("23"),
}

DEFAULT_ISSUER_COUNTRY = "ES"
GENERIC_CATEGORY = "service.generic"
#: What the plans of a business and the paid modules are, as ``TaxCategory`` keys: the SAME keys their
#: invoices use, so the rate that priced a sale and the one on its invoice come from one rule.
SAAS_SUBSCRIPTION_CATEGORY = "service.saas_subscription"
SOFTWARE_LICENSE_CATEGORY = "service.software_license"

#: The countries ERPlora invoices: the EU-27 and the UK, Spain first (where the customers are).
BILLING_COUNTRIES: tuple[str, ...] = (
    "ES",
    *sorted((set(EU_VAT_RATES) | {"GB"}) - {"ES"}),
)

#: Stripe's tax id type per billing country. Anything not listed is skipped rather than guessed: a wrong
#: type makes Stripe reject the whole tax id. Derived from the VAT table so no member state is left out
#: (a hand list of nine dropped a verified Polish VAT id, saas#1621).
TAX_ID_TYPES: dict[str, str] = {**dict.fromkeys(EU_VAT_RATES, "eu_vat"), "GB": "gb_vat"}

DOMESTIC = "domestic"
OSS = "oss"
REVERSE_CHARGE = "reverse_charge"
NOT_SUBJECT = "not_subject"
#: Subject but exempt (art. 20 LIVA): never returned by ``resolve_vat``; stamped by hand on a line.
EXEMPT = "exempt"

#: The treatments that charge VAT, so carry a rate and a quota. The rest declare the whole amount as base.
TREATMENTS_WITH_RATE = frozenset({DOMESTIC, OSS})

#: The first two digits of a Spanish postal code are the province, and with it the territories outside VAT.
_SPANISH_REGION_BY_POSTAL_PREFIX = {"35": "IC", "38": "IC", "51": "CE", "52": "ML"}
_SPANISH_POSTAL_CODE = re.compile(r"^\d{5}$")

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class VatBreakdown:
    """Base, quota, rate and qualification. ``base + tax`` is always the gross."""

    base: Decimal
    tax: Decimal
    rate: Decimal
    tax_country: str
    treatment: str = DOMESTIC
    tax_region: str = ""
    #: The quota was NOT charged by the gateway: it was taken out of the amount charged as VAT-inclusive
    #: (saas#1479). A FACT of the breakdown, so the invoice can say why its base is not the plan's price.
    vat_included_reconciled: bool = False

    @property
    def is_reverse_charge(self) -> bool:
        return self.treatment == REVERSE_CHARGE

    @property
    def is_subject(self) -> bool:
        return self.treatment in TREATMENTS_WITH_RATE


def tax_id_type_for(country: str) -> str:
    """Stripe's tax id type for a billing country, or ``""`` when there is none."""
    return TAX_ID_TYPES.get((country or "").strip().upper(), "")


def _q(value: Decimal) -> Decimal:
    # ADR-0123 §4: explicit HALF_UP; a bare quantize() inherits HALF_EVEN from the context.
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def spanish_region_for_postal_code(postal_code: str) -> str | None:
    """Spanish fiscal region of a postal code: ``""`` = the mainland and the Balearic Islands, ``None`` =
    not a Spanish postal code (five digits, spaces aside). Only a real code names its province: «3500» is
    Benidorm typed without its leading 0, not Las Palmas, and guessing it would sell it at 0 %."""
    code = (postal_code or "").replace(" ", "")
    if not _SPANISH_POSTAL_CODE.match(code):
        return None
    return _SPANISH_REGION_BY_POSTAL_PREFIX.get(code[:2], "")


def postal_code_is_valid(country: str, postal_code: str) -> bool:
    """A billing location the sale can be priced with: a country and a postal code of its shape (Spain:
    five digits; elsewhere, not blank — the tax does not depend on it)."""
    country = (country or "").strip().upper()
    if len(country) != 2:
        return False
    if country == "ES":
        return spanish_region_for_postal_code(postal_code) is not None
    return bool((postal_code or "").strip())


def reverse_charge_applies(
    *, customer_country: str, verified: bool, issuer_country: str = ""
) -> bool:
    """Is a sale to a business of ``customer_country`` with a VIES-``verified`` VAT number reverse charged?

    The one rule, for the engine (``_qualify``) and for what the panel tells the buyer: ERPlora in the ROI
    (``FiscalPolicy.intra_eu_reverse_charge``), a member state that is not the issuer's, a country at all,
    and the proof. Without any of them the VAT is charged.
    """
    policy = _policy()
    country = (customer_country or "").strip().upper()
    issuer = (
        (issuer_country or policy.issuer_country or DEFAULT_ISSUER_COUNTRY)
        .strip()
        .upper()
    )
    return bool(
        verified
        and country in EU_VAT_RATES
        and country != issuer
        and policy.intra_eu_reverse_charge
    )


def split_gross(gross: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Base and quota of an amount with the VAT inside; ``base + quota == gross``.

    The quota is derived BY SUBTRACTION, so the sum rebuilds the gross exactly even when rounding the base
    moved a cent: matching what was charged matters more than matching the rate.
    """
    gross = _q(Decimal(gross))
    rate = Decimal(rate or 0)
    if rate <= 0:
        return gross, Decimal("0.00")
    base = _q(gross / (Decimal("1") + rate / Decimal("100")))
    return base, gross - base


def add_vat(net: Decimal, rate: Decimal) -> Decimal:
    """The total to charge, adding ``rate`` to a NET amount: the one arithmetic of «€29.99 + VAT»."""
    net = _q(Decimal(net))
    rate = Decimal(rate or 0)
    if rate <= 0:
        return net
    return _q(net * (Decimal("1") + rate / Decimal("100")))


def vat_rate_for(
    *,
    country: str,
    region: str = "",
    category_key: str = GENERIC_CATEGORY,
    on_date=None,
) -> Decimal | None:
    """The rate of a territory, or ``None`` if it charges no VAT (NOT SUBJECT, which is not a 0 % rate)."""
    return _lookup_rate(
        (country or "").strip().upper(),
        (region or "").strip().upper(),
        category_key,
        on_date,
    )[0]


def _effective_rate(gross: Decimal, tax_cents: int) -> Decimal:
    """The rate an amount and its quota imply (``0.00`` without a base)."""
    tax = _q(Decimal(tax_cents) / Decimal("100"))
    base = gross - tax
    return _q(tax / base * Decimal("100")) if base else Decimal("0.00")


def _policy():
    from billing import queries

    return queries.fiscal_policy()


def _lookup_rate(
    country: str, region: str, category_key: str, on_date
) -> tuple[Decimal | None, bool]:
    """``(rate, do we know?)``. ``(None, True)`` is NOT SUBJECT (a rule says no VAT there); ``(None, False)``
    is «I don't know»: no rule and no backstop for that territory — nor when the question was about a
    REGION and the answer came from the country's rule (``queries.tax_rule`` falls from one to the other).

    Both collapse into «no quota» to INVOICE what was charged, but not to SELL: Las Palmas is sold without
    VAT because a rule says so, while a territory we know nothing about is not sold to (saas#1968).
    """
    from billing import queries

    rule = queries.tax_rule(
        country_code=country,
        region_code=region,
        category_key=category_key,
        on_date=on_date,
    )
    if rule is not None and region and rule.region_code.upper() != region:
        # The only regions here are the three territories OUTSIDE VAT: falling to the country's 21 % is
        # charging a Canarian what they do not owe. The rule is one click away in the admin; asked about a
        # region that is not in the table, this answers «I don't know» and the sale is refused (ADR-0190).
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


@dataclass(frozen=True)
class _Qualification:
    """How a sale is taxed, decided WITHOUT looking at the amount: one place for ``resolve_vat`` (what was
    charged) and ``quote_vat`` (what will be charged), so the two cannot qualify the same sale apart."""

    treatment: str
    rate: Decimal | None
    tax_country: str
    tax_region: str
    customer_country: str = ""


def _qualify(
    *,
    customer_country: str = "",
    customer_tax_id: str = "",
    customer_tax_id_type: str = "",
    customer_tax_id_verified: bool = False,
    customer_postal_code: str = "",
    category_key: str = GENERIC_CATEGORY,
    issuer_country: str = "",
    on_date=None,
    rate_charged: Callable[[Decimal], bool] | None = None,
    pending_base_cents: int = 0,
    selling: bool = False,
) -> _Qualification | None:
    """The qualification of the sale, or ``None`` when its territory has no rule («I don't know»).

    ``rate_charged`` is the one fact that depends on the amount: whether the gateway already charged a
    rate; asked for the customer's country's and the issuer's, the charged rate rules over the policy in
    both directions (saas#2292). ``pending_base_cents`` is the base of the sale being priced: the OSS
    threshold is crossed BY a sale, and that sale already goes to destination (saas#1969).

    ``selling``: a Spanish place without a real postal code is «I don't know» when SELLING (``None``: the
    sale door asks for the address), and the mainland when invoicing what was already charged (the VAT
    is charged rather than a 0 % guessed).
    """
    from billing import queries

    country = (customer_country or "").strip().upper()
    policy = _policy()
    issuer = (
        (issuer_country or policy.issuer_country or DEFAULT_ISSUER_COUNTRY)
        .strip()
        .upper()
    )
    issuer_region = (policy.issuer_region or "").strip().upper()

    if not country:
        # Stripe does not always send a country; a sale without one cannot go out without VAT.
        logger.info("[VAT] No customer country; the issuer's (%s) applies", issuer)
        country = issuer

    region = (
        spanish_region_for_postal_code(customer_postal_code) if country == "ES" else ""
    )
    if region is None:
        if selling:
            return None
        logger.warning(
            "[VAT] %r is not a Spanish postal code: the sale is taxed as on the mainland",
            customer_postal_code,
        )
        region = ""

    is_intra_eu_b2b = (
        customer_tax_id_type == "eu_vat"
        and bool(customer_tax_id)
        and reverse_charge_applies(
            customer_country=country,
            verified=customer_tax_id_verified,
            issuer_country=issuer,
        )
    )
    if is_intra_eu_b2b:
        return _Qualification(
            REVERSE_CHARGE, None, country, region, customer_country=country
        )

    rate, known = _lookup_rate(country, region, category_key, on_date)
    if not known:
        return None
    if rate is None:
        # Outside the scope of VAT: not subject, and no jurisdiction to declare (``tax_country`` empty).
        return _Qualification(NOT_SUBJECT, None, "", "", customer_country=country)

    if country != issuer and country in EU_VAT_RATES:
        # Another member state: the One-Stop Shop threshold decides whose rate. A third country with a
        # rate of its own in the table (a registration there) is charged that rate, never through the OSS.
        issuer_rate, issuer_known = _lookup_rate(
            issuer, issuer_region, category_key, on_date
        )
        # The charged rate is the evidence, both ways (saas#2292). When both rates are the same figure (NL,
        # BE, CZ, LV, LT share the Spanish 21 %) the money proves nothing and the policy decides.
        destination_rate_charged = rate_charged is not None and rate_charged(rate)
        issuer_rate_charged = (
            issuer_rate is not None
            and rate_charged is not None
            and rate_charged(issuer_rate)
        )
        if destination_rate_charged and not issuer_rate_charged:
            return _Qualification(OSS, rate, country, region, customer_country=country)
        only_issuer_rate_charged = issuer_rate_charged and not destination_rate_charged
        year = on_date.year if on_date else None
        if not only_issuer_rate_charged and queries.uses_destination_rate(
            policy, year=year, pending_cents=pending_base_cents
        ):
            return _Qualification(OSS, rate, country, region, customer_country=country)
        # Under the threshold the taxing right is the issuer's: its rate and its country.
        if not issuer_known:
            return None
        if issuer_rate is None:
            return _Qualification(NOT_SUBJECT, None, "", "", customer_country=country)
        return _Qualification(
            DOMESTIC, issuer_rate, issuer, issuer_region, customer_country=country
        )

    return _Qualification(DOMESTIC, rate, country, region, customer_country=country)


def quote_vat(
    net: Decimal,
    *,
    customer_country: str = "",
    customer_tax_id: str = "",
    customer_tax_id_type: str = "",
    customer_tax_id_verified: bool = False,
    customer_postal_code: str = "",
    category_key: str = GENERIC_CATEGORY,
    issuer_country: str = "",
    on_date=None,
) -> VatBreakdown | None:
    """The tax to ADD to a net price, or ``None`` when it cannot be resolved — the answer that REFUSES the
    sale (saas#1968): without a rule the rate would be a guess and the price is net.

    Different from a NOT SUBJECT breakdown, which IS an answer (the Canaries pay the net, not a cent more).
    Same qualification as the invoice (``_qualify``), so what is charged and what is declared agree.
    """
    net = _q(Decimal(net))
    qualification = _qualify(
        customer_country=customer_country,
        customer_tax_id=customer_tax_id,
        customer_tax_id_type=customer_tax_id_type,
        customer_tax_id_verified=customer_tax_id_verified,
        customer_postal_code=customer_postal_code,
        category_key=category_key,
        issuer_country=issuer_country,
        on_date=on_date,
        pending_base_cents=to_cents(net),
        selling=True,
    )
    if qualification is None:
        # A WARNING: the place may be what a person typed in a form; the door that refuses a sale logs
        # its own ERROR (``billing.services.sale_quote``).
        logger.warning(
            "[VAT] No tax rule for %s/%s (postal code %r): the sale cannot be priced",
            (customer_country or "?").strip().upper(),
            category_key,
            customer_postal_code,
            extra={
                "event": "fiscal.vat.rate_not_resolvable",
                "customer_country": (customer_country or "").strip().upper(),
                "customer_postal_code": customer_postal_code,
                "category_key": category_key,
            },
        )
        return None

    if qualification.rate is None:
        # Not subject or reverse charge: the net is charged, and that is all.
        return VatBreakdown(
            base=net,
            tax=Decimal("0.00"),
            rate=Decimal("0.00"),
            tax_country=qualification.tax_country,
            treatment=qualification.treatment,
            tax_region=qualification.tax_region,
        )

    total = add_vat(net, qualification.rate)
    return VatBreakdown(
        base=net,
        tax=total - net,
        rate=qualification.rate,
        tax_country=qualification.tax_country,
        treatment=qualification.treatment,
        tax_region=qualification.tax_region,
    )


def resolve_vat(
    gross: Decimal,
    *,
    customer_country: str = "",
    customer_tax_id: str = "",
    customer_tax_id_type: str = "",
    customer_tax_id_verified: bool = False,
    customer_postal_code: str = "",
    category_key: str = GENERIC_CATEGORY,
    tax_cents: int = 0,
    tax_included: bool = True,
    issuer_country: str = "",
    on_date=None,
) -> VatBreakdown:
    """Split base and quota of a CHARGED amount and qualify the sale.

    ``customer_tax_id_verified``: the VAT number is proved in VIES (``services.clear_tax_id_for_stripe``);
    without it there is no reverse charge, however ``eu_vat`` the type. ``tax_cents``: the quota Stripe
    already computed; it rules the amounts, never the qualification, which is ours. ``tax_included``: the
    tax is INSIDE ``gross`` (modules) or Stripe ADDED it to a net price (plans). ``on_date``: the date of
    the sale, to pick the rule in force (today by default).
    """
    gross = _q(Decimal(gross))
    qualification = _qualify(
        customer_country=customer_country,
        customer_tax_id=customer_tax_id,
        customer_tax_id_type=customer_tax_id_type,
        customer_tax_id_verified=customer_tax_id_verified,
        customer_postal_code=customer_postal_code,
        category_key=category_key,
        issuer_country=issuer_country,
        on_date=on_date,
        # The invoice describes the money really charged: the rate Stripe charged is the evidence (saas#2292).
        rate_charged=lambda rate: (
            bool(tax_cents) and _effective_rate(gross, tax_cents) == rate
        ),
    )

    if qualification is None:
        # A territory without a rule: to INVOICE what was charged it is indistinguishable from not subject
        # (both without quota) and the amount charged rules. To SELL it is not (``quote_vat``).
        qualification = _Qualification(NOT_SUBJECT, None, "", "")

    if qualification.rate is None:
        return _breakdown(
            gross,
            qualification.treatment,
            rate=None,
            tax_country=qualification.tax_country,
            tax_region=qualification.tax_region,
        )

    return _breakdown(
        gross,
        qualification.treatment,
        rate=qualification.rate,
        tax_country=qualification.tax_country,
        tax_region=qualification.tax_region,
        tax_cents=tax_cents,
        tax_included=tax_included,
        customer_country=qualification.customer_country,
    )


def _report_stripe_charged_no_tax(
    gross: Decimal,
    treatment: str,
    rate: Decimal,
    *,
    tax_country: str,
    customer_country: str,
) -> None:
    """A subject sale on which Stripe collected nothing: always a structured ERROR (alert on ``event``).

    Two misconfigurations end here —a sale that reached Stripe without our rate (saas#1478) and a VAT id
    Stripe reverse charged by its format while VIES had not confirmed it (saas#1479)— and both are silent
    on Stripe's side. The sale is reconciled out of our own margin until it is fixed.
    """
    logger.error(
        "[VAT] Stripe charged no tax on a %s sale of %s EUR at %s%% to a %s customer: reconciled as "
        "VAT-inclusive, so the quota comes out of our margin. Check the tax rules, the mirrored TaxRate in "
        "Stripe, FiscalPolicy.intra_eu_reverse_charge and the customer's VIES verdict",
        treatment,
        gross,
        rate,
        customer_country or "?",
        extra={
            "event": "fiscal.vat.stripe_charged_no_tax_on_subject_sale",
            "treatment": treatment,
            "gross": str(gross),
            "expected_rate": str(rate),
            "tax_country": tax_country,
            "customer_country": customer_country,
            "reconciled": True,
        },
    )


def _breakdown(
    gross: Decimal,
    treatment: str,
    *,
    rate: Decimal | None,
    tax_country: str,
    tax_region: str = "",
    tax_cents: int = 0,
    tax_included: bool = True,
    customer_country: str = "",
) -> VatBreakdown:
    """Split the amount charged between base and quota by the treatment."""
    if rate is None:
        # Not subject / reverse charge: all of it is base, there is no quota.
        return VatBreakdown(
            base=gross,
            tax=Decimal("0.00"),
            rate=Decimal("0.00"),
            tax_country=tax_country,
            treatment=treatment,
            tax_region=tax_region,
        )

    reconciled = False
    if not tax_included and not tax_cents:
        # NET price and Stripe charged no tax on a sale OUR qualification says is SUBJECT: reconcile
        # (saas#1479 + saas#1478). A Spanish domestic sale at 0 % does not exist; what was charged becomes
        # VAT-inclusive, as the tax office does when VAT was not charged (TJUE C-249/12 and C-250/12,
        # Tulică; art. 78.Cuatro LIVA). The total does not move; the quota comes out of our margin.
        _report_stripe_charged_no_tax(
            gross,
            treatment,
            rate,
            tax_country=tax_country,
            customer_country=customer_country,
        )
        reconciled = True

    if tax_cents:
        # Stripe already split it: its amounts rule.
        tax = _q(Decimal(tax_cents) / Decimal("100"))
        return VatBreakdown(
            base=gross - tax,
            tax=tax,
            rate=_effective_rate(gross, tax_cents),
            tax_country=tax_country,
            treatment=treatment,
            tax_region=tax_region,
        )

    base, tax = split_gross(gross, rate)
    return VatBreakdown(
        base=base,
        tax=tax,
        rate=rate,
        tax_country=tax_country,
        treatment=treatment,
        tax_region=tax_region,
        vat_included_reconciled=reconciled,
    )
