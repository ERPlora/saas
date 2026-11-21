"""The audit of the rate table: what the admin's alert and ``manage.py audit_tax_rules`` report."""

from dataclasses import dataclass
from decimal import Decimal

from billing import vat, vat_breakdown, vat_countries
from billing.models import GENERIC_CATEGORY, TaxRule
from billing.queries.tax import fiscal_policy, tax_rule


# --- The audit of the rate table ----------------------------------------------------------------------

#: The three Spanish territories outside the scope of VAT, each with a postal code that belongs to it: the
#: postal code is the only thing that tells Las Palmas from Madrid, so the audit asks through the same door
#: as the checkout.
NON_VAT_TERRITORIES = (("IC", "35001"), ("CE", "51001"), ("ML", "52001"))

#: Any amount gives the same verdict (the rate never depends on it); 100 reads as a percentage.
_AUDIT_PROBE = Decimal("100.00")

#: Where every problem is fixed: an alert that says what broke but not where to go is a second question.
TAX_RULE_ADMIN_URL = "/admin/billing/taxrule/"


@dataclass(frozen=True)
class TaxRuleAuditLine:
    """Something the audit looked at and was happy with. ``is_warning`` is never a failure: the territory is
    carried by the backstop in ``vat.py`` (right rate, but neither editable in the admin nor schedulable)."""

    text: str
    is_warning: bool = False


@dataclass
class TaxRuleAuditReport:
    issuer: str
    category: str
    lines: list[TaxRuleAuditLine]
    problems: list[str]

    @property
    def is_red(self) -> bool:
        return bool(self.problems)


def tax_rule_audit() -> TaxRuleAuditReport:
    """Look at every sale we can make and report the ones that would go out wrong (or be refused).

    Three checks: the issuer is in the TABLE (not only in the backstop); the territories outside VAT still
    resolve as not subject, both in the table and through the postal code the checkout reads; every place
    with a payer on file (``hubs.BillingProfile``) resolves. Reads only the database: no Stripe, no network.
    The category is the one the plan is sold with, or the audit goes green on a key nobody sells.
    """
    policy = fiscal_policy()
    issuer = (policy.issuer_country or vat.DEFAULT_ISSUER_COUNTRY).strip().upper()
    category = vat.SAAS_SUBSCRIPTION_CATEGORY
    report = TaxRuleAuditReport(issuer=issuer, category=category, lines=[], problems=[])
    _audit_issuer(report)
    _audit_territories_outside_vat(report)
    _audit_payers_on_file(report)
    return report


def _audit_issuer(report: TaxRuleAuditReport) -> None:
    rule = tax_rule(country_code=report.issuer, category_key=report.category)
    if rule is not None:
        report.lines.append(TaxRuleAuditLine(f"  {report.issuer}: {rule}"))
        return
    report.problems.append(
        f"No TaxRule in force for {report.issuer} (the issuer). Sales do not stop — the backstop in "
        f"vat.py still charges the country's general rate — but the rate is no longer the one in the "
        f"admin, and a rate change cannot be scheduled. Add the {report.issuer} rule in {TAX_RULE_ADMIN_URL}."
    )


def _audit_territories_outside_vat(report: TaxRuleAuditReport) -> None:
    for region, postal_code in NON_VAT_TERRITORIES:
        rule = tax_rule(country_code="ES", region_code=region, category_key=report.category)
        if rule is None or rule.region_code.upper() != region:
            report.problems.append(_region_rule_does_not_answer(region, report.category))
            continue
        if rule.is_subject:
            report.problems.append(
                f"The ES/{region} rule is marked subject to VAT at {rule.rate_pct}%. That territory is "
                f"outside the scope of VAT: the sale goes out at the net price and the invoice declares it "
                f"not subject (N2). Uncheck 'Subject to VAT' on that rule in {TAX_RULE_ADMIN_URL}."
            )
            continue
        # The other half: what the checkout would quote. It reads the region from the POSTAL CODE, so this
        # catches a break in that map — the table can be perfect and a Canarian still be charged 21 %.
        quote = vat.quote_vat(
            _AUDIT_PROBE,
            customer_country="ES",
            customer_postal_code=postal_code,
            category_key=report.category,
        )
        if quote is None or quote.treatment != vat_breakdown.NOT_SUBJECT or quote.tax:
            charged = "nothing at all" if quote is None else f"{quote.tax} EUR ({quote.treatment})"
            report.problems.append(
                f"A sale to ES/{region} (postal code {postal_code}) quotes {charged} instead of resolving "
                f"as not subject. The rule is right, so what is broken is how the postal code maps to the "
                f"region (spanish_region_for_postal_code)."
            )
            continue
        report.lines.append(TaxRuleAuditLine(f"  ES/{region}: not subject (probe {postal_code})"))


