"""The team's notices of the OSS threshold: its crossing and its 80 % warning, once per year, mailed to the team."""

import logging
from collections import Counter
from functools import partial
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from billing import emails, queries, vat
from billing.models import Invoice, OssNotice
from billing.money import to_cents
from billing.oss import OSS_WARNING_PERCENT

logger = logging.getLogger("billing.services")


def _counts_towards_oss(invoice: Invoice, issuer: str) -> bool:
    """The rule of ``queries.cross_border_b2c_cents``: a paid invoice to a payer of another member state
    without a VIES-verified VAT number."""
    return (
        invoice.kind == Invoice.Kind.INVOICE
        and invoice.payment_status == Invoice.PaymentStatus.PAID
        and invoice.payer_country in vat.EU_VAT_RATES
        and invoice.payer_country != issuer
        and not invoice.payer_tax_id_verified
    )


def _oss_noticed(year: int, kinds) -> bool:
    return OssNotice.objects.filter(year=year, kind__in=kinds).exists()


def _write_oss_notice(year: int, kind: str, invoice: Invoice, **values) -> OssNotice | None:
    """The year's notice of ``kind``, or ``None`` when a concurrent charge wrote it first (it tells)."""
    try:
        with transaction.atomic():
            return OssNotice.objects.create(year=year, kind=kind, invoice=invoice, **values)
    except IntegrityError:
        return None


def note_oss_threshold(invoice: Invoice) -> list[OssNotice]:
    """After charging ``invoice``: the year's crossing of the OSS threshold and its 80 % warning, each once per
    year, mailed to the team after the COMMIT. The crossing first, so a sale that jumps past the threshold is
    told once (``crossed``), never «80 %» after the fact. Nothing under a voluntary OSS registration (there is
    nothing to prepare) nor for a sale that does not count towards the threshold."""
    policy = queries.fiscal_policy()
    issuer = (policy.issuer_country or vat.DEFAULT_ISSUER_COUNTRY).strip().upper()
    if policy.oss_registered or not _counts_towards_oss(invoice, issuer):
        return []
    year = invoice.issued_on.year
    threshold = to_cents(policy.oss_threshold)
    written = []
    if not _oss_noticed(year, [OssNotice.Kind.CROSSED]):
        previous = queries.cross_border_b2c_cents(policy, year - 1)
        if previous > threshold:
            crossing = {
                "reason": OssNotice.Reason.PREVIOUS_YEAR,
                "accumulated_cents": previous,
                "effective_from": date(year, 1, 1),
            }
        else:
            # The invoice is saved as paid already: the sum includes it.
            current = queries.cross_border_b2c_cents(policy, year)
            crossing = (
                {"reason": OssNotice.Reason.CURRENT_YEAR, "accumulated_cents": current, "effective_from": invoice.issued_on}
                if current > threshold
                else None
            )
        if crossing is not None:
            written.append(
                _write_oss_notice(year, OssNotice.Kind.CROSSED, invoice, threshold_cents=threshold, **crossing)
            )
    if not _oss_noticed(year, [OssNotice.Kind.NEAR, OssNotice.Kind.CROSSED]):
        current = queries.cross_border_b2c_cents(policy, year)
        if current * 100 > threshold * OSS_WARNING_PERCENT:
            written.append(
                _write_oss_notice(
                    year, OssNotice.Kind.NEAR, invoice, accumulated_cents=current, threshold_cents=threshold
                )
            )
    written = [notice for notice in written if notice is not None]
    for notice in written:
        logger.warning(
            "[FISCAL] OSS %s %s: %s of %s cents (invoice %s)",
            notice.kind,
            notice.year,
            notice.accumulated_cents,
            notice.threshold_cents,
            invoice.number,
            extra={"event": f"billing.oss_{notice.kind}", "year": notice.year, "reason": notice.reason},
        )
        transaction.on_commit(partial(send_oss_notice, notice.id), robust=True)
    return written


def _note_oss_threshold_quietly(invoice: Invoice) -> None:
    """Charging never breaks over the notice: a failure is an ERROR, and the next charged sale tries again."""
    try:
        with transaction.atomic():
            note_oss_threshold(invoice)
    except Exception:  # noqa: BLE001 - the invoice stands; the next counted charge notes the threshold again
        logger.exception(
            "[FISCAL] The OSS threshold could not be noted for invoice %s",
            invoice.number,
            extra={"event": "billing.oss_notice_failed", "invoice_id": str(invoice.id)},
        )


def send_oss_notice(notice_id) -> bool:
    """Mail one notice to the team's mailbox (``SUPPORT_EMAIL``) and mark it sent; ``False`` when it could not
    leave (it stays owed: the daily ``retax_subscriptions`` sends it again)."""
    notice = OssNotice.objects.select_related("invoice").filter(pk=notice_id, mailed_at__isnull=True).first()
    if notice is None:
        return True
    try:
        emails.send_oss_notice(notice)
    except emails.MailNotSent:
        return False
    OssNotice.objects.filter(pk=notice.pk, mailed_at__isnull=True).update(mailed_at=timezone.now())
    return True


def send_pending_oss_notices() -> Counter:
    """Every notice whose mail has not left yet, sent again: ``notices_sent`` and ``notices_failed``."""
    counts = Counter({"notices_sent": 0, "notices_failed": 0})
    for notice_id in OssNotice.objects.filter(mailed_at__isnull=True).order_by("recorded_at").values_list("pk", flat=True):
        counts["notices_sent" if send_oss_notice(notice_id) else "notices_failed"] += 1
    return counts
