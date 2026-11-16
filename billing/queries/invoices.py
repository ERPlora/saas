"""ERPlora's invoices to an account, ``billing.invoice.{list,get,pdf,csv}``, and the CSV writer the admin's
billing report shares."""

import csv
import io
import logging
from datetime import date
from decimal import Decimal

from django.db.models import Q, Subquery
from django.db.models.functions import Coalesce, TruncDate
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import NotFound, OperationError, Unauthorized
from live.operations import AI, INTERNAL, operation

from billing.models import Invoice, PaymentFailure
from billing.money import from_cents
from billing.schemas import (
    InvoiceByIdIn,
    InvoiceDetailOut,
    InvoiceFileOut,
    InvoiceFilterIn,
    InvoiceListIn,
    InvoiceListOut,
)
from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import HubMember


logger = logging.getLogger("billing.queries")


# --- The Billing section: ERPlora's invoices, the subscriptions and the payment details -----------------
#
# Who sees an invoice: the account that paid it (its payer that day) and the current owner of its business
# (the owner manages billing); nobody else, whatever their role: a 404, never a hint. The same
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
    """The Stripe invoices whose payment the bank declined with the card still unchanged."""
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
    ai=AI(
        description="ERPlora's invoices to this account, newest first, by business, payment status, year and number.",
        asks={
            "en": ("show my invoices", "which is my latest invoice?", "which invoices are unpaid?"),
            "es": (
                "enséñame mis últimas facturas",
                "¿tengo alguna factura sin pagar?",
                "facturas de 2026 de la peluquería",
            ),
        },
    ),
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
    ai=AI(
        description="One invoice of ERPlora to this account with its lines and amounts.",
        asks={
            "en": ("open invoice ERP-2026-0042", "what's on my last invoice?", "show me the details of October's bill"),
            "es": (
                "ábreme la factura ERP-2026-0042",
                "¿qué me cobrasteis en la última factura?",
                "detalle de la factura de octubre",
            ),
        },
    ),
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
                "discount_cents": line.discount_cents,
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
    ai=INTERNAL,  # file
)
def invoice_pdf(ctx: OperationContext, data: InvoiceByIdIn) -> dict:
    """The PDF of an invoice, as ERPlora's platform hub issued it (``GET /internal/platform/invoices/{id}/pdf``,
    asked on demand). 404 ``billing.invoice_not_issued`` until the Hub issued it."""
    user = _billing_account(ctx)
    invoice = invoice_of(user, data.id)
    return {"filename": f"{invoice.number}.pdf", "content_type": "application/pdf", "content": platform_invoice_pdf(invoice)}


def platform_invoice_pdf(invoice: Invoice) -> bytes:
    """The PDF ERPlora's platform hub issued of ``invoice``, asked now (also the admin's): 404
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
    """A text cell that cannot run as a formula in the accountant's spreadsheet."""
    return f"'{value}" if value.startswith(FORMULA_STARTS) else value


def _csv_amount(cents: int, separator: str) -> str:
    return f"{from_cents(cents):.2f}".replace(".", separator)


def _csv_rate(rate: Decimal, separator: str) -> str:
    return f"{rate:.2f}".replace(".", separator)


def _invoice_csv_columns() -> dict:
    """Every column an invoice export can carry: its header and how an invoice fills its cell (given the language's
    decimal separator). Built under the export's language, so the headers come out translated."""
    return {
        "number": (_("Invoice"), lambda invoice, sep: _csv_text(invoice.number or invoice.stripe_number)),
        "date": (_("Date"), lambda invoice, sep: _date_of(invoice).isoformat()),
        "business": (_("Business"), lambda invoice, sep: _csv_text(invoice.business_name)),
        "payer": (_("Payer"), lambda invoice, sep: _csv_text(invoice.payer_name)),
        "tax_id": (_("Tax ID"), lambda invoice, sep: _csv_text(invoice.payer_tax_id)),
        "country": (_("Country"), lambda invoice, sep: _csv_text(invoice.payer_country)),
        "treatment": (_("Tax treatment"), lambda invoice, sep: _csv_text(str(invoice.get_tax_treatment_display()))),
        "rate": (_("VAT %"), lambda invoice, sep: _csv_rate(invoice.tax_rate, sep)),
        "net": (_("Tax base"), lambda invoice, sep: _csv_amount(invoice.net_cents, sep)),
        "tax": (_("VAT"), lambda invoice, sep: _csv_amount(invoice.tax_cents, sep)),
        "total": (_("Total"), lambda invoice, sep: _csv_amount(invoice.total_cents, sep)),
        "currency": (_("Currency"), lambda invoice, sep: _csv_text(invoice.currency)),
        "payment": (_("Payment"), lambda invoice, sep: _csv_text(str(Invoice.PaymentStatus(invoice.payment_status).label))),
        "status": (_("Status"), lambda invoice, sep: _csv_text(str(Invoice.FiscalStatus(invoice.fiscal_status).label))),
    }


#: The panel's «Download Excel».
ACCOUNT_CSV_COLUMNS = ("number", "date", "business", "net", "tax", "total", "currency", "payment", "status")
#: The admin's billing report: the panel's columns plus what the accountant needs for forms 303, 349 and 369.
REPORT_CSV_COLUMNS = ("number", "date", "business", "payer", "tax_id", "country", "treatment", "rate", "net", "tax",
                      "total", "currency", "payment", "status")


def rows_csv(rows, columns, *, language: str, filename: str) -> dict:
    """``rows`` as CSV for Excel, one line each; ``columns()`` gives the ``(header, cell)`` of each column and is
    called under ``language``, so the headers come out translated.

    UTF-8 with its BOM, so Excel reads the accents; in a language that writes a decimal comma (Spanish) the
    columns are split by «;» and the amounts carry the comma, as Excel expects there; elsewhere «,» and «.».
    Dates in ISO (Excel reads them in every language)."""
    with translation.override(language):
        separator = formats.get_format("DECIMAL_SEPARATOR", lang=language)
        chosen = columns()
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";" if separator == "," else ",")
        writer.writerow([header for header, _cell in chosen])
        for row in rows:
            writer.writerow([cell(row, separator) for _header, cell in chosen])
    return {
        "filename": filename,
        "content_type": "text/csv; charset=utf-8",
        "content": ("\ufeff" + buffer.getvalue()).encode("utf-8"),
    }


def invoices_csv(invoices, *, columns: tuple[str, ...], language: str, filename: str) -> dict:
    """The invoices as CSV for the accountant's Excel, with the ``columns`` of ``_invoice_csv_columns``."""
    return rows_csv(
        invoices.iterator(),
        lambda: [_invoice_csv_columns()[column] for column in columns],
        language=language,
        filename=filename,
    )


@operation(
    "billing.invoice.csv",
    kind="query",
    permission="billing.view",
    input=InvoiceFilterIn,
    output=InvoiceFileOut,
    expose_api=True,
    ai=INTERNAL,  # file
)
def invoice_csv(ctx: OperationContext, data: InvoiceFilterIn) -> dict:
    """«Download Excel»: the invoices the filters show, all of them, as CSV for the accountant."""
    user = _billing_account(ctx)
    return invoices_csv(
        _filtered_invoices(user, data),
        columns=ACCOUNT_CSV_COLUMNS,
        language=ctx.language,
        filename=f"erplora-invoices-{timezone.localdate().isoformat()}.csv",
    )
