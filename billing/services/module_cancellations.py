"""A bought module cancelled: it works until the end of the period it was paid for, and is kept again by undoing the
cancellation before it ends."""

import logging
import uuid

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.errors import NotFound as NotFoundError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.models import Module
from billing import events, queries, stripe_service
from billing.schemas.subscription_changes import ModuleIn, SubscriptionOut
from billing.services import downgrades, live_subscriptions, payment_gates, stripe_sales
from hubs.models import Subscription, SubscriptionItem

logger = logging.getLogger("billing.services")


def _bought_item(subscription: Subscription | None, slug: str) -> SubscriptionItem:
    item = (
        SubscriptionItem.objects.filter(
            subscription=subscription, module_slug=slug
        ).first()
        if subscription is not None
        else None
    )
    if item is None:
        raise NotFoundError(_("This business has no such module."))
    if item.source == SubscriptionItem.Source.PLAN:
        raise Conflict(
            _("This module comes with the plan: change the plan to drop it."),
            code="billing.module_included",
        )
    return item


@operation(
    "billing.module.cancel",
    kind="command",
    permission="billing.pay",
    input=ModuleIn,
    output=SubscriptionOut,
    ai=INTERNAL,  # unused
)
def module_cancel(ctx: OperationContext, data: ModuleIn) -> dict:
    """Cancel a bought module: it leaves the subscription without proration and works until the end of the
    period (``valid_until`` in the snapshot). The last thing a subscription bills ends the
    subscription at the end of the period instead (Stripe keeps at least one item)."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    downgrades._require_no_pending_change(hub)
    item = _bought_item(subscription, data.module)
    if item.valid_until is not None:
        return live_subscriptions.subscription_out(hub.id)
    payment_gates.require_stripe()
    live = stripe_sales._live(subscription)
    others = [line for line in stripe_sales._live_items(live) if line["id"] != item.stripe_item_id]
    with payment_gates.stripe_errors():
        if others:
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id,
                {
                    "items": [{"id": item.stripe_item_id, "deleted": True}],
                    "proration_behavior": "none",
                },
            )
        else:
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": True}
            )
    live_subscriptions.apply_live(hub.id, updated)
    record_event(
        ctx, events.MODULE_CANCELLED, {"hub_id": str(hub.id), "module": data.module}
    )
    return live_subscriptions.subscription_out(hub.id)


@operation(
    "billing.module.keep",
    kind="command",
    permission="billing.pay",
    input=ModuleIn,
    output=SubscriptionOut,
    ai=INTERNAL,  # unused
)
def module_keep(ctx: OperationContext, data: ModuleIn) -> dict:
    """Undo the cancellation of a module before it ends: it is billed again from the next renewal (nothing
    is charged now: the period was paid). Not with an unpaid invoice, nor once it ended (buy it again),
    nor while the plan itself is cancelled (keep the plan first)."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    downgrades._require_no_pending_change(hub)
    item = _bought_item(subscription, data.module)
    if item.valid_until is None:
        return live_subscriptions.subscription_out(hub.id)
    if item.valid_until <= timezone.now():
        raise Conflict(
            _("This module has ended: buy it again in the store."),
            code="billing.module_ended",
        )
    if queries.module_on_sale(item.module_slug) is None:
        # It works until its cancellation ends, and is not sold again by undoing it.
        raise Conflict(
            _("This module is no longer sold: it works until its cancellation ends and cannot be kept."),
            code="billing.module_off_sale",
        )
    stripe_sales._require_paid_up(hub, subscription)
    payment_gates.require_stripe()
    live = stripe_sales._live(subscription)
    billed = {line["id"] for line in stripe_sales._live_items(live)}
    with payment_gates.stripe_errors():
        if item.stripe_item_id and item.stripe_item_id in billed:
            if stripe_sales._plan_item(live) is not None:
                raise Conflict(
                    _(
                        "The plan is cancelled, and its modules with it: keep the plan first."
                    ),
                    code="billing.plan_cancelled",
                )
            live = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": False}
            )
        else:
            stripe_sales._require_room(live)
            sale = stripe_sales.module_sale(
                item.module_slug,
                subscription.billing_interval,
                module=Module.objects.filter(slug=item.module_slug).first(),
            )
            tax_rates = stripe_sales.price_sale(
                hub,
                sale,
                recurring_net=stripe_sales._recurring_net(subscription, sale.interval, adding=sale),
            )
            stripe_service.create_subscription_item(
                {
                    "subscription": subscription.stripe_subscription_id,
                    "price": sale.price_id,
                    "quantity": 1,
                    "tax_rates": tax_rates,
                    "proration_behavior": "none",
                    "metadata": {"hub_id": str(hub.id), "module": sale.slug},
                },
                # Its own request: keeping again after cancelling again must not replay the first keep.
                idempotency_key=f"module-keep-{hub.id}-{sale.slug}-{uuid.uuid4().hex}",
            )
            live = stripe_service.retrieve_subscription(
                subscription.stripe_subscription_id
            )
            if not any(
                (
                    found := queries.module_for_price(
                        (line.get("price") or {}).get("id", "")
                    )
                )
                and found[0].slug == sale.slug
                for line in stripe_sales._live_items(live)
            ):
                logger.error(
                    "[BILLING] Hub %s kept %s but Stripe does not bill it back",
                    hub.id,
                    sale.slug,
                )
                raise OperationError(
                    _(
                        "The payment service did not confirm the change. Nothing was charged; try again."
                    ),
                    code="billing.not_confirmed",
                    status=502,
                )
    live_subscriptions.apply_live(hub.id, live)
    record_event(
        ctx, events.MODULE_KEPT, {"hub_id": str(hub.id), "module": data.module}
    )
    return live_subscriptions.subscription_out(hub.id)
