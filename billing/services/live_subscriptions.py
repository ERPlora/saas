"""What the live subscription says, applied to the business (webhook, operations, sweep), and the subscription as
an operation answers it."""

import logging
from functools import partial
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from billing import queries
from billing.models import PaymentFailure
from billing.services import downgrades, stripe_sales, stripe_sync, unpaid_notices
from billing.stripe_period import subscription_period
from hubs.queries import plan_catalog
from hubs.services import hub_callbacks, subscription_sync
from hubs.models import Hub, Subscription, SubscriptionItem
from hubs.schemas.subscriptions import ModuleRightIn, SubscriptionApplyIn

logger = logging.getLogger("billing.services")


def subscription_out(hub_id) -> dict:
    subscription = Subscription.objects.select_related("plan").get(hub_id=hub_id)
    return {
        "hub_id": hub_id,
        "plan": subscription.plan.slug,
        "billing_interval": subscription.billing_interval,
        "status": subscription.status,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "current_period_end": subscription.current_period_end,
        "trial_end": subscription.trial_end,
        "modules": [
            {
                "slug": item.module_slug,
                "source": item.source,
                "valid_until": item.valid_until,
            }
            for item in subscription.items.order_by("module_slug")
        ],
        "scheduled_change": queries.scheduled_change_of(hub_id),
    }


def unpaid_state(hub: Hub, live_status: str, now: datetime | None = None) -> dict:
    """The standing and the «why unpaid» of a business whose live subscription is ``live_status``: paid →
    good (its failures resolved); in dunning → grace for 7 days from the oldest unpaid invoice, then
    suspended (Stripe's ``unpaid`` at once); anything else leaves both as they are."""
    now = now or timezone.now()
    open_failures = PaymentFailure.objects.filter(hub=hub, resolved_at__isnull=True)
    if live_status in stripe_sales.PAID_STATUSES or live_status in stripe_sales.ENDED_STATUSES:
        open_failures.update(resolved_at=now)
        return {
            "standing": "good",
            "unpaid_reason": None,
            "unpaid_since": None,
            "unpaid_invoice_url": None,
        }
    if live_status not in stripe_sales.DUNNING_STATUSES:
        return {}
    oldest = open_failures.order_by("invoice_created_at").first()
    latest = open_failures.order_by("-failed_at").first()
    since = oldest.invoice_created_at if oldest else None
    overdue = since is not None and now - since > stripe_sales.UNPAID_PLAN_GRACE
    suspended = live_status == "unpaid" or overdue or hub.status == Hub.Status.SUSPENDED
    reason = PaymentFailure.Reason.PAYMENT_FAILED.value
    if latest is not None:
        reason = (
            "card_changed"
            if latest.reason == PaymentFailure.Reason.CARD_DECLINED
            and latest.card_changed_at
            else latest.reason
        )
    return {
        "standing": "suspended" if suspended else "grace",
        "unpaid_reason": reason,
        "unpaid_since": since,
        "unpaid_invoice_url": (latest.hosted_invoice_url or None) if latest else None,
    }


def live_state(hub: Hub, live: dict, now: datetime | None = None) -> dict:  # noqa: C901
    """``hubs.subscription.apply``'s fields for what the live subscription ``live`` says of ``hub``."""
    now = now or timezone.now()
    status = live.get("status") or ""
    if status in stripe_sales.ENDED_STATUSES:
        return ended_state(hub, now)
    start, end = subscription_period(live)
    period_end = stripe_sync._moment(end)
    cancelling = bool(live.get("cancel_at_period_end") or live.get("cancel_at"))
    plan, interval, rights, unknown = None, None, {}, False
    for line in stripe_sales._live_items(live):
        price_id = (line.get("price") or {}).get("id", "")
        if (found := queries.plan_for_price(price_id)) is not None:
            plan, interval = found
        elif (found := queries.module_for_price(price_id)) is not None:
            module, interval = found[0], interval or found[1]
            rights[module.slug] = ModuleRightIn(
                module_slug=module.slug,
                stripe_item_id=line["id"],
                valid_until=period_end if cancelling else None,
            )
        else:
            unknown = True
            logger.error(
                "[BILLING] Stripe bills hub %s a price nobody sells: %s",
                hub.id,
                price_id,
            )
    subscription = Subscription.objects.filter(hub=hub).first()
    for item in SubscriptionItem.objects.filter(
        subscription=subscription, source=SubscriptionItem.Source.PURCHASE
    ):
        if item.module_slug in rights or not item.is_live(now):
            continue
        # Cancelled (it left Stripe without proration) and paid until the end of its period.
        rights[item.module_slug] = ModuleRightIn(
            module_slug=item.module_slug,
            stripe_item_id="",
            valid_until=item.valid_until or period_end or now,
        )
    method = live.get("default_payment_method")
    if isinstance(method, dict):
        method = method.get("id")
    if method:
        # A card put on the subscription (the Customer Portal) after a decline: «Pay» works again.
        mark_card_changed(hub=hub, method=method)
    customer = live.get("customer")
    state = {
        "status": status,
        "stripe_customer_id": customer["id"]
        if isinstance(customer, dict)
        else customer or "",
        "stripe_subscription_id": live["id"],
        "current_period_start": stripe_sync._moment(start),
        "current_period_end": period_end,
        "cancel_at_period_end": cancelling,
        "modules": list(rights.values()),
        **unpaid_state(hub, status, now),
    }
    if plan is not None or not unknown:
        # Only modules: the business is on Free with them. A price nobody sells leaves the plan as it is.
        state["plan"] = plan.slug if plan else _free_slug()
    if interval:
        state["billing_interval"] = interval
    if plan is not None:
        # A module bought alone on Free keeps the sign-up trial; a paid plan carries its own.
        state["trial_start"] = stripe_sync._moment(live.get("trial_start"))
        state["trial_end"] = stripe_sync._moment(live.get("trial_end"))
    return state


