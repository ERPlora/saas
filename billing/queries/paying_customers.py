"""The paying customers of the admin: which businesses Stripe charges today, on what plan, since when and how much.

What a business pays is what it was actually charged: the base of its last invoice collected for a whole period,
never the price list, so a promo code or a paid app shows as charged.
"""

from django.db.models import OuterRef, Subquery, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from billing.models import Invoice, InvoiceLine, PayingCustomer
from billing.money import from_cents, to_cents
from billing.queries.billing_report import CUSTOMER_KINDS, customer_kind
from billing.queries.catalog import _ENDED_STATUSES
from billing.queries.invoices import _csv_amount, _csv_text, rows_csv
from hubs.models import Subscription


def _collected_invoices(hub):
    """The invoices (not credit notes) of ``hub`` that were collected; ``hub`` is an outer reference."""
    return Invoice.objects.filter(hub=hub, kind=Invoice.Kind.INVOICE, payment_status=Invoice.PaymentStatus.PAID)


def paying_customers():
    """Every business Stripe charges today (``is_paying``), each with ``customer_since`` (the date of its first
    collected invoice) and ``charged_cents`` (the base of the whole-period lines of its last collected invoice that
    has any: the prorations of a change in the middle of a period are not what it pays), with the period those lines
    bill (``charged_from``, ``charged_until``). ``None`` before its first collected invoice."""
    last_whole_period = (
        _collected_invoices(OuterRef(OuterRef("hub")))
        .filter(lines__proration=False)
        .order_by("-issued_on", "-sequence")
        .values("pk")[:1]
    )
    whole_period_lines = InvoiceLine.objects.filter(invoice=Subquery(last_whole_period), proration=False)
    charged = whole_period_lines.order_by().values("invoice").annotate(cents=Sum("net_cents")).values("cents")
    billed = whole_period_lines.order_by("position")
    return (
        PayingCustomer.objects.exclude(stripe_subscription_id="")
        .exclude(status__in=_ENDED_STATUSES)
        .select_related("hub__billing_profile", "plan")
        .annotate(
            customer_since=Subquery(_collected_invoices(OuterRef("hub")).order_by("issued_on").values("issued_on")[:1]),
            charged_cents=Subquery(charged[:1]),
            charged_from=Subquery(billed.values("period_start")[:1]),
            charged_until=Subquery(billed.values("period_end")[:1]),
        )
        .order_by("hub__name", "pk")
    )


#: A charge that bills more days than this is a year's: a month never reaches it.
_LONGEST_MONTHLY_PERIOD_DAYS = 62


def _charged_a_year(customer) -> bool:
    """Whether what ``customer`` was charged bills a year: told from the period of the lines charged, because a
    business that changed how often it pays is still on its last charge until the next one is collected. Lines
    without a period follow the subscription."""
    if customer.charged_from and customer.charged_until:
        return (customer.charged_until - customer.charged_from).days > _LONGEST_MONTHLY_PERIOD_DAYS
    return customer.billing_interval == Subscription.Interval.YEAR


def monthly_cents(customer) -> int | None:
    """What ``customer`` (a row of ``paying_customers``) pays a month before VAT: a yearly charge divided by 12."""
    if customer.charged_cents is None:
        return None
    if _charged_a_year(customer):
        return to_cents(from_cents(customer.charged_cents) / 12)
    return customer.charged_cents


def _payer_profile(customer):
    return customer.hub.billing_profile


def paying_customer_payer(customer) -> str:
    profile = _payer_profile(customer)
    return profile.billing_name if profile is not None else ""


def paying_customer_country(customer) -> str:
    profile = _payer_profile(customer)
    return profile.billing_country if profile is not None else ""


def paying_customer_kind(customer) -> str:
    """Company, self-employed or individual, told from its payer's tax ID as the billing report tells it."""
    profile = _payer_profile(customer)
    return customer_kind(paying_customer_country(customer), profile.tax_id if profile is not None else "")


def paying_customer_values(field: str) -> list[str]:
    """The values ``field`` takes among the paying customers, for a filter that offers only those."""
    return [value for value in paying_customers().order_by(field).values_list(field, flat=True).distinct() if value]


def _paying_customer_csv_columns() -> list:
    def amount(customer, separator):
        cents = monthly_cents(customer)
        return "" if cents is None else _csv_amount(cents, separator)

    return [
        (_("Business"), lambda customer, sep: _csv_text(customer.hub.name)),
        (_("Payer"), lambda customer, sep: _csv_text(paying_customer_payer(customer))),
        (_("Country"), lambda customer, sep: _csv_text(paying_customer_country(customer))),
        (_("Customer"), lambda customer, sep: str(CUSTOMER_KINDS[paying_customer_kind(customer)])),
        (_("Plan"), lambda customer, sep: _csv_text(customer.plan.translated("name"))),
        (_("Billing frequency"), lambda customer, sep: str(customer.get_billing_interval_display())),
        (_("Monthly tax base (€)"), amount),
        (_("Customer since"), lambda customer, sep: customer.customer_since.isoformat() if customer.customer_since else ""),
        (_("Status"), lambda customer, sep: str(customer.get_status_display())),
    ]


def paying_customers_csv(customers, language: str) -> dict:
    """The admin's «Download Excel» of the paying customers: the list's columns, in the billing report's format."""
    return rows_csv(
        customers.iterator(),
        _paying_customer_csv_columns,
        language=language,
        filename=f"erplora-paying-customers-{timezone.localdate().isoformat()}.csv",
    )
