"""Rectifying invoices: a credit note, a refund or a negative Stripe invoice rectifies the invoice ERPlora
issued, in its own series."""

import logging
from functools import partial
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.operations import INTERNAL, operation

from billing import events, stripe_service
from billing.models import Invoice, InvoiceLine
from billing.schemas import CreditNoteRecordIn, InvoiceRecordOut, RefundRecordIn
from billing.services import invoice_events, invoice_numbering, invoice_sealing, plan_changes, platform_invoices
from hubs.models import Hub

logger = logging.getLogger("billing.services")


class RectifiedInvoiceMissing(Exception):
    """A credit note, a refund or a negative invoice whose invoice ERPlora has not recorded (yet): Stripe does not
    order its events, so the webhook answers 500 and Stripe retries."""


def rectification_type(reason: str | None) -> str:
    """VeriFactu's type of a rectifying invoice for Stripe's reason: a refund, a duplicate, a price change or an
    order change modify the base (art. 80.1, 80.2 LIVA, or an error): R1; a fraudulent charge, R4 (other)."""
    return Invoice.RectificationType.R4 if reason == "fraudulent" else Invoice.RectificationType.R1


def _rectifying_lines(original: Invoice, items: list[dict]) -> list[InvoiceLine]:
    """The lines of a rectifying invoice, negative where they give money back, sealed with the qualification of
    the invoice they rectify (a rectifying invoice keeps it) and the rate of the line they correct. ``items``:
    ``{amount, tax, description, quantity, price, stripe_line_id, split}``; ``split`` = the amount has the VAT
    inside (a refund): it is taken out at that rate."""
    sources = list(original.lines.all())
    lines = []
    for position, item in enumerate(items, start=1):
        kind, slug, category = invoice_sealing._item_of(item.get("price") or "")
        source = next((line for line in sources if line.stripe_line_id and line.stripe_line_id == item.get("source_line")), None)
        source = source or next((line for line in sources if slug and line.item_slug == slug), None)
        rate, net, tax = invoice_sealing._sealed_amounts(
            item["amount"],
            item["tax"],
            treatment=original.tax_treatment,
            rate=source.tax_rate if source is not None else original.tax_rate,
            reconciled=item.get("split", False) or (original.vat_included_reconciled and not item["tax"]),
        )
        lines.append(
            InvoiceLine(
                position=position,
                description=(item.get("description") or (source.description if source else "") or _("Credit"))[:255],
                item_kind=source.item_kind if source else kind,
                item_slug=source.item_slug if source else slug,
                quantity=max(int(item.get("quantity") or 1), 1),
                proration=bool(item.get("proration")),
                period_start=item.get("period_start") or (source.period_start if source else None),
                period_end=item.get("period_end") or (source.period_end if source else None),
                tax_category_id=source.tax_category_id if source else category,
                tax_treatment=original.tax_treatment,
                tax_rate=rate,
                net_cents=net,
                tax_cents=tax,
                total_cents=net + tax,
                stripe_line_id=item.get("stripe_line_id") or "",
            )
        )
    return lines


