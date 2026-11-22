"""ERPlora's invoices recorded from Stripe: a paid Stripe invoice numbered and issued, an unpaid one listed
without a number, and one Stripe voided."""

import logging
from functools import partial
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.operations import INTERNAL, operation

from billing import events, queries, stripe_service, vat, vat_breakdown, vat_countries, vies
from billing.models import Invoice, InvoiceLine, VatCheck
from billing.money import from_cents, to_cents
from billing.schemas.invoice_records import InvoiceRecordIn, InvoiceRecordOut
from billing.services import (
    invoice_discounts,
    invoice_events,
    invoice_numbering,
    invoice_sealing,
    oss_notices,
    plan_changes,
    platform_invoices,
    rectifying_invoices,
    vat_clearance,
)
from hubs.services import hub_callbacks
from hubs.models import Hub

logger = logging.getLogger("billing.services")

# The Stripe receipt is not the legal invoice. A paid Stripe invoice becomes ERPlora's ``Invoice`` in the
# webhook's transaction (the row is what makes it durable), numbered here and issued by ERPlora's platform
# hub, which chains it in VeriFactu (``post_platform_invoice``, after the COMMIT). An unpaid one is listed
# without a number («Not collected», «Pay»); a credit note is a rectifying invoice of its own series.


def _with_all_lines(invoice: dict) -> dict:
    """The Stripe invoice with every line in ``lines.data`` (the event embeds only the first ones)."""
    lines = stripe_service.invoice_lines(invoice)
    return {**invoice, "lines": {"object": "list", "data": lines, "has_more": False}}


class VatProofUnavailable(Exception):
    """VIES could not answer and no verdict on file says how the payer's VAT number stood when it was charged:
    the invoice waits (the webhook answers 500 and Stripe retries) rather than guess."""


def _payer_clearance(hub: Hub, charged_at: datetime) -> tuple[bool, str]:
    """Whether the payer's VAT number grants the reverse charge on a sale charged at ``charged_at``, and the
    VIES consultation number that proves it. Asked before the business is locked (VIES may take seconds).

    Judged as of the charge: the last verdict VIES gave until then decides, even one older
    than the 30 days a SALE trusts (the proof travels with the invoice; a later outage of VIES cannot turn a
    verified intra-EU B2B sale into a Spanish one). With no verdict before the charge, VIES is asked now; if it
    cannot answer, ``VatProofUnavailable``: never Spanish VAT because VIES was down. Only a number of ANOTHER
    member state is ever judged: a national or a non-EU one cannot be reverse charged."""
    profile = hub.billing_profile
    if profile is None or not profile.tax_id:
        return False, ""
    country = (profile.billing_country or "").strip().upper()
    issuer = vat_clearance._issuer_country()
    value = vies.with_country_prefix(profile.tax_id, country, issuer_country=issuer)
    if (
        not value
        or country == issuer
        or country not in vat_countries.EU_VAT_RATES
        or vies.is_uk_vat_number(value)
        or vies.is_domestic_vat_number(value, issuer_country=issuer, customer_country=country)
    ):
        return False, ""
    verdict = queries.vat_verdict_as_of(value, charged_at)
    if verdict is not None:
        if verdict.status == VatCheck.VERIFIED:
            return True, verdict.consultation_number
        return False, ""
    clearance = vat_clearance.clear_tax_id_for_stripe(value, customer_country=country)
    if clearance.verified:
        return True, (clearance.check.consultation_number if clearance.check is not None else "")
    if clearance.status == vat_clearance.CLEARANCE_INVALID:
        return False, ""
    logger.error(
        "[INVOICE] VIES cannot answer about %s and nothing on file proves it: the invoice of hub %s waits",
        value, hub.id, extra={"event": "billing.invoice_waits_for_vies"},
    )
    raise VatProofUnavailable(value)


def _payer_snapshot(hub: Hub, *, verified: bool, consultation: str) -> dict:
    """The payer as it is today (``hubs.BillingProfile``), copied onto the invoice: an edit of the profile
    never rewrites an issued invoice."""
    profile = hub.billing_profile
    if profile is None:
        return {"payer_name": "", "language": hub.language or settings.LANGUAGE_CODE}
    owner = profile.owner
    country = (profile.billing_country or "").strip().upper()
    tax_id = vies.normalise(profile.tax_id)
    return {
        "billing_profile": profile,
        "payer_account": owner,
        "payer_name": profile.billing_name or (owner.get_full_name() if owner else "") or "",
        "payer_tax_id": tax_id,
        "payer_tax_id_type": vat_countries.tax_id_type_for(country) if tax_id else "",
        "payer_tax_id_verified": verified,
        "vat_consultation_number": consultation if verified else "",
        "payer_address": profile.billing_address or "",
        "payer_city": profile.billing_city or "",
        "payer_postal_code": (profile.billing_postal_code or "").strip().upper(),
        "payer_country": country,
        "payer_email": profile.billing_email or (owner.email if owner else ""),
        "language": (getattr(owner, "language", "") or hub.language or settings.LANGUAGE_CODE),
    }


