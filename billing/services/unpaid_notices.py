"""The payer told of an unpaid invoice: each one once while the business still works, and the suspension once."""

import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from billing.models import Invoice, PaymentFailure
from billing.services import stripe_customers, stripe_sales, stripe_sync
from hubs.models import Hub

logger = logging.getLogger("billing.services")


NOTIFIED, NOTHING_TO_TELL, MAIL_NOT_SENT = "notified", "nothing", "mail_failed"


def notify_unpaid(hub_id) -> str:
    """Tell the payer of ``hub_id`` what its unpaid episode owes them: each unpaid
    invoice once, while the business still works (how much, until when, where to pay); the suspension once,
    which also stands for the invoices not told yet. The business is locked, so two deliveries never send the
    same mail twice. Nobody to tell is done too; a mail that cannot leave stays owed (``MAIL_NOT_SENT``)."""
    from billing import emails

    with stripe_sync.holding(hub_id):
        hub = Hub.objects.select_related("billing_profile__owner").get(pk=hub_id)
        owed = list(PaymentFailure.objects.filter(hub=hub, resolved_at__isnull=True).order_by("invoice_created_at"))
        suspended = hub.status == Hub.Status.SUSPENDED
        if suspended:
            to_tell = [] if any(f.suspension_notified_at for f in owed) else owed
        else:
            to_tell = [f for f in owed if f.notified_at is None] if hub.status == Hub.Status.PAST_DUE else []
        if not to_tell:
            return NOTHING_TO_TELL
        to, language = _unpaid_recipient(hub)
        now = timezone.now()
        try:
            if to and suspended:
                emails.send_business_suspended(
                    hub, to=to, language=language, amount=sum((_owed_amount(f) for f in owed), Decimal(0))
                )
            elif to:
                for failure in to_tell:
                    emails.send_payment_failed(
                        hub,
                        to=to,
                        language=language,
                        amount=_owed_amount(failure),
                        declined=failure.reason == PaymentFailure.Reason.CARD_DECLINED,
                        suspends_on=failure.invoice_created_at + stripe_sales.UNPAID_PLAN_GRACE,
                    )
                    PaymentFailure.objects.filter(pk=failure.pk).update(notified_at=now)
        except emails.MailNotSent:
            return MAIL_NOT_SENT
        if not to:
            logger.warning("[UNPAID] Hub %s owes an invoice and has nobody to tell", hub.id)
        if suspended:
            PaymentFailure.objects.filter(pk__in=[f.pk for f in owed]).update(
                suspension_notified_at=now, notified_at=Coalesce("notified_at", Value(now))
            )
        return NOTIFIED


def _unpaid_recipient(hub: Hub) -> tuple[str, str]:
    """Who hears of the unpaid invoice: the payer's address for invoices, else the payer's own (the owner's
    when the business has no payer yet), in the payer's language."""
    profile = hub.billing_profile
    account = (profile.owner if profile is not None else None) or stripe_customers._owner_of(hub)
    to = (profile.billing_email if profile is not None else "") or (account.email if account else "")
    return to, getattr(account, "language", "") or hub.language or settings.LANGUAGE_CODE


def _owed_amount(failure: PaymentFailure) -> Decimal:
    """What the unpaid invoice asks for, as Billing lists it («Not collected»)."""
    listed = Invoice.objects.filter(stripe_invoice_id=failure.stripe_invoice_id).first()
    return listed.total if listed is not None else Decimal(0)


def _notify_quietly(hub_id) -> None:
    try:
        notify_unpaid(hub_id)
    except Exception:  # noqa: BLE001 - a mail never undoes the dunning; sweep_unpaid sends it again
        logger.exception("[UNPAID] The payer of hub %s could not be told", hub_id)
