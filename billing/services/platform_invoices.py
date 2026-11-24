"""ERPlora's platform hub issues the invoices: each one posted to it after the COMMIT, its fiscal status stored as
the hub answers it, the payer's mail once it is issued, and the pass that posts and asks again what is owed."""

import logging
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from functools import partial
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation

from billing import emails, events, platform_contract
from billing.models import Invoice
from billing.schemas.invoice_records import FiscalAnswerIn, FiscalAnswerOut
from billing.services import invoice_events
from hubs import hub_client
from hubs.services import exclusive_runs
from hubs.hub_client import HubRefused, HubUnavailable

logger = logging.getLogger("billing.services")


#: What one post of an invoice came to: answered (its status stored), the Hub away (retried), the Hub
#: refusing it (kept with its code, retried: the run fails), or nothing to post (not paid).
POSTED, UNREACHABLE, REFUSED, NOTHING_TO_POST = "posted", "unreachable", "refused", "nothing_to_post"
#: The statuses the platform hub answers (``Invoice.FiscalStatus`` without «not issued»).
PLATFORM_STATUSES = frozenset({"issuing", "issued", "accepted", "accepted_with_errors", "rejected"})
#: Issued by the platform hub: it has the QR and the PDF.
ISSUED_STATUSES = frozenset({"issued", "accepted", "accepted_with_errors"})
#: The wait before posting again an invoice the Hub did not take: one ``reconcile_platform_invoices`` run
#: (15 minutes) after the first failure, doubling, never more than 6 hours.
PLATFORM_FIRST_WAIT = timedelta(minutes=15)
PLATFORM_LONGEST_WAIT = timedelta(hours=6)
#: An invoice still «issuing» after this long is stuck: the reconcile run fails (the ``task_failed`` alarm).
PLATFORM_STUCK_AFTER = timedelta(hours=1)


def platform_backoff(attempts: int) -> timedelta:
    """How long an invoice waits after its ``attempts``-th failed post."""
    return min(PLATFORM_FIRST_WAIT * 2 ** max(attempts - 1, 0), PLATFORM_LONGEST_WAIT)


def platform_payload(invoice: Invoice) -> dict:
    """The body of ``POST /internal/platform/invoices``: the whole invoice, so the platform hub issues it in
    VeriFactu and prints its PDF without asking the SaaS anything. Keyed by ``id`` (idempotent)."""
    rectified = invoice.rectifies
    return {
        "id": str(invoice.id),
        "kind": invoice.kind,
        "series": invoice.series,
        "number": invoice.number,
        "issued_on": platform_contract.day(invoice.issued_on),
        "stripe_invoice_id": invoice.stripe_invoice_id,
        "stripe_source_id": invoice.stripe_source_id,
        "rectification": (
            {"type": invoice.rectification_type, "reason": invoice.rectification_reason}
            if invoice.kind == Invoice.Kind.CREDIT_NOTE
            else None
        ),
        "currency": invoice.currency,
        "language": invoice.language,
        "net_cents": invoice.net_cents,
        "tax_cents": invoice.tax_cents,
        "total_cents": invoice.total_cents,
        "tax_treatment": invoice.tax_treatment,
        "tax_country": invoice.tax_country,
        "tax_rate": str(invoice.tax_rate),
        "vat_included_reconciled": invoice.vat_included_reconciled,
        "vat_included_because_unverified": invoice.vat_included_because_unverified,
        "business": {"id": str(invoice.hub_id) if invoice.hub_id else None, "name": invoice.business_name},
        "recipient": {
            "name": invoice.payer_name,
            "tax_id": invoice.payer_tax_id,
            "tax_id_type": invoice.payer_tax_id_type,
            "tax_id_verified": invoice.payer_tax_id_verified,
            "vat_consultation_number": invoice.vat_consultation_number,
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
                "period_start": platform_contract.day(line.period_start),
                "period_end": platform_contract.day(line.period_end),
                "tax_category": line.tax_category_id,
                "tax_treatment": line.tax_treatment or invoice.tax_treatment,
                "tax_rate": str(line.tax_rate),
                "net_cents": line.net_cents,
                "tax_cents": line.tax_cents,
                "total_cents": line.total_cents,
                "discount_cents": line.discount_cents,
            }
            for line in invoice.lines.order_by("position")
        ],
        "rectifies": (
            {"id": str(rectified.id), "number": rectified.number, "issued_on": platform_contract.day(rectified.issued_on)}
            if rectified is not None
            else None
        ),
    }


