"""``manage.py sweep_unpaid``: the safety net of unpaid plans and deleted businesses. Every business in dunning is
replayed with its oldest open invoice, the suspended ones age, a deleted business stops paying, the payers of deleted
accounts go, and a mail of the unpaid episode that could not leave is sent again."""

import logging
from collections import Counter

from django.db import transaction
from django.db.models import Q

from billing import stripe_service
from billing.models import PaymentFailure
from billing.services import departed_payers, invoice_webhooks, live_subscriptions, stripe_sales, unpaid_notices
from billing.stripe_keys import StripeKeyMode
from hubs.services import suspensions
from hubs.models import BillingProfile, Hub, Subscription

logger = logging.getLogger("billing.services")


#: The counts a sweep reports; ``errors`` makes the run fail after its whole pass (``task_failed``).
SWEEP_COUNTS = (
    "checked",
    "suspended",
    "cancelled",
    "payers_forgotten",
    "notified",
    "mail_failed",
    "errors",
    # The clock of the suspended businesses (``hubs.services.suspensions.age_suspended``).
    "warned",
    "final_notice",
    "expired",
    "undated",
)
#: Businesses whose unpaid plan the sweep looks at: still running (a suspended one already is).
SWEPT_STATUSES = [Hub.Status.PREPARING, Hub.Status.ACTIVE, Hub.Status.PAST_DUE]


def sweep_unpaid() -> Counter:
    """One pass of ``sweep_unpaid``: every business in dunning still running is replayed with its
    OLDEST open invoice through ``invoice_payment_failed`` (the live subscription decides; ``unpaid`` at once,
    else past the grace; one suspension), and the Stripe subscription of every deleted business is
    cancelled now. One business never stops the others; Stripe missing or failing for one is an error."""
    counts = Counter({key: 0 for key in SWEEP_COUNTS})
    configured = stripe_service.key_mode() is not StripeKeyMode.UNKNOWN
    counts.update(_replay_those_in_dunning(configured))
    # The businesses suspended too long: the notices of day 30 and 150 and the deletion
    # on day 180, which the next step ends in Stripe in this same pass.
    counts.update(suspensions.age_suspended())
    counts.update(_end_the_deleted(configured))
    counts.update(_forget_the_departed())
    counts.update(_tell_the_untold())
    return counts


def _replay_those_in_dunning(configured: bool) -> Counter:
    """Every business in dunning still running, decided again with its oldest open invoice."""
    counts = Counter()
    owed = (
        Subscription.objects.filter(
            status__in=stripe_sales.DUNNING_STATUSES, hub__status__in=SWEPT_STATUSES
        )
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in owed:
        counts["checked"] += 1
        if not configured:
            logger.error(
                "[UNPAID SWEEP] Stripe is not configured: %s is not swept",
                subscription.stripe_subscription_id,
            )
            counts["errors"] += 1
            continue
        try:
            invoices = stripe_service.open_invoices(subscription.stripe_subscription_id)
            if invoices:
                invoice_webhooks.invoice_payment_failed(
                    min(invoices, key=lambda invoice: invoice.get("created") or 0),
                    replay=True,
                )
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception(
                "[UNPAID SWEEP] %s could not be swept",
                subscription.stripe_subscription_id,
            )
            counts["errors"] += 1
            continue
        if Hub.objects.filter(
            pk=subscription.hub_id, status=Hub.Status.SUSPENDED
        ).exists():
            counts["suspended"] += 1
    return counts


def _end_the_deleted(configured: bool) -> Counter:
    """The billing of every business that was deleted, ended in Stripe."""
    counts = Counter()
    # Asked at deletion (``hubs.business.delete``), whatever the business is now: recovered on Free, too.
    deleted = (
        Subscription.objects.filter(cancel_requested_at__isnull=False)
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in deleted:
        if not configured:
            logger.error(
                "[UNPAID SWEEP] Stripe is not configured: deleted hub %s still pays",
                subscription.hub_id,
            )
            counts["errors"] += 1
            continue
        try:
            _end_billing_of_deleted(subscription)
        except Exception:  # noqa: BLE001 - kept for the next run, which fails until it goes through
            logger.exception(
                "[UNPAID SWEEP] The billing of deleted hub %s could not be ended",
                subscription.hub_id,
            )
            counts["errors"] += 1
            continue
        counts["cancelled"] += 1
    return counts


def _end_billing_of_deleted(subscription: Subscription) -> None:
    """A deleted business stops paying now (``test_hub_delete_cancels_billing``): a subscription Stripe no
    longer has counts as ended; any other failure keeps it for the next run."""
    try:
        stripe_service.cancel_subscription(subscription.stripe_subscription_id)
    except stripe_service.StripeRefused as refused:
        if refused.code != "resource_missing":
            raise
    logger.info(
        "[UNPAID SWEEP] Ended %s of deleted hub %s",
        subscription.stripe_subscription_id,
        subscription.hub_id,
    )
    with transaction.atomic():
        live_subscriptions.apply_state(subscription.hub, live_subscriptions.ended_state(subscription.hub))


def _forget_the_departed() -> Counter:
    """The payers of deleted accounts, once nothing more can be charged to them."""
    counts = Counter()
    departed = BillingProfile.objects.filter(forget_after__isnull=False).order_by("pk").values_list("pk", flat=True)
    for profile_id in list(departed):
        try:
            outcome = departed_payers.forget_departed_payer(profile_id)
        except Exception:  # noqa: BLE001 - one payer never stops the pass; it is retried on the next one
            logger.exception("[UNPAID SWEEP] The payer %s of a deleted account could not be forgotten", profile_id)
            counts["errors"] += 1
            continue
        if outcome == departed_payers.PAYER_FORGOTTEN:
            counts["payers_forgotten"] += 1
    return counts


def _tell_the_untold() -> Counter:
    """The mails of an unpaid episode that could not leave, sent again."""
    counts = Counter()
    untold = (
        PaymentFailure.objects.filter(resolved_at__isnull=True)
        .filter(
            Q(hub__status=Hub.Status.PAST_DUE, notified_at__isnull=True)
            | Q(hub__status=Hub.Status.SUSPENDED, suspension_notified_at__isnull=True)
        )
        .values_list("hub_id", flat=True)
        .distinct()
    )
    for hub_id in sorted(set(untold)):
        try:
            outcome = unpaid_notices.notify_unpaid(hub_id)
        except Exception:  # noqa: BLE001 - one business never stops the pass
            logger.exception("[UNPAID SWEEP] The payer of hub %s could not be told", hub_id)
            outcome = unpaid_notices.MAIL_NOT_SENT
        if outcome == unpaid_notices.NOTIFIED:
            counts["notified"] += 1
        elif outcome == unpaid_notices.MAIL_NOT_SENT:
            counts["mail_failed"] += 1
    return counts