def _free_slug() -> str:
    plan = plan_catalog.free_plan()
    return plan.slug if plan else "free"


def ended_state(hub: Hub, now: datetime | None = None) -> dict:
    """A subscription that ended: back to Free, its bought modules over now, nothing owed."""
    now = now or timezone.now()
    subscription = Subscription.objects.filter(hub=hub).first()
    rights = [
        ModuleRightIn(
            module_slug=item.module_slug,
            stripe_item_id="",
            valid_until=min(item.valid_until or now, now),
        )
        for item in SubscriptionItem.objects.filter(
            subscription=subscription, source=SubscriptionItem.Source.PURCHASE
        )
    ]
    return {
        "plan": _free_slug(),
        "status": Subscription.Status.ACTIVE.value,
        "stripe_subscription_id": "",
        "current_period_start": None,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "trial_start": None,
        "trial_end": None,
        "modules": rights,
        "cancel_requested_at": None,
        **unpaid_state(hub, "canceled", now),
    }


def apply_live(hub_id, live: dict) -> None:
    """Write what the live subscription says of the business (``hubs.subscription.apply``); a downgrade Stripe
    has just applied is forgotten."""
    hub = Hub.objects.get(pk=hub_id)
    apply_state(hub, live_state(hub, live))
    downgrades._forget_applied_change(hub_id, live)


def apply_state(hub: Hub, state: dict) -> bool:
    """Write ``state`` through ``hubs.subscription.apply``; whether anything changed."""
    applied = subscription_sync.subscription_apply(
        hub_callbacks.system_ctx_for(hub.id), SubscriptionApplyIn(hub_id=hub.id, **state)
    )
    if state.get("standing") in ("grace", "suspended"):
        # Whatever put the business in dunning (a failure, Stripe's ``unpaid``, the sweep), its payer is told
        # once, after the COMMIT; a mail that cannot leave is sent by the next ``sweep_unpaid``.
        transaction.on_commit(partial(unpaid_notices._notify_quietly, hub.id), robust=True)
    return applied.changed


def mark_card_changed(
    *, method: str, stripe_customer_id: str | None = None, hub: Hub | None = None
) -> bool:
    """Note that the card of the unresolved declined failures (of a customer, or of a business) is not
    ``method`` any more; ``True`` when one was noted. Each business is locked before its failures (the one
    lock order of every writer: Hub, then PaymentFailure)."""

    def changeable(business_id):
        return (
            PaymentFailure.objects.filter(
                hub_id=business_id,
                resolved_at__isnull=True,
                reason=PaymentFailure.Reason.CARD_DECLINED,
                card_changed_at__isnull=True,
            )
            .exclude(payment_method_id=method)
            # The card that failed is unknown: no card can be said to be another one.
            .exclude(payment_method_id="")
        )

    if hub is not None:
        # Called with the business already held (``live_state``, inside its lock).
        return changeable(hub.id).update(card_changed_at=timezone.now()) > 0
    hub_ids = set(
        PaymentFailure.objects.filter(
            stripe_customer_id=stripe_customer_id,
            resolved_at__isnull=True,
            reason=PaymentFailure.Reason.CARD_DECLINED,
            card_changed_at__isnull=True,
        ).values_list("hub_id", flat=True)
    )
    noted = False
    for business in Hub.objects.filter(pk__in=hub_ids).order_by("pk"):
        with stripe_sync.holding(business.id):
            now = timezone.now()
            if not changeable(business.id).update(card_changed_at=now):
                continue
            noted = True
            local = Subscription.objects.filter(hub=business).first()
            if local is not None and local.status in stripe_sales.DUNNING_STATUSES:
                apply_state(business, unpaid_state(business, local.status, now))
    return noted
