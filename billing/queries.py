"""Reads of billing: the rule in force, the policy, ERPlora's identity, the VIES log, the payer of a
business, and the operation ``billing.tax.preview``.

Only this module and ``services.py`` touch the ORM: the VAT engine (``billing.vat``) reads the table and the
policy through the functions below. Nothing here asks VIES nor writes: a query runs READ ONLY.

The Billing section (lot L3-C): ``billing.invoice.{list,get,pdf,csv}`` (ERPlora's invoices; the PDF is asked
to the platform hub), ``billing.subscription.list`` and ``billing.payment_method.get`` (the card, asked to
Stripe and kept a few minutes).
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from django_ratelimit.core import is_ratelimited
from live.context import OperationContext
from live.errors import OperationError, Unauthorized
from live.operations import operation

from apps import queries as app_queries
from apps.icons import FALLBACK_ICON_SVG
from apps.models import Module
from billing import vat, vies
from billing.models import (
    Invoice,
    CompanyConfig,
    FiscalPolicy,
    GENERIC_CATEGORY,
    PromoCode,
    PromoRedemption,
    TaxRule,
    VatCheck,
    normalise_promo_code,
)
from billing.money import from_cents, to_cents
from hubs.models import Plan
from billing.schemas import PromoCheckIn, PromoCheckOut, TaxPreviewIn, TaxPreviewOut
from billing.schemas import StoreCatalogIn, StoreCatalogOut
from hubs import queries as hub_queries
from hubs import services as hub_services
from hubs.models import HubMember, Subscription, SubscriptionItem
import csv
import io

from django.core.cache import cache
from django.db.models import Subquery
from django.db.models.functions import Coalesce, TruncDate
from django.utils import formats, translation
from live.errors import NotFound

from billing.models import PaymentFailure, PlanChangeSchedule
from billing.schemas import (
    InvoiceByIdIn,
    InvoiceDetailOut,
    InvoiceFileOut,
    InvoiceFilterIn,
    InvoiceListIn,
    InvoiceListOut,
    PaymentMethodIn,
    PaymentMethodOut,
    SubscriptionListIn,
    SubscriptionListOut,
)
from billing import stripe_service
from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub

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


# --- The audit of the rate table (BILLING-F04, saas#1968, saas#1995) ---------------------------------

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
        if quote is None or quote.treatment != vat.NOT_SUBJECT or quote.tax:
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
    answering by ticking a box (saas#1995). The row is looked for with the precedence ``tax_rule`` uses —
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
        region = vat.spanish_region_for_postal_code(postal_code) if country == "ES" else ""
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


def cross_border_b2c_cents(policy: FiscalPolicy, year: int) -> int:
    """The tax base of the year's intra-EU B2C distance sales, in integer cents (the OSS threshold).

    The sales to consumers of OTHER member states —a payer without a VIES-verified VAT number; an
    unverified business was taxed like a consumer and counts (saas#1969)— invoiced outside this SaaS by the
    old one, carried by hand in ``FiscalPolicy`` for ``oss_carried_year`` and the year before, plus
    ERPlora's invoices issued here that year (``billing.Invoice``, lot L3-C: paid ones and their credit
    notes, which take their base back). Only the base counts: the threshold is on the value of the
    supplies, VAT excluded. Domestic and non-EU sales never count.
    """
    carried = 0
    carried_year = policy.oss_carried_year
    if carried_year is not None and year == carried_year:
        carried = int(policy.oss_carried_current_cents)
    elif carried_year is not None and year == carried_year - 1:
        carried = int(policy.oss_carried_previous_cents)
    issuer = (policy.issuer_country or vat.DEFAULT_ISSUER_COUNTRY).strip().upper()
    invoiced = Invoice.objects.filter(
        payment_status=Invoice.PaymentStatus.PAID,
        issued_on__year=year,
        payer_country__in=[code for code in vat.EU_VAT_RATES if code != issuer],
        payer_tax_id_verified=False,
    ).aggregate(total=Sum("net_cents"))["total"]
    return carried + int(invoiced or 0)


def oss_total_is_known(policy: FiscalPolicy, year: int) -> bool:
    """Whether the year's cross-border B2C total is a fact or an assumption. Until the old SaaS's amounts are
    carried (``oss_carried_year``) a 0 is not a fact, and the admin says «unknown». From the carried year on it
    is: the old SaaS sells no more, so a later year is this SaaS's invoices alone, and the carried «this year»
    is that year's «last year» (``cross_border_b2c_cents``), with nobody editing the policy each January
    (review of L3-C)."""
    return policy.oss_carried_year is not None and year >= policy.oss_carried_year


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


def vat_verdict_as_of(vat_number: str, moment) -> VatCheck | None:
    """The last verdict VIES gave about a number until ``moment``, whatever its age: a verification WITH proof
    (consultation number or manual override) or a refusal. What it said then is what an invoice of then is
    judged by (``services._payer_clearance``); «could not answer» says nothing."""
    with_proof = Q(status=VatCheck.VERIFIED) & (~Q(consultation_number="") | Q(override_at__isnull=False))
    return (
        VatCheck.objects.filter(vat_number=vies.normalise(vat_number), requested_at__lte=moment)
        .filter(with_proof | Q(status=VatCheck.INVALID))
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
    expose_api=True,
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


# --- Promo codes (lot L2-B) --------------------------------------------------------------------------

#: The per-person budget of ``billing.promo.check``.
PROMO_CHECK_GROUP = "billing.promo-check"


def redeemable_promo(
    code: str | None, *, hub=None, customer: str = ""
) -> PromoCode | None:
    """The promo code that grants a trial now, or ``None``: unknown, inactive, expired and exhausted are all
    ``None``, because none of them may block a sale (a bad code is simply not applied). With ``hub`` (and its
    payer's Stripe ``customer``), also ``None`` once that business or that payer used it (review of L2-B)."""
    normalised = normalise_promo_code(code)
    if not normalised:
        return None
    promo = PromoCode.objects.filter(code=normalised).first()
    if promo is None or not promo.is_redeemable:
        return None
    if hub is not None:
        used_by = (
            Q(hub=hub) | Q(stripe_customer_id=customer) if customer else Q(hub=hub)
        )
        if PromoRedemption.objects.filter(promo=promo).filter(used_by).exists():
            return None
    return promo


@operation(
    "billing.promo.check",
    kind="query",
    permission="billing.view",
    input=PromoCheckIn,
    output=PromoCheckOut,
)
def promo_check(ctx: OperationContext, params: PromoCheckIn) -> dict:
    """Whether a promo code grants a trial now, before paying (the store). An invalid code is an answer, not
    an error; asking too often is a 429, so codes cannot be guessed by brute force."""
    account = ctx.actor
    if getattr(account, "pk", None) is None:
        raise Unauthorized(_("Sign in to use a promo code."))
    if is_ratelimited(
        None,
        group=PROMO_CHECK_GROUP,
        key=lambda group, request: f"user:{account.pk}",
        rate=settings.PROMO_CHECK_RATE,
        increment=True,
    ):
        raise OperationError(
            _("Too many promo codes tried in the last minute. Try again in a moment."),
            code="billing.promo_check_throttled",
            status=429,
        )
    code = normalise_promo_code(params.code)
    promo = redeemable_promo(code)
    return {
        "code": code,
        "valid": promo is not None,
        "trial_days": promo.trial_days if promo else 0,
    }


# --- What is sold, and what Stripe bills (lot L2-B) --------------------------------------------------


def plan_on_sale(slug: str):
    """The active plan with that slug, or ``None``."""
    return Plan.objects.filter(slug=slug, is_active=True).first()


def module_on_sale(slug: str):
    """The paid module with that slug, while it is on sale (``apps.Module``), or ``None``."""
    return Module.objects.filter(slug=slug, is_active=True).first()


def businesses_having_module(slug: str) -> list[str]:
    """The names of the businesses that have the bought module ``slug`` now (open-ended, or cancelled and still
    working): what Stripe bills or billed for this period (BILLING-G66, saas#2568: its row is not deleted)."""
    now = timezone.now()
    items = SubscriptionItem.objects.filter(
        module_slug=slug, source=SubscriptionItem.Source.PURCHASE
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
    return sorted(set(items.values_list("subscription__hub__name", flat=True)))


def plan_for_price(price_id: str):
    """``(plan, interval)`` of a Stripe price of a plan, or ``None`` when no plan has it."""
    if not price_id:
        return None
    plan = Plan.objects.filter(stripe_price_id=price_id).first()
    if plan is not None:
        return plan, "month"
    plan = Plan.objects.filter(stripe_price_id_annual=price_id).first()
    return (plan, "year") if plan is not None else None


def module_for_price(price_id: str):
    """``(module, interval)`` of a Stripe price of a module (retired ones too), or ``None``."""
    if not price_id:
        return None
    module = Module.objects.filter(stripe_price_id_monthly=price_id).first()
    if module is not None:
        return module, "month"
    module = Module.objects.filter(stripe_price_id_annual=price_id).first()
    return (module, "year") if module is not None else None


# --- The Store (lot L2-D) ----------------------------------------------------------------------------

#: Statuses of a Stripe subscription that bill nothing any more (``billing.services.ENDED_STATUSES``).
_ENDED_STATUSES = frozenset({"canceled", "incomplete_expired"})


def is_paying(subscription: Subscription | None) -> bool:
    """Stripe bills the business already: it has a subscription there that has not ended."""
    return (
        subscription is not None
        and bool(subscription.stripe_subscription_id)
        and subscription.status not in _ENDED_STATUSES
    )


def offered_plans(paying: bool):
    """The paid plans on sale a business may move to (audit 2 S-03; the catalogue, ``hubs/0013``): the ones sold at sign-up
    while Stripe does not bill it (Free), the ``upgrade_only`` ones too once it pays. Free is not bought (a paid
    plan is cancelled to get it) and an ``internal_only`` plan is never offered here."""
    plans = Plan.objects.public().filter(price_monthly__gt=0)
    if not paying:
        plans = plans.filter(upgrade_only=False)
    return plans.order_by("display_order", "price_monthly")


@operation(
    "billing.store.catalog",
    kind="query",
    permission="billing.view",
    input=StoreCatalogIn,
    output=StoreCatalogOut,
)
def store_catalog(ctx: OperationContext, params: StoreCatalogIn) -> dict:
    """What the Store sells the business and what it already has: every paid module on sale with its net
    prices in cents, whether the business owns it (bought or included in its plan; a cancelled one until it
    ends), the plan, its billing and whether Stripe bills it already, and the paid plans it may move to
    (``offered_plans``: no upgrade-only plan for a business Stripe does not bill, audit 2 S-03). Only the owner buys for a business
    (round 17 §2.7), so only the owner reads it; a deleted business buys nothing (409). Never asks Stripe."""
    member = hub_queries.access(hub_queries.account_of(ctx), params.hub_id, HubMember.Role.OWNER)
    if not hub_queries.is_writable(member.hub):
        raise hub_services.business_deleted()
    subscription = (
        Subscription.objects.select_related("plan", "trial_plan").filter(hub_id=member.hub_id).first()
    )
    now = timezone.now()
    owned = {}
    if subscription is not None:
        for item in SubscriptionItem.objects.filter(subscription=subscription).order_by("module_slug"):
            if item.is_live(now):
                owned[item.module_slug] = item
    # On sale, and the ones the business has although they are not any more (saas#2589: taking a module off
    # sale stops new purchases, never the charge of who has it, so its owner still sees it to cancel it).
    rows = Module.objects.filter(Q(is_active=True) | Q(slug__in=owned)).order_by("slug")
    cards = app_queries.cards_of([row.slug for row in rows], ctx.language or "")
    modules = []
    for module in rows:
        item = owned.get(module.slug)
        card = cards.get(module.slug)
        modules.append(
            {
                "slug": module.slug,
                "tier": module.tier,
                "price_monthly_cents": module.price_monthly_cents,
                "price_annual_cents": module.price_annual_cents,
                "owned": item is not None,
                "source": item.source if item is not None else None,
                "valid_until": item.valid_until if item is not None else None,
                "on_sale": module.is_active,
                "name": card["name"] if card else module.slug,
                "summary": card["summary"] if card else "",
                "icon_svg": card["icon_svg"] if card else FALLBACK_ICON_SVG,
            }
        )
    plan = None
    paying = is_paying(subscription)
    if subscription is not None:
        plan = {
            "plan": subscription.plan.slug,
            "billing_interval": subscription.billing_interval,
            "status": subscription.status,
            "paying": paying,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "current_period_end": subscription.current_period_end,
            "trial_plan": subscription.trial_plan.slug if subscription.trial_plan_id else None,
            "trial_end": subscription.trial_end,
        }
    return {
        "hub_id": member.hub_id,
        "subscription": plan,
        "modules": modules,
        "offered_plans": [offered.slug for offered in offered_plans(paying)],
    }


# --- The Billing section: ERPlora's invoices, the subscriptions and the payment details (lot L3-C) -----
#
# Who sees an invoice: the account that paid it (its payer that day) and the current owner of its business
# (round 17 §2.7: the owner manages billing); nobody else, whatever their role: a 404, never a hint. The same
# rule gives the subscriptions (the owner's businesses and the ones the account pays) and the cards (only the
# account's own payers: a card is never shown to anybody but whoever it belongs to).

#: Issued by the platform hub: the invoice has its QR and its PDF.
ISSUED_STATUSES = ("issued", "accepted", "accepted_with_errors")
#: A card is asked to Stripe at most this often per payer; ``customer.updated`` forgets it before.
CARD_CACHE_SECONDS = 10 * 60


def _billing_account(ctx: OperationContext):
    if ctx.actor is None or isinstance(ctx.actor, str):
        raise Unauthorized(_("Sign in to see your billing."))
    return ctx.actor


def _owned_hub_ids(user):
    return HubMember.objects.filter(user=user, role=HubMember.Role.OWNER, accepted_at__isnull=False).values("hub_id")


def invoices_of(user):
    """Every invoice the account sees: the ones it paid and the ones of the businesses it owns."""
    return Invoice.objects.filter(Q(payer_account=user) | Q(hub_id__in=Subquery(_owned_hub_ids(user))))


def invoice_of(user, invoice_id) -> Invoice:
    """One invoice the account sees, or 404 (an invoice of somebody else's does not exist for it)."""
    invoice = (
        invoices_of(user).select_related("hub__billing_profile", "rectifies").filter(pk=invoice_id).first()
    )
    if invoice is None:
        raise NotFound(_("This invoice does not exist or you have no access to it."))
    return invoice


def pays_for(user, invoice: Invoice) -> bool:
    """Whether the account pays the business of ``invoice`` now (its ``BillingProfile`` is the account's);
    without the business, whether it paid the invoice."""
    profile = invoice.hub.billing_profile if invoice.hub_id and invoice.hub else None
    if profile is not None:
        return profile.owner_id == user.pk
    return invoice.payer_account_id == user.pk


def _cards_declined(stripe_invoice_ids) -> set[str]:
    """The Stripe invoices whose payment the bank declined with the card still unchanged (mockups §6.18)."""
    return set(
        PaymentFailure.objects.filter(
            stripe_invoice_id__in=list(stripe_invoice_ids),
            resolved_at__isnull=True,
            reason=PaymentFailure.Reason.CARD_DECLINED,
            card_changed_at__isnull=True,
        ).values_list("stripe_invoice_id", flat=True)
    )


def card_change_required(invoice: Invoice) -> bool:
    return invoice.stripe_invoice_id in _cards_declined([invoice.stripe_invoice_id])


def _filtered_invoices(user, data: InvoiceFilterIn):
    invoices = invoices_of(user).select_related("hub__billing_profile")
    if data.hub_id is not None:
        invoices = invoices.filter(hub_id=data.hub_id)
    if data.status:
        invoices = invoices.filter(payment_status=data.status)
    if data.year:
        invoices = invoices.filter(
            Q(issued_on__year=data.year) | Q(issued_on__isnull=True, billed_at__year=data.year)
        )
    if data.search:
        invoices = invoices.filter(Q(number__icontains=data.search) | Q(stripe_number__icontains=data.search))
    return invoices.annotate(
        on=Coalesce("issued_on", TruncDate("billed_at"), TruncDate("created_at"))
    ).order_by("-on", "-sequence", "-created_at")


def _date_of(invoice: Invoice) -> date:
    if invoice.issued_on is not None:
        return invoice.issued_on
    return timezone.localdate(invoice.billed_at or invoice.created_at)


def _invoice_row(invoice: Invoice, user, declined: set[str]) -> dict:
    paid = invoice.payment_status == Invoice.PaymentStatus.PAID
    pdf = paid and invoice.fiscal_status in ISSUED_STATUSES
    actions, can_pay, blocked = [], False, None
    if invoice.payment_status == Invoice.PaymentStatus.OPEN:
        actions.append("pay")
        if not pays_for(user, invoice):
            blocked = "payer_required"
        elif invoice.stripe_invoice_id in declined:
            blocked = "card_change_required"
        else:
            can_pay = bool(invoice.hosted_invoice_url)
    if pdf:
        actions.append("pdf")
    return {
        "id": invoice.id,
        "kind": invoice.kind,
        "kind_label": str(Invoice.Kind(invoice.kind).label),
        "number": invoice.number or None,
        "reference": invoice.stripe_number,
        "date": _date_of(invoice),
        "business": {"id": invoice.hub_id, "name": invoice.business_name},
        "currency": invoice.currency,
        "net_cents": invoice.net_cents,
        "tax_cents": invoice.tax_cents,
        "total_cents": invoice.total_cents,
        "payment_status": invoice.payment_status,
        "payment_status_label": str(Invoice.PaymentStatus(invoice.payment_status).label),
        "fiscal_status": invoice.fiscal_status,
        "fiscal_status_label": str(Invoice.FiscalStatus(invoice.fiscal_status).label),
        "pay_blocked_reason": blocked,
        "actions": actions,
        "can": {"pay": can_pay, "pdf": pdf},
        "rectification": (
            {"type": invoice.rectification_type, "reason": invoice.rectification_reason}
            if invoice.rectification_type
            else None
        ),
        "stripe_source_id": invoice.stripe_source_id,
    }


@operation(
    "billing.invoice.list",
    kind="query",
    permission="billing.view",
    input=InvoiceListIn,
    output=InvoiceListOut,
    expose_api=True,
)
def invoice_list(ctx: OperationContext, data: InvoiceListIn) -> dict:
    """ERPlora's invoices of the account, the newest first, filtered by business, payment, year and number:
    the paid ones with their number, the ones not collected yet with Stripe's reference and «Pay»."""
    user = _billing_account(ctx)
    invoices = _filtered_invoices(user, data)
    total = invoices.count()
    page = list(invoices[data.offset : data.offset + data.limit])
    declined = _cards_declined(i.stripe_invoice_id for i in page if i.payment_status == Invoice.PaymentStatus.OPEN)
    with translation.override(ctx.language):
        rows = [_invoice_row(invoice, user, declined) for invoice in page]
    return {"rows": rows, "total": total, "limit": data.limit, "offset": data.offset}


@operation(
    "billing.invoice.get",
    kind="query",
    permission="billing.view",
    input=InvoiceByIdIn,
    output=InvoiceDetailOut,
    expose_api=True,
)
def invoice_get(ctx: OperationContext, data: InvoiceByIdIn) -> dict:
    """One invoice with its lines, its recipient as it was on the issue date and its QR."""
    user = _billing_account(ctx)
    invoice = invoice_of(user, data.id)
    declined = _cards_declined([invoice.stripe_invoice_id])
    with translation.override(ctx.language):
        row = _invoice_row(invoice, user, declined)
    rectified = invoice.rectifies
    return {
        **row,
        "issued_on": invoice.issued_on,
        "paid_at": invoice.paid_at,
        "tax_treatment": invoice.tax_treatment,
        "tax_country": invoice.tax_country,
        "tax_rate": invoice.tax_rate,
        "recipient": {
            "name": invoice.payer_name,
            "tax_id": invoice.payer_tax_id,
            "address": invoice.payer_address,
            "city": invoice.payer_city,
            "postal_code": invoice.payer_postal_code,
            "country": invoice.payer_country,
            "email": invoice.payer_email,
        },
        "lines": [
            {
                "position": line.position,
                "description": line.description,
                "item_kind": line.item_kind,
                "item_slug": line.item_slug,
                "quantity": line.quantity,
                "proration": line.proration,
                "period_start": line.period_start,
                "period_end": line.period_end,
                "tax_rate": line.tax_rate,
                "net_cents": line.net_cents,
                "tax_cents": line.tax_cents,
                "total_cents": line.total_cents,
            }
            for line in invoice.lines.order_by("position")
        ],
        "rectifies": {"id": rectified.id, "number": rectified.number} if rectified is not None else None,
        "qr": invoice.qr,
    }


@operation(
    "billing.invoice.pdf",
    kind="query",
    permission="billing.view",
    input=InvoiceByIdIn,
    output=InvoiceFileOut,
    expose_api=True,
)
def invoice_pdf(ctx: OperationContext, data: InvoiceByIdIn) -> dict:
    """The PDF of an invoice, as ERPlora's platform hub issued it (``GET /internal/platform/invoices/{id}/pdf``,
    asked on demand: round 17 §2.7). 404 ``billing.invoice_not_issued`` until the Hub issued it."""
    user = _billing_account(ctx)
    invoice = invoice_of(user, data.id)
    return {"filename": f"{invoice.number}.pdf", "content_type": "application/pdf", "content": platform_invoice_pdf(invoice)}


def platform_invoice_pdf(invoice: Invoice) -> bytes:
    """The PDF ERPlora's platform hub issued of ``invoice``, asked now (also the admin's, BILLING-G12): 404
    ``billing.invoice_not_issued`` until it is issued, 503 ``billing.platform_unavailable`` with the Hub away."""
    if invoice.payment_status != Invoice.PaymentStatus.PAID or invoice.fiscal_status not in ISSUED_STATUSES:
        raise NotFound(
            _("This invoice is still being issued: its PDF is ready once it is."), code="billing.invoice_not_issued"
        )
    try:
        return hub_client.get_platform_invoice_pdf(str(invoice.id))
    except HubUnavailable:
        raise OperationError(
            _("The invoice cannot be downloaded right now. Try again in a moment."),
            code="billing.platform_unavailable",
            status=503,
        ) from None
    except HubRefused as refused:
        logger.error("[INVOICE] The platform hub has no PDF of invoice %s: %s", invoice.number, refused)
        raise NotFound(
            _("This invoice is still being issued: its PDF is ready once it is."), code="billing.invoice_not_issued"
        ) from None


#: What makes a spreadsheet read a cell as a formula (CSV injection, OWASP).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _csv_text(value: str) -> str:
    """A text cell that cannot run as a formula in the accountant's spreadsheet (review of L3-C)."""
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def _csv_amount(cents: int, separator: str) -> str:
    return f"{from_cents(cents):.2f}".replace(".", separator)


@operation(
    "billing.invoice.csv",
    kind="query",
    permission="billing.view",
    input=InvoiceFilterIn,
    output=InvoiceFileOut,
    expose_api=True,
)
def invoice_csv(ctx: OperationContext, data: InvoiceFilterIn) -> dict:
    """«Download Excel» (W-F9): the invoices the filters show, all of them, as CSV for the accountant.

    UTF-8 with its BOM, so Excel reads the accents; in a language that writes a decimal comma (Spanish) the
    columns are split by «;» and the amounts carry the comma, as Excel expects there; elsewhere «,» and «.».
    Dates in ISO (Excel reads them in every language)."""
    user = _billing_account(ctx)
    with translation.override(ctx.language):
        separator = formats.get_format("DECIMAL_SEPARATOR", lang=ctx.language)
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";" if separator == "," else ",")
        writer.writerow(
            [_("Invoice"), _("Date"), _("Business"), _("Tax base"), _("VAT"), _("Total"), _("Currency"),
             _("Payment"), _("Status")]
        )
        for invoice in _filtered_invoices(user, data).iterator():
            writer.writerow(
                [
                    _csv_text(invoice.number or invoice.stripe_number),
                    _date_of(invoice).isoformat(),
                    _csv_text(invoice.business_name),
                    _csv_amount(invoice.net_cents, separator),
                    _csv_amount(invoice.tax_cents, separator),
                    _csv_amount(invoice.total_cents, separator),
                    _csv_text(invoice.currency),
                    _csv_text(str(Invoice.PaymentStatus(invoice.payment_status).label)),
                    _csv_text(str(Invoice.FiscalStatus(invoice.fiscal_status).label)),
                ]
            )
    return {
        "filename": f"erplora-invoices-{timezone.localdate().isoformat()}.csv",
        "content_type": "text/csv; charset=utf-8",
        "content": ("\ufeff" + buffer.getvalue()).encode("utf-8"),
    }


# --- Subscriptions -----------------------------------------------------------------------------------

#: A Stripe subscription that ended bills nothing: the business is back on Free (PLAN-SAAS §3.3).
ENDED_SUBSCRIPTIONS = ("canceled", "incomplete_expired")


def _module_price(module: Module | None, interval: str) -> int | None:
    if module is None:
        return None
    return module.price_annual_cents if interval == "year" else module.price_monthly_cents


def _with_vat_cents(parts: list[tuple[int, str]], payer: Payer) -> int | None:
    """What net amounts cost with VAT for this payer (``parts``: ``(cents, category)``), as the checkout
    prices them; ``None`` while the payer's place is unknown or has no rule."""
    if not payer.has_location:
        return None
    verified = _vat_status_on_file(payer.tax_id, payer.country) == "verified"
    total = 0
    for cents, category in parts:
        quote = vat.quote_vat(
            from_cents(cents),
            customer_country=payer.country,
            customer_postal_code=payer.postal_code,
            customer_tax_id=payer.tax_id,
            customer_tax_id_type=payer.tax_id_type,
            customer_tax_id_verified=verified,
            category_key=category,
        )
        if quote is None:
            return None
        total += to_cents(quote.base + quote.tax)
    return total


def _subscription_row(
    subscription: Subscription, user, owned: set, unpaid: dict, modules: dict, scheduled: dict
) -> dict:
    hub = subscription.hub
    plan = subscription.plan
    interval = subscription.billing_interval
    plan_cents = to_cents((plan.price_annual if interval == "year" else plan.price_monthly) or 0)
    items = []
    billed = [(plan_cents, vat.SAAS_SUBSCRIPTION_CATEGORY)] if plan_cents else []
    for item in subscription.items.all():
        price = _module_price(modules.get(item.module_slug), interval)
        items.append(
            {
                "slug": item.module_slug,
                "interval": interval,
                "price_cents": price,
                "source": item.source,
                "valid_until": item.valid_until,
            }
        )
        if item.source == "purchase" and item.valid_until is None and price:
            billed.append((price, vat.SOFTWARE_LICENSE_CATEGORY))
    cancelling = subscription.cancel_at_period_end
    next_invoice = None
    if not cancelling:
        next_invoice = {
            "date": subscription.current_period_end,
            "total_cents": _with_vat_cents(billed, payer_of(hub)),
            "currency": "EUR",
        }
    profile = hub.billing_profile
    manages = (
        hub.id in owned
        and profile is not None
        and profile.owner_id == user.pk
        and hub_queries.is_writable(hub)
    )
    unpaid_id = unpaid.get(hub.id)
    can = {
        "change_plan": manages and unpaid_id is None,
        "cancel_plan": manages and not cancelling,
        "keep_plan": manages and cancelling,
        "view_invoice": unpaid_id is not None,
        "view_invoices": True,
    }
    order = ["view_invoice", *(["keep_plan", "change_plan"] if cancelling else ["change_plan", "cancel_plan"]),
             "view_invoices"]
    return {
        "business": {"id": hub.id, "name": hub.name},
        "plan": {"slug": plan.slug, "name": plan.translated("name"), "interval": interval, "price_cents": plan_cents},
        "modules": items,
        "next_invoice": next_invoice,
        "status": subscription.status,
        "status_label": str(Subscription.Status(subscription.status).label),
        "cancelling": cancelling,
        "ends_at": subscription.current_period_end if cancelling else None,
        "cancel_requested": subscription.cancel_requested_at is not None,
        "unpaid_invoice_id": unpaid_id,
        "scheduled_change": scheduled.get(hub.id),
        "actions": [action for action in order if can[action]],
        "can": can,
    }


@operation(
    "billing.subscription.list",
    kind="query",
    permission="billing.view",
    input=SubscriptionListIn,
    output=SubscriptionListOut,
)
def subscription_list(ctx: OperationContext, data: SubscriptionListIn) -> dict:
    """One row per business of the account that Stripe bills (it owns it or pays it): the plan and modules at
    their net price, the next invoice with VAT and what the row's buttons do (mockups ``billing.html``)."""
    user = _billing_account(ctx)
    owned = set(_owned_hub_ids(user).values_list("hub_id", flat=True))
    subscriptions = (
        Subscription.objects.select_related("hub__billing_profile", "plan")
        .prefetch_related("items")
        .filter(Q(hub_id__in=owned) | Q(hub__billing_profile__owner=user))
        .exclude(stripe_subscription_id="")
        .exclude(status__in=ENDED_SUBSCRIPTIONS)
        .exclude(hub__status=Hub.Status.DELETED)
        .order_by("hub__name", "hub_id")
    )
    total = subscriptions.count()
    page = list(subscriptions[data.offset : data.offset + data.limit])
    unpaid = {}
    for hub_id, invoice_id in (
        Invoice.objects.filter(
            hub_id__in=[s.hub_id for s in page], kind=Invoice.Kind.INVOICE, payment_status=Invoice.PaymentStatus.OPEN
        )
        .order_by("-billed_at")
        .values_list("hub_id", "id")
    ):
        unpaid[hub_id] = invoice_id
    slugs = {item.module_slug for subscription in page for item in subscription.items.all()}
    modules = {module.slug: module for module in Module.objects.filter(slug__in=slugs)}
    with translation.override(ctx.language):
        scheduled = {
            change.hub_id: {"plan": change.plan_slug, "interval": change.interval, "starts_at": change.starts_at}
            for change in PlanChangeSchedule.objects.filter(hub_id__in=[s.hub_id for s in page])
        }
        rows = [
            _subscription_row(subscription, user, owned, unpaid, modules, scheduled) for subscription in page
        ]
    return {"rows": rows, "total": total, "limit": data.limit, "offset": data.offset}


# --- Payment details --------------------------------------------------------------------------------


def card_cache_key(customer_id: str) -> str:
    return f"billing.card.{customer_id}"


def _card_of(customer_id: str, subscription_id: str) -> tuple[dict | None, bool]:
    """The card of a payer, ``(card, unavailable)``: kept ``CARD_CACHE_SECONDS``; Stripe away is
    ``unavailable`` (never cached, never invented)."""
    key = card_cache_key(customer_id)
    kept = cache.get(key)
    if kept is not None:
        return kept.get("card"), False
    try:
        card = stripe_service.payment_card(subscription_id=subscription_id, customer_id=customer_id)
    except (stripe_service.StripeUnavailable, stripe_service.StripeNotConfigured, stripe_service.StripeRefused):
        logger.warning("[BILLING] Stripe did not give the card of customer %s", customer_id)
        return None, True
    cache.set(key, {"card": card}, CARD_CACHE_SECONDS)
    return card, False


@operation(
    "billing.payment_method.get",
    kind="query",
    permission="billing.view",
    input=PaymentMethodIn,
    output=PaymentMethodOut,
)
def payment_method_get(ctx: OperationContext, data: PaymentMethodIn) -> dict:
    """The card of each of the account's payers (one Stripe customer per business's payer), the businesses it
    pays and its last failed charge. Read from Stripe (the subscription's card, else the customer's default),
    kept a few minutes; changing it is Stripe's Customer Portal (``billing.portal.open``)."""
    user = _billing_account(ctx)
    hubs = (
        Hub.objects.select_related("billing_profile", "subscription")
        .filter(billing_profile__owner=user)
        .exclude(billing_profile__stripe_customer_id="")
        .exclude(status=Hub.Status.DELETED)
        .order_by("name", "id")
    )
    if data.hub_id is not None:
        hubs = hubs.filter(pk=data.hub_id)
    customers: dict[str, list[Hub]] = {}
    for hub in hubs:
        customers.setdefault(hub.billing_profile.stripe_customer_id, []).append(hub)
    methods = []
    for customer, businesses in customers.items():
        billed = [
            hub
            for hub in businesses
            if getattr(hub, "subscription", None) is not None
            and hub.subscription.stripe_subscription_id
            and hub.subscription.status not in ENDED_SUBSCRIPTIONS
        ]
        paying = billed[0].subscription.stripe_subscription_id if billed else ""
        card, unavailable = _card_of(customer, paying)
        failure = (
            PaymentFailure.objects.select_related("hub")
            .filter(hub__in=businesses, resolved_at__isnull=True)
            .order_by("-failed_at")
            .first()
        )
        methods.append(
            {
                # The card pays the businesses Stripe bills; a Free one on the same payer is not paid with it (audit 2
                # R-26). With none billed, the ones it is kept for.
                "businesses": [{"id": hub.id, "name": hub.name} for hub in billed or businesses],
                "card": card,
                "unavailable": unavailable,
                "last_failure": {"at": failure.failed_at, "business": failure.hub.name} if failure else None,
            }
        )
    return {"methods": methods}

