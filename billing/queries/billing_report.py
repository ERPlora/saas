"""The admin's billing report: what ERPlora invoiced in a month, a quarter or a year, and its Excel."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import F, Count, Sum, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils.translation import gettext_lazy

from billing.models import TAX_TREATMENTS, Invoice, InvoiceLine
from billing.money import from_cents
from billing.nif import is_legal_person_nif, is_spanish_tax_id, normalise_nif
from billing.queries.invoices import ISSUED_STATUSES, REPORT_CSV_COLUMNS, invoices_csv
from hubs.countries import PAYER_COUNTRY_NAMES


# --- The billing report of the admin -------------------------------------------------------------------
#
# What ERPlora invoiced in a month, a quarter or a year, for the accountant: only invoices that were collected
# and issued by the platform hub count, on their issue date. A credit note is negative, so the net is a plain sum.


@dataclass(frozen=True)
class ReportPeriod:
    year: int
    period: str
    start: date
    end: date
    #: How the period is named in the file: ``2026``, ``2026-Q3`` or ``2026-08``.
    key: str


def report_period(year: int, period: str) -> ReportPeriod:
    """``period`` is ``year``, a quarter (``q1``…``q4``) or a month (``m1``…``m12``); anything else is a
    ``ValueError``."""
    if period == "year":
        return ReportPeriod(year, period, date(year, 1, 1), date(year, 12, 31), f"{year}")
    kind, number = period[:1], period[1:]
    if not number.isdigit():
        raise ValueError(f"Unknown report period: {period!r}")
    if kind == "q" and 1 <= int(number) <= 4:
        first = 3 * int(number) - 2
        last = first + 2
        return ReportPeriod(
            year, period, date(year, first, 1), date(year, last, monthrange(year, last)[1]), f"{year}-Q{number}"
        )
    if kind == "m" and 1 <= int(number) <= 12:
        month = int(number)
        return ReportPeriod(
            year, period, date(year, month, 1), date(year, month, monthrange(year, month)[1]), f"{year}-{month:02d}"
        )
    raise ValueError(f"Unknown report period: {period!r}")


def quarter_of(day: date) -> ReportPeriod:
    return report_period(day.year, f"q{(day.month - 1) // 3 + 1}")


@dataclass(frozen=True)
class ReportTotals:
    invoices: int
    net_cents: int
    tax_cents: int
    total_cents: int

    @property
    def net(self) -> Decimal:
        return from_cents(self.net_cents)

    @property
    def tax(self) -> Decimal:
        return from_cents(self.tax_cents)

    @property
    def total(self) -> Decimal:
        return from_cents(self.total_cents)


@dataclass(frozen=True)
class ReportTaxRow(ReportTotals):
    treatment: str
    country: str
    rate: Decimal

    @property
    def treatment_label(self) -> str:
        return dict(TAX_TREATMENTS).get(self.treatment, self.treatment)

    @property
    def country_name(self) -> str:
        return PAYER_COUNTRY_NAMES.get(self.country, self.country)


#: The kind of customer, told from the tax ID the invoice carries (there is no «company» flag): a Spanish tax ID
#: of a legal person or any tax ID from abroad is a company; a Spanish one of a natural person (DNI or NIE) is a
#: self-employed person or an individual with a tax ID; no tax ID, an individual.
CUSTOMER_KINDS = {
    "company": gettext_lazy("Company"),
    "self_employed": gettext_lazy("Self-employed or individual with a Spanish tax ID"),
    "individual": gettext_lazy("Individual without a tax ID"),
}


@dataclass(frozen=True)
class ReportCustomerRow(ReportTotals):
    kind: str

    @property
    def label(self) -> str:
        return CUSTOMER_KINDS[self.kind]


@dataclass(frozen=True)
class BillingReport:
    period: ReportPeriod
    invoices: ReportTotals
    credit_notes: ReportTotals
    net: ReportTotals
    by_tax: list[ReportTaxRow]
    by_customer: list[ReportCustomerRow]
    #: Collected in the period but not issued yet (being issued, or rejected by the platform hub): not counted.
    not_issued: list[str]


def customer_kind(country: str, tax_id: str) -> str:
    nif = normalise_nif(tax_id)
    if not nif:
        return "individual"
    if (country or "").upper() in ("", "ES"):
        if nif.startswith("ES") and is_spanish_tax_id(nif[2:]):
            nif = nif[2:]
        return "company" if is_legal_person_nif(nif) else "self_employed"
    return "company"


def _period_invoices(period: ReportPeriod):
    return Invoice.objects.filter(
        issued_on__gte=period.start, issued_on__lte=period.end, payment_status=Invoice.PaymentStatus.PAID
    )


def report_invoices(period: ReportPeriod):
    """The invoices the report counts: collected and issued, with their issue date in the period."""
    return _period_invoices(period).filter(fiscal_status__in=ISSUED_STATUSES).order_by("issued_on", "series", "sequence")


def _totals(row: dict | None) -> ReportTotals:
    row = row or {}
    return ReportTotals(
        invoices=row.get("invoices", 0),
        net_cents=int(row.get("net") or 0),
        tax_cents=int(row.get("tax") or 0),
        total_cents=int(row.get("total") or 0),
    )


_REPORT_SUMS = {"net": Sum("net_cents"), "tax": Sum("tax_cents"), "total": Sum("total_cents")}


def billing_report(period: ReportPeriod) -> BillingReport:
    counted = report_invoices(period).order_by()
    per_kind = {row["kind"]: row for row in counted.values("kind").annotate(invoices=Count("id"), **_REPORT_SUMS)}
    invoices = _totals(per_kind.get(Invoice.Kind.INVOICE))
    credit_notes = _totals(per_kind.get(Invoice.Kind.CREDIT_NOTE))
    net = ReportTotals(
        invoices=invoices.invoices + credit_notes.invoices,
        net_cents=invoices.net_cents + credit_notes.net_cents,
        tax_cents=invoices.tax_cents + credit_notes.tax_cents,
        total_cents=invoices.total_cents + credit_notes.total_cents,
    )
    # As the platform hub received each line: one without its own treatment carries the invoice's.
    lines = (
        InvoiceLine.objects.filter(invoice__in=counted)
        .annotate(
            treatment=Coalesce(NullIf("tax_treatment", Value("")), "invoice__tax_treatment"),
            country=F("invoice__payer_country"),
        )
        .values("treatment", "country", "tax_rate")
        .annotate(invoices=Count("invoice", distinct=True), **_REPORT_SUMS)
        .order_by()
    )
    order = [code for code, _label in TAX_TREATMENTS]
    by_tax = sorted(
        (
            ReportTaxRow(**vars(_totals(row)), treatment=row["treatment"], country=row["country"], rate=row["tax_rate"])
            for row in lines
        ),
        key=lambda row: (order.index(row.treatment) if row.treatment in order else len(order), row.country, row.rate),
    )
    per_customer = {kind: [0, 0, 0, 0] for kind in CUSTOMER_KINDS}
    for country, tax_id, net_cents, tax_cents, total_cents in counted.values_list(
        "payer_country", "payer_tax_id", "net_cents", "tax_cents", "total_cents"
    ):
        sums = per_customer[customer_kind(country, tax_id)]
        sums[0] += 1
        sums[1] += net_cents
        sums[2] += tax_cents
        sums[3] += total_cents
    by_customer = [ReportCustomerRow(*sums, kind=kind) for kind, sums in per_customer.items()]
    not_issued = list(
        _period_invoices(period)
        .exclude(fiscal_status__in=ISSUED_STATUSES)
        .order_by("issued_on", "series", "sequence")
        .values_list("number", flat=True)
    )
    return BillingReport(period, invoices, credit_notes, net, by_tax, by_customer, not_issued)


def billing_report_csv(period: ReportPeriod, language: str) -> dict:
    """The report's «Download Excel»: one row per invoice it counts."""
    return invoices_csv(
        report_invoices(period),
        columns=REPORT_CSV_COLUMNS,
        language=language,
        filename=f"erplora-invoices-{period.key}.csv",
    )