@operation(
    "billing.invoice.record",
    kind="command",
    permission="billing.manage",
    input=InvoiceRecordIn,
    output=InvoiceRecordOut,
    ai=INTERNAL,  # platform
)
def invoice_record(ctx: OperationContext, data: InvoiceRecordIn) -> dict:
    """The webhook's door to ERPlora's invoices (the platform only; no route): a Stripe invoice of a
    business, ``open`` (listed, not collected), ``paid`` (numbered and issued) or ``void`` (Stripe gave up).
    Idempotent by the Stripe invoice: a paid one is never recorded twice, nor reopened."""
    hub = Hub.objects.select_related("billing_profile__owner").get(pk=data.hub_id)
    stripe_invoice = data.invoice
    existing = (
        Invoice.objects.select_for_update()
        .filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice.get("id") or "")
        .first()
    )
    if data.status == "void":
        return _void(ctx, existing)
    if existing is not None and existing.payment_status == Invoice.PaymentStatus.PAID:
        return invoice_sealing._record_out(existing, "duplicate")
    total = int(stripe_invoice.get("total") or 0)
    if total < 0 and data.status == "paid":
        return rectifying_invoices._record_negative(ctx, hub, stripe_invoice)
    if total <= 0 and not invoice_discounts.is_fully_discounted(stripe_invoice):
        return invoice_sealing._record_out(existing, "ignored")
    if data.status == "open":
        return _record_open(ctx, hub, stripe_invoice, existing)
    return _record_paid(ctx, hub, data, existing)


def _stripe_fields(stripe_invoice: dict) -> dict:
    return {
        "stripe_number": (stripe_invoice.get("number") or "")[:64],
        "hosted_invoice_url": stripe_invoice.get("hosted_invoice_url") or "",
        "billed_at": invoice_sealing._moment_or_none(stripe_invoice.get("created")),
        "currency": (stripe_invoice.get("currency") or "eur").upper(),
    }


def _record_open(ctx, hub: Hub, stripe_invoice: dict, existing: Invoice | None) -> dict:
    """An unpaid Stripe invoice, listed with what it asks (no number: one is given at the payment)."""
    if existing is not None:
        if existing.payment_status == Invoice.PaymentStatus.OPEN:
            Invoice.objects.filter(pk=existing.pk).update(
                hosted_invoice_url=stripe_invoice.get("hosted_invoice_url") or existing.hosted_invoice_url,
                updated_at=timezone.now(),
            )
        return invoice_sealing._record_out(existing, "duplicate")
    total = int(stripe_invoice["total"])
    tax = plan_changes.tax_cents_of(stripe_invoice)
    profile = hub.billing_profile
    listed = Invoice.objects.create(
        kind=Invoice.Kind.INVOICE,
        hub=hub,
        business_name=hub.name,
        billing_profile=profile,
        payer_account=profile.owner if profile else None,
        stripe_invoice_id=stripe_invoice["id"],
        payment_status=Invoice.PaymentStatus.OPEN,
        net_cents=total - tax,
        tax_cents=tax,
        total_cents=total,
        **_stripe_fields(stripe_invoice),
    )
    invoice_events._record_invoice_event(ctx, listed, events.INVOICE_RECORDED,
                          {"id": str(listed.id), "hub_id": str(hub.id), "payment_status": "open"})
    return invoice_sealing._record_out(listed, "listed")


def _void(ctx, existing: Invoice | None) -> dict:
    """Stripe voided (or gave up on) an unpaid invoice: it leaves «not collected». A paid one never changes."""
    if existing is None or existing.payment_status != Invoice.PaymentStatus.OPEN:
        return invoice_sealing._record_out(existing, "ignored")
    Invoice.objects.filter(pk=existing.pk).update(payment_status=Invoice.PaymentStatus.VOID, updated_at=timezone.now())
    invoice_events._record_invoice_event(ctx, existing, events.INVOICE_VOIDED, {"id": str(existing.id), "hub_id": str(existing.hub_id)})
    existing.payment_status = Invoice.PaymentStatus.VOID
    return invoice_sealing._record_out(existing, "voided")


def _sealed_line(position: int, line: dict, breakdown: vat_breakdown.VatBreakdown) -> InvoiceLine:
    """A Stripe line as a line of ERPlora's invoice: what it sells, its discount and its base, rate and quota sealed."""
    kind, slug, category = invoice_sealing._item_of(invoice_sealing._price_of(line))
    amount, discount = invoice_discounts.line_amounts(line)
    rate, net, tax = invoice_sealing._sealed_amounts(
        amount,
        invoice_sealing._line_tax_cents(line),
        treatment=breakdown.treatment,
        rate=invoice_sealing._nominal_rate(breakdown, category) if breakdown.is_subject else Decimal("0.00"),
        reconciled=breakdown.vat_included_reconciled,
    )
    period = line.get("period") or {}
    return InvoiceLine(
        position=position,
        description=(line.get("description") or slug or _("Subscription"))[:255],
        item_kind=kind,
        item_slug=slug,
        quantity=max(int(line.get("quantity") or 1), 1),
        proration=invoice_sealing._is_proration(line),
        period_start=invoice_sealing._moment_or_none(period.get("start")),
        period_end=invoice_sealing._moment_or_none(period.get("end")),
        tax_category_id=category,
        tax_treatment=breakdown.treatment,
        tax_rate=rate,
        net_cents=net,
        tax_cents=tax,
        total_cents=net + tax,
        discount_cents=discount,
        stripe_line_id=line.get("id") or "",
    )


