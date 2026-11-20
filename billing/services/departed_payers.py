"""The payer of an account that deleted itself goes with the account, once nothing can be charged to it any more."""

import logging
from datetime import datetime
from functools import partial

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from billing import stripe_service
from billing.models import Invoice
from billing.services import invoice_recording
from hubs.models import BillingProfile, Hub, Subscription

logger = logging.getLogger("billing.services")


# GDPR art. 17: the payer record (``hubs.BillingProfile``) and its Stripe customer go with the account; the
# invoices ERPlora issued keep their own copy of the payer (Commercial Code art. 30, General Tax Law art. 66),
# which is what the law asks to keep (art. 17(3)(b)). Only what can still be charged holds the payer, because
# the invoice issued at that payment must name it: a subscription Stripe still bills, or an invoice not paid
# yet, which waits at most ``PAYER_RETENTION`` and is then voided in Stripe, as Stripe advises for a deletion
# request (docs.stripe.com/privacy/deletion-requests).

#: How long the payer of a deleted account waits for an invoice still unpaid: the 90 days a deleted business
#: is kept (``Hub.RETENTION``). On that day (``forget_after``) what is unpaid is voided and the payer goes.
PAYER_RETENTION = Hub.RETENTION
PAYER_FORGOTTEN = "forgotten"
PAYER_HELD = "held"


def payer_leaving(sender, user_id, **kwargs) -> None:
    """``accounts.signals.account_deleting``: each payer of the account gets its purge date and goes after the
    COMMIT, unless something can still be charged to it (``forget_departed_payer``; ``sweep_unpaid`` finishes).

    A live subscription only holds it here in a business that was deleted, which ``sweep_unpaid`` cancels on its
    next pass. A business still alive never does: whoever still pays for it (``hubs.queries.payers.still_pays``) can
    neither delete its account (409 ``accounts.pays_businesses``) nor be taken out of it (409 ``hubs.member_pays``)."""
    profile_ids = list(BillingProfile.objects.filter(owner_id=user_id).values_list("pk", flat=True))
    if not profile_ids:
        return
    now = timezone.now()
    BillingProfile.objects.filter(pk__in=profile_ids).update(forget_after=now + PAYER_RETENTION, updated_at=now)
    transaction.on_commit(partial(_forget_payers_quietly, profile_ids), robust=True)


def _forget_payers_quietly(profile_ids) -> None:
    for profile_id in profile_ids:
        try:
            forget_departed_payer(profile_id)
        except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the deletion; sweep_unpaid retries
            logger.exception("[PAYER] The payer %s of a deleted account could not be forgotten yet", profile_id)


def forget_departed_payer(profile_id, now: datetime | None = None) -> str:
    """Forget the payer of a deleted account (``forget_after`` set) once nothing can be charged to it any more:
    no subscription Stripe still bills for its businesses, and no invoice of it unpaid (from its purge date,
    those are voided in Stripe first). Its Stripe customer is deleted, its businesses stop naming it and the
    record goes. ``PAYER_HELD`` while something holds it; a Stripe failure raises (the sweep counts it)."""
    now = now or timezone.now()
    profile = BillingProfile.objects.filter(pk=profile_id, forget_after__isnull=False).first()
    if profile is None:
        return PAYER_FORGOTTEN
    if Subscription.objects.filter(hub__billing_profile=profile).exclude(stripe_subscription_id="").exists():
        return PAYER_HELD
    unpaid = Invoice.objects.filter(
        Q(billing_profile=profile) | Q(hub__billing_profile=profile), payment_status=Invoice.PaymentStatus.OPEN
    )
    if unpaid.exists():
        if now < profile.forget_after:
            return PAYER_HELD
        for stripe_invoice_id in list(unpaid.values_list("stripe_invoice_id", flat=True)):
            invoice_recording.invoice_voided(stripe_service.void_invoice(stripe_invoice_id))
    if profile.stripe_customer_id:
        try:
            stripe_service.delete_customer(profile.stripe_customer_id)
        except stripe_service.StripeRefused as refused:
            if refused.code != "resource_missing":
                raise
    with transaction.atomic():
        Hub.objects.filter(billing_profile=profile).update(billing_profile=None, updated_at=now)
        profile.delete()
    logger.info("[PAYER] The payer %s of a deleted account is forgotten", profile_id)
    return PAYER_FORGOTTEN