def _answer_of(body) -> dict | None:
    """The platform hub's answer as ``FiscalAnswerIn``, or ``None`` for one the SaaS does not know."""
    body = body if isinstance(body, dict) else {}
    status = body.get("status")
    if status not in PLATFORM_STATUSES:
        return None
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return {
        "status": status,
        "qr": str(body.get("qr") or ""),
        "error_code": str(error.get("code") or "")[:64],
        "error": str(error.get("message") or ""),
    }


def post_platform_invoice(invoice_id) -> str:
    """Post a paid invoice to ERPlora's platform hub (``POST /internal/platform/invoices``) and store what
    it answers. Outside any transaction (a call to the Hub never holds the database). Idempotent on the
    Hub's side by the invoice's id: posting it again answers what it has."""
    invoice = Invoice.objects.select_related("rectifies").filter(pk=invoice_id).first()
    if invoice is None or invoice.payment_status != Invoice.PaymentStatus.PAID or not invoice.number:
        return NOTHING_TO_POST
    try:
        answer = hub_client.post_platform_invoice(platform_payload(invoice))
    except HubUnavailable as failed:
        _post_failed(invoice, str(failed))
        return UNREACHABLE
    except HubRefused as refused:
        logger.error(
            "[INVOICE] The platform hub refused invoice %s: %s", invoice.number, refused,
            extra={"event": "billing.platform_invoice_refused", "code": refused.code},
        )
        _post_failed(invoice, str(refused), code=refused.code, message=refused.message)
        return REFUSED
    known = _answer_of(answer.body)
    if known is None:
        logger.error("[INVOICE] The platform hub answered %r for invoice %s", answer.body, invoice.number)
        _post_failed(invoice, f"unknown answer: {answer.body!r}"[:255])
        return UNREACHABLE
    Invoice.objects.filter(pk=invoice.pk).update(
        post_attempts=F("post_attempts") + 1, next_post_at=None, last_post_error=""
    )
    invoice_apply_fiscal_status(invoice_events._invoice_ctx(invoice), FiscalAnswerIn(id=invoice.id, **known))
    return POSTED


def _post_failed(invoice: Invoice, error: str, *, code: str = "", message: str = "") -> None:
    attempts = invoice.post_attempts + 1
    logger.warning("[INVOICE] Invoice %s owed to the platform hub (attempt %s): %s", invoice.number, attempts, error)
    fields = {
        "post_attempts": attempts,
        "last_post_error": error[:255],
        "next_post_at": timezone.now() + platform_backoff(attempts),
        "updated_at": timezone.now(),
    }
    if code:
        fields.update(fiscal_error_code=code[:64], fiscal_error=message)
    Invoice.objects.filter(pk=invoice.pk).update(**fields)


def refresh_platform_invoice(invoice_id) -> str:
    """Ask the platform hub how an issued invoice stands (``GET /internal/platform/invoices/{id}``): the AEAT
    accepts or rejects it after the Hub issued it. Returns its fiscal status now, or ``unreachable`` /
    ``refused``."""
    invoice = Invoice.objects.filter(pk=invoice_id).first()
    if invoice is None:
        return NOTHING_TO_POST
    try:
        answer = hub_client.get_platform_invoice(str(invoice.id))
    except HubUnavailable:
        return UNREACHABLE
    except HubRefused as refused:
        logger.error("[INVOICE] The platform hub does not know invoice %s: %s", invoice.number, refused)
        return REFUSED
    known = _answer_of(answer.body)
    if known is None:
        logger.warning("[INVOICE] The platform hub answered %r for invoice %s", answer.body, invoice.number)
        return invoice.fiscal_status
    return invoice_apply_fiscal_status(invoice_events._invoice_ctx(invoice), FiscalAnswerIn(id=invoice.id, **known)).fiscal_status