def _rectify(ctx, original: Invoice, *, source_id: str, items: list[dict], expected_total: int, rtype: str,  # noqa: PLR0913
             reason: str, stripe_number: str = "", billed_at: datetime | None = None) -> dict:
    """A rectifying invoice of ``original`` (``ERPR`` series, its qualification and recipient), once per Stripe
    ``source_id``; its lines must add up to what Stripe gave back, or nothing is invoiced. Issued after the
    COMMIT."""
    existing = Invoice.objects.filter(kind=Invoice.Kind.CREDIT_NOTE, stripe_source_id=source_id).first()
    if existing is not None:
        return invoice_sealing._record_out(existing, "duplicate")
    lines = _rectifying_lines(original, items)
    net_cents = sum(line.net_cents for line in lines)
    tax_cents = sum(line.tax_cents for line in lines)
    invoice_sealing._require_adds_up(source_id, net_cents + tax_cents, expected_total, original.hub_id)
    now = timezone.now()
    series, sequence, number, today = invoice_numbering.issue_number(Invoice.Kind.CREDIT_NOTE)
    copied = {
        field: getattr(original, field)
        for field in (
            "hub_id", "business_name", "billing_profile_id", "payer_account_id", "payer_name", "payer_tax_id",
            "payer_tax_id_type", "payer_tax_id_verified", "vat_consultation_number", "payer_address", "payer_city",
            "payer_postal_code", "payer_country", "payer_email", "language", "currency", "tax_treatment",
            "tax_country", "tax_rate", "stripe_invoice_id",
        )
    }
    rectifying = Invoice.objects.create(
        kind=Invoice.Kind.CREDIT_NOTE,
        rectifies=original,
        stripe_source_id=source_id,
        stripe_number=(stripe_number or "")[:64],
        billed_at=billed_at,
        rectification_type=rtype,
        rectification_reason=(reason or "")[:255],
        series=series,
        sequence=sequence,
        number=number,
        issued_on=today,
        payment_status=Invoice.PaymentStatus.PAID,
        paid_at=now,
        net_cents=net_cents,
        tax_cents=tax_cents,
        total_cents=net_cents + tax_cents,
        fiscal_status=Invoice.FiscalStatus.ISSUING,
        fiscal_status_at=now,
        next_post_at=now,
        **copied,
    )
    for line in lines:
        line.invoice = rectifying
    InvoiceLine.objects.bulk_create(lines)
    invoice_events._record_invoice_event(ctx, rectifying, events.CREDIT_NOTE_RECORDED, {"id": str(rectifying.id),
                                                                         "rectifies": str(original.id)})
    transaction.on_commit(partial(platform_invoices._post_quietly, rectifying.id), robust=True)
    return invoice_sealing._record_out(rectifying, "numbered")


def _stripe_items(stripe_lines: list[dict], *, sign: int) -> list[dict]:
    """Stripe's lines (of an invoice or a credit note) as the items of a rectifying invoice; ``sign`` -1 for a
    credit note, whose amounts Stripe gives positive."""
    items = []
    for line in stripe_lines:
        period = line.get("period") or {}
        items.append(
            {
                "amount": sign * int(line.get("amount") or 0),
                "tax": sign * invoice_sealing._line_tax_cents(line),
                "description": line.get("description") or "",
                "quantity": line.get("quantity") or 1,
                "price": invoice_sealing._price_of(line),
                "proration": invoice_sealing._is_proration(line),
                "period_start": invoice_sealing._moment_or_none(period.get("start")),
                "period_end": invoice_sealing._moment_or_none(period.get("end")),
                "source_line": line.get("invoice_line_item") or "",
                "stripe_line_id": line.get("id") or "",
            }
        )
    return items


def _record_negative(ctx, hub: Hub, stripe_invoice: dict) -> dict:
    """A Stripe invoice of a negative total (a proration credit larger than what it bills; legacy or manual:
    downgrades wait for the end of the period) rectifies the invoice whose period its credited lines belong to
    R1, a modification of the price (art. 80.2 LIVA)."""
    lines = (stripe_invoice.get("lines") or {}).get("data") or []
    credited = [
        invoice_sealing._moment_or_none((line.get("period") or {}).get("start"))
        for line in lines
        if int(line.get("amount") or 0) < 0
    ]
    moment = min((when for when in credited if when is not None), default=None)
    found = (
        InvoiceLine.objects.select_related("invoice")
        .filter(
            invoice__hub=hub,
            invoice__kind=Invoice.Kind.INVOICE,
            invoice__payment_status=Invoice.PaymentStatus.PAID,
            period_start__lte=moment,
            period_end__gt=moment,
        )
        .order_by("-invoice__issued_on", "-invoice__sequence")
        .first()
        if moment is not None
        else None
    )
    if found is None:
        logger.error(
            "[INVOICE] Stripe invoice %s of hub %s credits a period ERPlora has not invoiced",
            stripe_invoice.get("id"), hub.id, extra={"event": "fiscal.credit.unknown_invoice"},
        )
        raise RectifiedInvoiceMissing(stripe_invoice.get("id"))
    return _rectify(
        ctx,
        found.invoice,
        source_id=stripe_invoice["id"],
        items=_stripe_items(lines, sign=1),
        expected_total=int(stripe_invoice["total"]),
        rtype=Invoice.RectificationType.R1,
        reason=stripe_invoice.get("description") or "proration",
        stripe_number=stripe_invoice.get("number") or "",
        billed_at=invoice_sealing._moment_or_none(stripe_invoice.get("created")),
    )


