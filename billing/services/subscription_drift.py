"""``manage.py sync_subscriptions``: every subscription Stripe still bills is read again from Stripe, and what drifted
from erplora.com is written as a lost webhook would have."""

import logging
from collections import Counter

from django.db import transaction

from billing import stripe_service
from billing.services import downgrades, live_subscriptions, stripe_sync
from hubs.models import Subscription, SubscriptionItem

logger = logging.getLogger("billing.services")


#: The counts of a pass; ``missing`` and ``errors`` make the run fail after it (``task_failed``).
SYNC_COUNTS = ("checked", "in_sync", "fixed", "drifted", "pending", "missing", "errors")
#: What the log names when a subscription drifted (``hubs.subscription.apply`` decides what is written).
DRIFT_FIELDS = (
    "plan",
    "billing_interval",
    "status",
    "stripe_subscription_id",
    "current_period_start",
    "current_period_end",
    "cancel_at_period_end",
    "trial_start",
    "trial_end",
)


def _drift(subscription: Subscription, state: dict) -> list[str]:
    """The fields where what Stripe says (``state``) and what erplora.com holds differ, bought modules too."""
    held = {field: getattr(subscription, field) for field in DRIFT_FIELDS if field != "plan"}
    held["plan"] = subscription.plan.slug
    fields = [field for field in DRIFT_FIELDS if field in state and state[field] != held[field]]
    bought = {
        (item.module_slug, item.valid_until)
        for item in subscription.items.filter(source=SubscriptionItem.Source.PURCHASE)
    }
    if {(right.module_slug, right.valid_until) for right in state["modules"]} != bought:
        fields.append("modules")
    return fields


def sync_subscription(subscription: Subscription, *, apply: bool = True) -> str:
    """Read the business's subscription from Stripe and write what it says, as a lost
    ``customer.subscription.updated`` would have (``live_state``), under the business's lock.
    ``in_sync`` · ``fixed`` · ``drifted`` (``apply=False``: nothing written) · ``pending`` (its first payment is
    not done) · ``missing`` (Stripe does not know it: left as it is, for the team). Stripe not answering raises
    (``stripe_service.StripeUnavailable``)."""
    hub = subscription.hub
    with stripe_sync.holding(hub.id):
        # Read inside the lock, as the webhook does: nothing changes the business between reading and writing.
        try:
            live = stripe_service.retrieve_subscription(subscription.stripe_subscription_id)
        except stripe_service.StripeRefused as refused:
            if refused.code != "resource_missing":
                raise
            logger.error(
                "[BILLING] Stripe does not know subscription %s of hub %s",
                subscription.stripe_subscription_id,
                hub.id,
                extra={"event": "billing.subscription_missing", "hub_id": str(hub.id)},
            )
            return "missing"
        if live.get("status") in ("incomplete", ""):
            return "pending"
        held = Subscription.objects.select_related("plan").get(pk=subscription.pk)
        state = live_subscriptions.live_state(hub, live)
        fields = _drift(held, state)
        changed = live_subscriptions.apply_state(hub, state)
        if not apply:
            # Everything the reading wrote (a card noted as changed included) goes back.
            transaction.set_rollback(True)
        elif changed:
            downgrades._forget_applied_change(hub.id, live)
    if not changed:
        return "in_sync"
    logger.warning(
        "[BILLING] Subscription %s of hub %s drifted from Stripe: %s",
        subscription.stripe_subscription_id,
        hub.id,
        ", ".join(fields) or "its standing",
        extra={"event": "billing.subscription_drift", "hub_id": str(hub.id), "fields": fields},
    )
    return "fixed" if apply else "drifted"


def sync_subscriptions(*, apply: bool = True) -> Counter:
    """One pass of ``manage.py sync_subscriptions``: every subscription Stripe still bills (with its id), one at a
    time; one business never stops the others."""
    counts = Counter({key: 0 for key in SYNC_COUNTS})
    for subscription in (
        Subscription.objects.exclude(stripe_subscription_id="").select_related("hub").order_by("pk")
    ):
        counts["checked"] += 1
        try:
            counts[sync_subscription(subscription, apply=apply)] += 1
        except Exception:  # noqa: BLE001 - one business never stops the pass; the next one reads it again
            logger.exception(
                "[BILLING] Subscription %s could not be read from Stripe",
                subscription.stripe_subscription_id,
                extra={"event": "billing.sync_failed", "hub_id": str(subscription.hub_id)},
            )
            counts["errors"] += 1
    return counts
