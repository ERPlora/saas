"""A subscription changed or ended in Stripe, and a payer whose default card changed, from the webhook."""

from django.core.cache import cache

from billing import queries, stripe_service
from billing.services import live_subscriptions, stripe_sync, webhook_targets
from hubs.models import Subscription


def subscription_updated(obj: dict) -> str:
    """A subscription changed (plan, items, status, period, cancellation): the LIVE one is applied;
    Stripe not answering → the event as it came. The first event of a new subscription finds its business
    by the ``hub_id`` of its metadata, only if that business has no other subscription."""
    subscription_id = obj.get("id") or ""
    subscription = webhook_targets._local_subscription(subscription_id)
    hub = subscription.hub if subscription is not None else None
    if hub is None:
        named = webhook_targets._hub_named((obj.get("metadata") or {}).get("hub_id"))
        if (
            named is not None
            and not Subscription.objects.filter(hub=named)
            .exclude(stripe_subscription_id="")
            .exists()
        ):
            hub = named
    if hub is None:
        return "unknown"
    with stripe_sync.holding(hub.id):
        # Stripe not answering raises: the event's snapshot may be stale, and Stripe retries it.
        live = stripe_service.retrieve_subscription(subscription_id)
        if live.get("status") in ("incomplete", ""):
            return "pending"
        live_subscriptions.apply_live(hub.id, live)
    return "processed"


def subscription_deleted(obj: dict) -> str:
    """The subscription ended (a cancelled plan at its period's end, Stripe giving up, a deleted business):
    the business goes back to Free, its bought modules end, nothing is owed. Nothing new is
    opened in Stripe (no «maintenance» subscription any more)."""
    subscription = webhook_targets._local_subscription(obj.get("id") or "")
    if subscription is None:
        return "unknown"
    with stripe_sync.holding(subscription.hub_id):
        live_subscriptions.apply_state(subscription.hub, live_subscriptions.ended_state(subscription.hub))
    return "processed"


def customer_updated(customer: dict) -> str:
    """The payer's default card changed (the Customer Portal): a declined card's failure becomes
    ``card_changed``, and «Pay» works again. The card Billing shows
    (``billing.payment_method.get``) is read again from Stripe."""
    cache.delete(queries.card_cache_key(customer.get("id") or ""))
    method = (customer.get("invoice_settings") or {}).get("default_payment_method")
    if isinstance(method, dict):
        method = method.get("id")
    return (
        "processed"
        if method
        and live_subscriptions.mark_card_changed(stripe_customer_id=customer.get("id"), method=method)
        else "ignored"
    )