def _record_paid(ctx, hub: Hub, data: InvoiceRecordIn, existing: Invoice | None) -> dict:
    """A paid Stripe invoice becomes ERPlora's invoice: the payer sealed, the qualification of the sale and
    each line's base, rate and quota sealed, the next number of the series; issued after the COMMIT."""
    stripe_invoice = data.invoice
    total = int(stripe_invoice["total"])
    payer = queries.payer_of(hub)
    breakdown = vat.resolve_vat(
        from_cents(total),
        customer_country=payer.country,
        customer_postal_code=payer.postal_code,
        customer_tax_id=payer.tax_id,
        customer_tax_id_type=payer.tax_id_type,
        customer_tax_id_verified=data.tax_id_verified,
        category_key=vat.SAAS_SUBSCRIPTION_CATEGORY,
        tax_cents=plan_changes.tax_cents_of(stripe_invoice),
        tax_included=False,
    )
    lines = [
        _sealed_line(position, line, breakdown)
        for position, line in enumerate((stripe_invoice.get("lines") or {}).get("data") or [], start=1)
    ]
    if not lines:
        # Stripe always bills a line; without one the whole amount is one line of the subscription.
        lines.append(
            InvoiceLine(
                position=1,
                description=_("Subscription"),
                tax_category_id=vat.SAAS_SUBSCRIPTION_CATEGORY,
                tax_treatment=breakdown.treatment,
                tax_rate=breakdown.rate,
                net_cents=to_cents(breakdown.base),
                tax_cents=to_cents(breakdown.tax),
                total_cents=total,
            )
        )
    net_cents = sum(line.net_cents for line in lines)
    tax_cents = sum(line.tax_cents for line in lines)
    invoice_sealing._require_adds_up(stripe_invoice.get("id"), net_cents + tax_cents, total, hub.id)
    now = timezone.now()
    series, sequence, number, today = invoice_numbering.issue_number(Invoice.Kind.INVOICE)
    values = {
        "kind": Invoice.Kind.INVOICE,
        "hub": hub,
        "business_name": hub.name,
        "stripe_invoice_id": stripe_invoice["id"],
        **_stripe_fields(stripe_invoice),
        **_payer_snapshot(hub, verified=data.tax_id_verified, consultation=data.vat_consultation_number),
        "series": series,
        "sequence": sequence,
        "number": number,
        "issued_on": today,
        "payment_status": Invoice.PaymentStatus.PAID,
        "paid_at": invoice_sealing._moment_or_none((stripe_invoice.get("status_transitions") or {}).get("paid_at")) or now,
        "net_cents": net_cents,
        "tax_cents": tax_cents,
        "total_cents": net_cents + tax_cents,
        "tax_treatment": breakdown.treatment,
        "tax_country": breakdown.tax_country,
        "tax_rate": invoice_sealing._nominal_rate(breakdown, vat.SAAS_SUBSCRIPTION_CATEGORY) if breakdown.is_subject else Decimal("0.00"),
        "vat_included_reconciled": breakdown.vat_included_reconciled,
        "fiscal_status": Invoice.FiscalStatus.ISSUING,
        "fiscal_status_at": now,
        "next_post_at": now,
    }
    if existing is None:
        invoice = Invoice.objects.create(**values)
    else:
        invoice = existing
        for field, value in values.items():
            setattr(invoice, field, value)
        invoice.save()
        invoice.lines.all().delete()
    for line in lines:
        line.invoice = invoice
    InvoiceLine.objects.bulk_create(lines)
    invoice_events._record_invoice_event(ctx, invoice, events.INVOICE_RECORDED,
                          {"id": str(invoice.id), "hub_id": str(hub.id), "payment_status": "paid"})
    transaction.on_commit(partial(platform_invoices._post_quietly, invoice.id), robust=True)
    oss_notices._note_oss_threshold_quietly(invoice)
    return invoice_sealing._record_out(invoice, "numbered")


def invoice_voided(stripe_invoice: dict) -> str:
    """Stripe voided an unpaid invoice, or gave up on it (``marked_uncollectible``): it leaves «not collected»
    (it is no longer payable). An invoice ERPlora does not list is ignored."""
    listed = (
        Invoice.objects.filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice.get("id") or "")
        .values_list("hub_id", "payment_status")
        .first()
    )
    if listed is None or listed[1] != Invoice.PaymentStatus.OPEN or listed[0] is None:
        return "ignored"
    out = invoice_record(
        hub_callbacks.system_ctx_for(listed[0]), InvoiceRecordIn(hub_id=listed[0], invoice=stripe_invoice, status="void")
    )
    return "processed" if out.outcome == "voided" else "ignored"