def _issued_invoice(stripe_invoice_id: str) -> Invoice | None:
    return (
        Invoice.objects.filter(
            kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice_id, payment_status=Invoice.PaymentStatus.PAID
        )
        .only("id", "hub_id", "payer_account_id")
        .first()
    )


def _missing_original(what: str, stripe_invoice_id: str):
    logger.error(
        "[INVOICE] %s rectifies Stripe invoice %s, which ERPlora has not invoiced (yet): Stripe retries",
        what, stripe_invoice_id, extra={"event": "fiscal.credit.unknown_invoice"},
    )
    return RectifiedInvoiceMissing(stripe_invoice_id)


def credit_note_created(credit_note: dict) -> str:
    """A credit note of a paid invoice (``credit_note.created``) becomes a rectifying invoice of its own series.
    Ahead of its invoice (Stripe does not order events) it raises: Stripe retries."""
    rectified = credit_note.get("invoice") or ""
    if isinstance(rectified, dict):
        rectified = rectified.get("id") or ""
    original = _issued_invoice(rectified)
    if original is None:
        raise _missing_original(f"Credit note {credit_note.get('id')}", rectified)
    # The event is a snapshot of when it was created: a note voided since (``credit_note.voided``, possible while its
    # invoice was open, when this event was still waiting for it) is no rectification, so it is read LIVE.
    if stripe_service.retrieve_credit_note(credit_note["id"]).get("status") == "void":
        logger.warning("[INVOICE] Credit note %s was voided in Stripe: no rectifying invoice", credit_note["id"])
        return "ignored"
    lines = stripe_service.credit_note_lines(credit_note)
    credit_note_record(
        invoice_events._invoice_ctx(original),
        CreditNoteRecordIn(credit_note={**credit_note, "lines": {"object": "list", "data": lines, "has_more": False}}),
    )
    return "processed"


def credit_note_voided(credit_note: dict) -> str:
    """A credit note voided in Stripe (``credit_note.voided``). Stripe voids one only while its invoice is
    OPEN, and a rectifying invoice is recorded here only for a PAID one, so normally there is none: ``voided``, and its
    ``credit_note.created`` never records it (read live there). Nothing fiscal is done on its own: a rectifying
    invoice recorded anyway is never modified (a record sent to the AEAT is corrected with a new one) and the team is
    told by mail to correct it by hand: ``needs_review``. A mail that cannot leave raises, so Stripe retries it."""
    from billing import emails

    rectifying = (
        Invoice.objects.filter(kind=Invoice.Kind.CREDIT_NOTE, stripe_source_id=credit_note.get("id") or "")
        .only("id", "number", "series", "sequence", "fiscal_status", "rectifies_id", "total_cents")
        .first()
    )
    if rectifying is None:
        logger.info("[INVOICE] Credit note %s voided in Stripe: it was never a rectifying invoice", credit_note.get("id"))
        return "voided"
    logger.error(
        "[INVOICE] Credit note %s voided in Stripe after it became rectifying invoice %s: correct it by hand",
        credit_note.get("id"), rectifying.number, extra={"event": "fiscal.credit.voided_after_rectifying"},
    )
    emails.send_credit_note_voided(rectifying, credit_note.get("id") or "")
    return "needs_review"