def _region_rule_does_not_answer(region: str, category: str) -> str:
    """Say WHICH of the two things happened: a missing row is fixed by creating it, a row that stopped
    answering by ticking a box. The row is looked for with the precedence ``tax_rule`` uses —
    the category first, then the generic one — or another row of the territory is described instead."""
    rows = TaxRule.objects.filter(country_code="ES", region_code=region).order_by("-valid_from", "-id")
    shadow = next(
        (
            row
            for key in dict.fromkeys((category, GENERIC_CATEGORY))
            for row in rows.filter(category_id=key)[:1]
        ),
        None,
    )
    consequence = (
        "the table falls back to the mainland rate, which the VAT engine refuses: nobody is overcharged, "
        "but every paid checkout to that territory is REFUSED."
    )
    if shadow is None:
        return (
            f"No TaxRule for ES/{region}, so {consequence} Add the ES/{region} rule with 'Subject to VAT' "
            f"UNCHECKED in {TAX_RULE_ADMIN_URL}."
        )
    return (
        f"The ES/{region} rule is in the table but does not answer — 'Active' is unticked, or its validity "
        f"no longer covers today (active={shadow.is_active}, valid_from={shadow.valid_from}, "
        f"valid_to={shadow.valid_to or 'none'}). So {consequence} Tick 'Active' on that rule — or fix its "
        f"dates — in {TAX_RULE_ADMIN_URL}."
    )


def _audit_payers_on_file(report: TaxRuleAuditReport) -> None:
    """The countries we sell to are not a list somebody keeps: they are the payers on file. One quote per
    TERRITORY answers for every payer in it (the rate depends on nothing else)."""
    from hubs.models import BillingProfile

    on_file = (
        BillingProfile.objects.exclude(billing_country="")
        .values_list("billing_country", "billing_postal_code")
        .distinct()
    )
    territories: dict[tuple[str, str], str] = {}
    for country, postal_code in on_file:
        country = (country or "").strip().upper()
        region = vat_countries.spanish_region_for_postal_code(postal_code) if country == "ES" else ""
        if region is None:
            report.problems.append(
                f"A payer is on file in ES with the postal code {postal_code!r}, which is not a Spanish "
                f"postal code: the territory is unknown, so a paid checkout to that address is REFUSED "
                f"until the business's billing details are corrected."
            )
            continue
        territories.setdefault((country, region), postal_code)

    for (country, region), postal_code in sorted(territories.items()):
        where = f"{country}/{region}" if region else country
        quote = vat.quote_vat(
            _AUDIT_PROBE,
            customer_country=country,
            customer_postal_code=postal_code,
            category_key=report.category,
        )
        if quote is None:
            report.problems.append(
                f"A payer is on file in {where} and no rule resolves there, so a paid checkout to that "
                f"address is REFUSED (the price is net: selling without the rate would be paying the VAT "
                f"ourselves). Add the {where} rule in {TAX_RULE_ADMIN_URL}."
            )
            continue
        report.lines.append(
            TaxRuleAuditLine(f"  {where}: {quote.treatment} {quote.rate}% (payer on file)")
        )
        if tax_rule(country_code=country, region_code=region, category_key=report.category) is None:
            report.lines.append(
                TaxRuleAuditLine(
                    "    ^ that rate comes from the backstop in vat.py, not from the table: it can be "
                    "neither edited in the admin nor scheduled to change.",
                    is_warning=True,
                )
            )