@operation(
    "billing.invoice.apply_fiscal_status",
    kind="command",
    permission="billing.manage",
    input=FiscalAnswerIn,
    output=FiscalAnswerOut,
    ai=INTERNAL,  # platform
)
def invoice_apply_fiscal_status(ctx: OperationContext, data: FiscalAnswerIn) -> dict:
    """What the platform hub says of an invoice, stored as it says it (the platform only; no route). «Issuing»
    never moves an invoice back; a rejection is an ERROR for support (the Hub corrects it with a new record,
    and its next answer replaces this one). The first time it is issued, its payer gets an e-mail."""
    invoice = Invoice.objects.select_for_update().get(pk=data.id)
    status = invoice.fiscal_status if data.status == "issuing" else data.status
    fields = {"fiscal_status": status, "qr": data.qr or invoice.qr, "fiscal_error_code": data.error_code,
              "fiscal_error": data.error}
    changed = any(getattr(invoice, field) != value for field, value in fields.items())
    if not changed:
        return {"id": invoice.id, "fiscal_status": invoice.fiscal_status, "changed": False}
    first_issue = invoice.fiscal_status not in ISSUED_STATUSES and status in ISSUED_STATUSES
    now = timezone.now()
    Invoice.objects.filter(pk=invoice.pk).update(**fields, fiscal_status_at=now, updated_at=now)
    if status == Invoice.FiscalStatus.REJECTED:
        logger.error(
            "[INVOICE] The AEAT rejected invoice %s: %s %s", invoice.number, data.error_code, data.error,
            extra={"event": "billing.platform_invoice_rejected", "invoice": invoice.number},
        )
    invoice_events._record_invoice_event(ctx, invoice, events.INVOICE_FISCAL_STATUS_CHANGED, {"id": str(invoice.id), "status": status})
    if first_issue and invoice.emailed_at is None:
        transaction.on_commit(partial(_email_quietly, invoice.id), robust=True)
    return {"id": invoice.id, "fiscal_status": status, "changed": True}