@operation(
    "billing.credit_note.record",
    kind="command",
    permission="billing.manage",
    input=CreditNoteRecordIn,
    output=InvoiceRecordOut,
    ai=INTERNAL,  # platform
)
def credit_note_record(ctx: OperationContext, data: CreditNoteRecordIn) -> dict:
    """A Stripe credit note as a rectifying invoice (the platform only; no route): negative amounts, the
    qualification and the payer of the invoice it rectifies, its type (``rectification_type``) and reason
    (the memo, or Stripe's reason); issued after the COMMIT. Idempotent by the credit note."""
    credit_note = data.credit_note
    rectified = credit_note.get("invoice") or ""
    if isinstance(rectified, dict):
        rectified = rectified.get("id") or ""
    original = (
        Invoice.objects.select_for_update()
        .filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=rectified, payment_status=Invoice.PaymentStatus.PAID)
        .first()
    )
    if original is None:
        raise _missing_original(f"Credit note {credit_note.get('id')}", rectified)
    lines = (credit_note.get("lines") or {}).get("data") or []
    items = _stripe_items(lines, sign=-1) or [
        {"amount": -(int(credit_note.get("total") or 0) - plan_changes.tax_cents_of(credit_note)), "tax": -plan_changes.tax_cents_of(credit_note)}
    ]
    return _rectify(
        ctx,
        original,
        source_id=credit_note["id"],
        items=items,
        expected_total=-int(credit_note.get("total") or 0),
        rtype=rectification_type(credit_note.get("reason")),
        reason=credit_note.get("memo") or credit_note.get("reason") or "credit_note",
        stripe_number=credit_note.get("number") or "",
        billed_at=invoice_sealing._moment_or_none(credit_note.get("created")),
    )


def charge_refunded(charge: dict) -> str:
    """Money given back without a credit note (``charge.refunded``; a refund in the Dashboard): each refund is a
    rectifying invoice of the invoice the charge paid, its gross split at that invoice's rate.
    A refund a credit note covers is that credit note's; one still pending waits for its next event; a charge
    that paid no invoice of Stripe is not ours."""
    intent = charge.get("payment_intent") or ""
    if isinstance(intent, dict):
        intent = intent.get("id") or ""
    stripe_invoice_id = stripe_service.invoice_paid_by(intent) if intent else None
    if not stripe_invoice_id:
        return "ignored"
    original = _issued_invoice(stripe_invoice_id)
    if original is None:
        raise _missing_original(f"Refund of charge {charge.get('id')}", stripe_invoice_id)
    covered = stripe_service.credit_note_refund_ids(stripe_invoice_id)
    for refund in stripe_service.charge_refunds(charge["id"]):
        if refund.get("status") != "succeeded" or refund["id"] in covered:
            continue
        refund_record(invoice_events._invoice_ctx(original), RefundRecordIn(invoice_id=original.id, refund=refund))
    return "processed"


@operation(
    "billing.refund.record",
    kind="command",
    permission="billing.manage",
    input=RefundRecordIn,
    output=InvoiceRecordOut,
    ai=INTERNAL,  # platform
)
def refund_record(ctx: OperationContext, data: RefundRecordIn) -> dict:
    """A Stripe refund without a credit note as a rectifying invoice of ``invoice_id`` (the platform only; no
    route): one line with the gross refunded, the VAT taken out at the invoice's rate. Idempotent by the refund."""
    original = Invoice.objects.select_for_update().get(pk=data.invoice_id)
    refund = data.refund
    amount = int(refund.get("amount") or 0)
    return _rectify(
        ctx,
        original,
        source_id=refund["id"],
        items=[{"amount": -amount, "tax": 0, "description": _("Refund"), "split": True}],
        expected_total=-amount,
        rtype=rectification_type(refund.get("reason")),
        reason=refund.get("reason") or "refund",
        billed_at=invoice_sealing._moment_or_none(refund.get("created")),
    )