def _post_quietly(invoice_id) -> None:
    try:
        post_platform_invoice(invoice_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the invoice; it stays «issuing»
        logger.exception("[INVOICE] Posting invoice %s to the platform hub crashed", invoice_id)


#: What sending the payer's mail of an invoice came to.
MAILED, MAIL_SKIPPED, MAIL_FAILED = "mailed", "mail_skipped", "mail_failed"


def send_invoice_mail(invoice_id) -> str:
    """Send the payer the mail of an issued invoice, with its PDF attached (``billing.emails``), and mark it sent.
    Nothing to send (nobody to send it to) is done too; a mail that cannot leave, also for want of its PDF, stays
    owed for ``reconcile_platform_invoices``."""
    invoice = Invoice.objects.select_related("hub", "payer_account").get(pk=invoice_id)
    try:
        sent = emails.send_invoice_issued(invoice)
    except emails.MailNotSent:
        return MAIL_FAILED
    Invoice.objects.filter(pk=invoice_id).update(emailed_at=timezone.now())
    return MAILED if sent else MAIL_SKIPPED


def _email_quietly(invoice_id) -> None:
    try:
        send_invoice_mail(invoice_id)
    except Exception:  # noqa: BLE001 - a mail never undoes the invoice; the reconcile run sends it again
        logger.exception("[INVOICE] The e-mail of invoice %s could not be sent", invoice_id)


#: The counts of a ``reconcile_platform_invoices`` run; the failing ones make it exit with an error.
PLATFORM_COUNTS = (
    "posted", "accepted", "waiting", "mailed", "unreachable", "refused", "rejected", "stuck", "mail_failed", "errors",
    "cut_short",
)
PLATFORM_FAILING = ("unreachable", "refused", "rejected", "stuck", "mail_failed", "errors")
#: What the status of an invoice asked about counts as; any other one is accepted.
ASKED_COUNTS = {
    UNREACHABLE: "unreachable",
    REFUSED: "refused",
    Invoice.FiscalStatus.REJECTED: "rejected",
    Invoice.FiscalStatus.ISSUED: "waiting",
}


def reconcile_platform_invoices(now: datetime | None = None, go_on: Callable[[], bool] | None = None) -> Counter:
    """One pass of ``reconcile_platform_invoices`` (the ``saas-worker``, every 15 minutes): post again every
    «issuing» invoice whose wait passed, ask the platform hub about every issued (or rejected) one until the AEAT
    accepts it, and count the ones «issuing» for longer than ``PLATFORM_STUCK_AFTER``. One invoice never stops the
    others. ``go_on`` (the worker's stop request and the round's time budget) is asked before each call to the Hub
    or mail: once it says no, the pass ends after the invoice in course (``cut_short`` 1, the rest in the next pass);
    the count of the stuck ones is always made."""
    now = now or timezone.now()
    counts = Counter({key: 0 for key in PLATFORM_COUNTS})
    paid = Invoice.objects.filter(payment_status=Invoice.PaymentStatus.PAID).exclude(number="")
    due = (
        paid.filter(fiscal_status=Invoice.FiscalStatus.ISSUING)
        .filter(Q(next_post_at__isnull=True) | Q(next_post_at__lte=now))
        .order_by("series", "issued_on", "sequence")
        .values_list("id", flat=True)
    )
    for invoice_id in _until_cut_short(due, counts, go_on):
        outcome = _post_again(invoice_id)
        if outcome != NOTHING_TO_POST:
            counts[outcome] += 1
    asked = paid.filter(fiscal_status__in=[Invoice.FiscalStatus.ISSUED, Invoice.FiscalStatus.REJECTED]).values_list(
        "id", flat=True
    )
    for invoice_id in _until_cut_short(asked, counts, go_on):
        counts[_ask_again(invoice_id)] += 1
    counts["stuck"] = paid.filter(
        fiscal_status=Invoice.FiscalStatus.ISSUING, fiscal_status_at__lte=now - PLATFORM_STUCK_AFTER
    ).count()
    unmailed = paid.filter(fiscal_status__in=ISSUED_STATUSES, emailed_at__isnull=True).values_list("id", flat=True)
    for invoice_id in _until_cut_short(unmailed, counts, go_on):
        outcome = send_invoice_mail(invoice_id)
        if outcome == MAIL_FAILED:
            counts["mail_failed"] += 1
        elif outcome == MAILED:
            counts["mailed"] += 1
    return counts


def _until_cut_short(invoice_ids: Iterable, counts: Counter, go_on: Callable[[], bool] | None) -> Iterator:
    """Each invoice of a step of the pass, ``go_on`` asked before it; none once the pass is cut short."""
    if counts["cut_short"]:
        return
    for invoice_id in list(invoice_ids):
        if go_on is not None and not go_on():
            counts["cut_short"] = 1
            return
        yield invoice_id


def _post_again(invoice_id) -> str:
    try:
        return post_platform_invoice(invoice_id)
    except Exception:  # noqa: BLE001 - one invoice never stops the pass; it stays owed
        logger.exception("[INVOICE] Posting invoice %s crashed", invoice_id)
        return "errors"


def _ask_again(invoice_id) -> str:
    try:
        status = refresh_platform_invoice(invoice_id)
    except Exception:  # noqa: BLE001 - one invoice never stops the pass
        logger.exception("[INVOICE] Asking about invoice %s crashed", invoice_id)
        return "errors"
    return ASKED_COUNTS.get(status, "accepted")


def platform_run_failed(counts: Counter) -> bool:
    return any(counts[key] for key in PLATFORM_FAILING)


def reconcile_platform_invoices_exclusively(go_on: Callable[[], bool] | None = None) -> Counter | None:
    """One pass of ``reconcile_platform_invoices`` under its lock: its counts, or ``None`` when another run holds the
    lock (and this one did nothing). What the command and the ``saas-worker`` (every 15 minutes, ``base.worker``,
    with its ``go_on``) both run."""
    with exclusive_runs.run_exclusively("reconcile_platform_invoices") as mine:
        return reconcile_platform_invoices(go_on=go_on) if mine else None
