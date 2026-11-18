"""A business that pays already: a module or a plan previewed and confirmed, charged now or not at all, and the plan
cancelled at the end of its period or kept."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, INTERNAL, operation
from live.outbox import record_event

from billing import events, queries, stripe_service
from billing.models import PromoCode
from billing.schemas import CheckoutConfirmIn, HubIn, PlanChangeIn, SubscriptionOut
from billing.services import (
    discounts,
    downgrades,
    live_subscriptions,
    payment_gates,
    promo_codes,
    stripe_sales,
    stripe_sync,
)
from billing.stripe_period import subscription_period
from hubs.models import Hub, Subscription


@dataclass(frozen=True)
class PlanChange:
    """What a plan change sends to Stripe: the items, and how it is charged."""

    items: list
    #: ``always_invoice`` (charged now) or ``none`` (a trial: nothing until it ends).
    proration_behavior: str
    #: The sign-up trial left, or a promo code's: the plan starts charging then.
    trial_end: int | None = None
    promo: PromoCode | None = None


def _plan_change(
    hub: Hub, subscription: Subscription, live: dict, sale: stripe_sales.Sale, promo_code: str = ""
) -> PlanChange:
    """The items of a plan change: the plan item gets the new price; on a change of billing, every module
    item its price of the new billing (Stripe bills one interval per subscription), each with our tax. A
    subscription of modules alone (a Free business) gets its plan item, keeping the days left of the sign-up
    trial or a promo code's, as the checkout does. Never with a code of a discount; yearly billing waits for a discount
    for months to end."""
    discounts.require_annual_allowed(live, subscription, sale)
    if (
        sale.plan.pk == subscription.plan_id
        and sale.interval == subscription.billing_interval
    ):
        raise Conflict(
            _("This business is already on this plan."), code="billing.same_plan"
        )
    if subscription.cancel_at_period_end:
        raise Conflict(
            _("The plan is cancelled: keep it first, then change it."),
            code="billing.cancellation_pending",
        )
    recurring = stripe_sales._recurring_net(subscription, sale.interval, plan=sale.plan)
    tax_rates = stripe_sales.price_sale(hub, sale, recurring_net=recurring)
    current = stripe_sales._plan_item(live)
    plan_line = {"price": sale.price_id, "tax_rates": tax_rates}
    if current is None:
        stripe_sales._require_room(live)
    items = [
        {"id": current["id"], **plan_line, "tax_rates": stripe_sync._rates_param(tax_rates)}
        if current
        else {**plan_line, "quantity": 1}
    ]
    if sale.interval != subscription.billing_interval:
        for item in stripe_sales._live_items(live):
            found = queries.module_for_price(item["price"]["id"])
            if found is None:
                continue
            module_line = stripe_sales.module_sale(found[0].slug, sale.interval, module=found[0])
            items.append(
                {
                    "id": item["id"],
                    "price": module_line.price_id,
                    "tax_rates": stripe_sync._rates_param(
                        stripe_sales.price_sale(hub, module_line, recurring_net=recurring)
                    ),
                }
            )
    if current is not None:
        return PlanChange(items, "always_invoice")
    promo = promo_codes.plan_change_promo(promo_code, hub=hub, customer=subscription.stripe_customer_id)
    trial_end = promo_codes.trial_end(subscription, promo, timezone.now())
    if trial_end is None:
        return PlanChange(items, "always_invoice")
    return PlanChange(items, "none", trial_end=trial_end, promo=promo)


def _preview(
    hub: Hub, subscription: Subscription, sale: stripe_sales.Sale, promo_code: str = ""
) -> dict:
    live = stripe_sales._live(subscription)
    proration_date = int(timezone.now().timestamp())
    details: dict = {
        "proration_behavior": "always_invoice",
        "proration_date": proration_date,
    }
    if sale.kind == "plan":
        change = _plan_change(hub, subscription, live, sale, promo_code)
        if change.trial_end is None and stripe_sales._plan_item(live) is not None and downgrades.is_downgrade(subscription, sale):
            _start, period_end = subscription_period(live)
            return {
                "flow": "confirm",
                "session_id": None,
                "client_secret": None,
                "publishable_key": None,
                "preview": {
                    "amount_due_cents": 0,
                    "tax_cents": 0,
                    "currency": "eur",
                    "proration_date": proration_date,
                    # The new price starts with the next period (a downgrade waits for it).
                    "charge_starts_at": period_end,
                },
            }
        details["items"] = change.items
        if change.trial_end is not None:
            # A trial charges nothing now: no proration (Stripe refuses a proration date without one).
            details = {
                "items": change.items,
                "proration_behavior": "none",
                "trial_end": change.trial_end,
            }
    else:
        stripe_sales._require_room(live)
        recurring = stripe_sales._recurring_net(subscription, sale.interval, adding=sale)
        details["items"] = [
            {
                "price": sale.price_id,
                "quantity": 1,
                "tax_rates": stripe_sales.price_sale(hub, sale, recurring_net=recurring),
            }
        ]
    with payment_gates.stripe_errors():
        preview = stripe_service.preview_invoice(
            {
                "customer": live.get("customer") or subscription.stripe_customer_id,
                "subscription": subscription.stripe_subscription_id,
                "subscription_details": details,
            }
        )
    trial_end = live.get("trial_end")
    trialing = (
        live.get("status") == "trialing" and trial_end and trial_end > proration_date
    )
    return {
        "flow": "confirm",
        "session_id": None,
        "client_secret": None,
        "publishable_key": None,
        "preview": {
            "amount_due_cents": int(preview.get("amount_due") or 0),
            "tax_cents": tax_cents_of(preview),
            "currency": preview.get("currency") or "eur",
            "proration_date": proration_date,
            # A module added during the plan's trial is charged once the trial ends, with the plan.
            "charge_starts_at": details.get("trial_end")
            or (trial_end if trialing else None),
        },
    }


def tax_cents_of(invoice: dict) -> int:
    """The tax an invoice (or a preview) carries, in cents: ``total_taxes`` since the 2025 API, ``tax``
    before."""
    taxes = invoice.get("total_taxes")
    if taxes is not None:
        return sum(int(tax.get("amount") or 0) for tax in taxes)
    return int(invoice.get("tax") or 0)


#: How long a preview's price holds, and how far ahead of now a proration date may be (clock skew).
PREVIEW_VALID_FOR = timedelta(hours=1)
PREVIEW_SKEW = timedelta(seconds=60)


def _require_fresh_preview(proration_date: int) -> None:
    """The proration date the confirmation sends is the preview's, and the preview is recent: a date in the
    future would charge less, an old one another price."""
    now = timezone.now()
    moment = stripe_sync._moment(proration_date)
    if (
        moment is None
        or moment < now - PREVIEW_VALID_FOR
        or moment > now + PREVIEW_SKEW
    ):
        raise Conflict(
            _("The price shown is out of date: review it again."),
            code="billing.preview_expired",
        )


def _checkout_required() -> Conflict:
    return Conflict(
        _("This business does not pay anything yet: buy it with the checkout."),
        code="billing.checkout_required",
    )


@operation(
    "billing.checkout.confirm",
    kind="command",
    permission="billing.pay",
    input=CheckoutConfirmIn,
    output=SubscriptionOut,
    ai=INTERNAL,  # stripe
)
def checkout_confirm(ctx: OperationContext, data: CheckoutConfirmIn) -> dict:
    """Add a module to the subscription of a business that pays already, at the previewed proration: the
    prorated part is charged NOW (``always_invoice``) or the module is not added (``error_if_incomplete``:
    a declined card is 409 ``billing.card_declined`` and nothing changes). Each confirmation is its own Stripe
    request (a retry after changing the card must not replay the decline); the hub's lock serialises them."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    downgrades._require_no_pending_change(hub)
    if not stripe_sales._paying(subscription):
        raise _checkout_required()
    sale = stripe_sales.module_sale(data.module, subscription.billing_interval)
    payment_gates.require_payments()
    _require_fresh_preview(data.proration_date)
    stripe_sales._require_paid_up(hub, subscription)
    stripe_sales._require_module_not_owned(subscription, sale.slug)
    stripe_sales._require_room(stripe_sales._live(subscription))
    tax_rates = stripe_sales.price_sale(
        hub,
        sale,
        recurring_net=stripe_sales._recurring_net(subscription, sale.interval, adding=sale),
    )
    with payment_gates.stripe_errors(charging=True):
        stripe_service.create_subscription_item(
            {
                "subscription": subscription.stripe_subscription_id,
                "price": sale.price_id,
                "quantity": 1,
                "tax_rates": tax_rates,
                "proration_behavior": "always_invoice",
                "proration_date": data.proration_date,
                "payment_behavior": "error_if_incomplete",
                "metadata": {"hub_id": str(hub.id), "module": sale.slug},
            },
            idempotency_key=f"module-{hub.id}-{sale.slug}-{uuid.uuid4().hex}",
        )
    # Charged: a read-back that fails is not «nothing was charged»; the webhook applies it then.
    live = stripe_sync._read_live(subscription.stripe_subscription_id)
    if live is not None:
        live_subscriptions.apply_live(hub.id, live)
    record_event(ctx, events.MODULE_ADDED, {"hub_id": str(hub.id), "module": sale.slug})
    return live_subscriptions.subscription_out(hub.id)


@operation(
    "billing.plan.change",
    kind="command",
    permission="billing.pay",
    input=PlanChangeIn,
    output=SubscriptionOut,
    # Not a tool of the chat, on purpose: it charges now, so it is done in the Store,
    # whose dialog asks the server for the fresh preview (``proration_date``, ``_require_fresh_preview``) and shows it.
    ai=INTERNAL,  # preview
)
def plan_change(ctx: OperationContext, data: PlanChangeIn) -> dict:
    """Move a paying business to another plan or billing, at the previewed proration (``billing.checkout.start``
    with the plan): charged NOW or not at all. A free business buys with the checkout; going back to Free is
    cancelling; a cancelled plan is kept before it changes. A business paying modules alone gets its plan
    with the trial it has left (or its promo code's), charging nothing until it ends."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    if not stripe_sales._paying(subscription):
        raise _checkout_required()
    sale = stripe_sales.plan_sale(hub, data.plan, data.interval)
    payment_gates.require_payments()
    _require_fresh_preview(data.proration_date)
    stripe_sales._require_paid_up(hub, subscription)
    live = stripe_sales._live(subscription)
    change = _plan_change(hub, subscription, live, sale, data.promo_code)
    if change.trial_end is None and stripe_sales._plan_item(live) is not None and downgrades.is_downgrade(subscription, sale):
        downgrades._schedule_downgrade(hub, subscription, live, sale, change.items)
        record_event(
            ctx,
            events.PLAN_CHANGE_SCHEDULED,
            {"hub_id": str(hub.id), "plan": sale.slug, "interval": sale.interval},
        )
        return live_subscriptions.subscription_out(hub.id)
    downgrades._release_pending(hub, live)
    params = {"items": change.items, "payment_behavior": "error_if_incomplete"}
    if change.trial_end is not None:
        params.update(proration_behavior="none", trial_end=change.trial_end)
    else:
        params.update(
            proration_behavior="always_invoice", proration_date=data.proration_date
        )
    with payment_gates.stripe_errors(charging=True):
        updated = stripe_service.update_subscription(
            subscription.stripe_subscription_id,
            params,
            idempotency_key=f"plan-{hub.id}-{sale.slug}-{sale.interval}-{uuid.uuid4().hex}",
        )
    live_subscriptions.apply_live(hub.id, updated)
    if change.promo is not None:
        promo_codes.redeem_promo(change.promo.code, hub=hub, customer=subscription.stripe_customer_id)
    record_event(
        ctx,
        events.PLAN_CHANGED,
        {"hub_id": str(hub.id), "plan": sale.slug, "interval": sale.interval},
    )
    return live_subscriptions.subscription_out(hub.id)


@operation(
    "billing.plan.cancel",
    kind="command",
    permission="billing.pay",
    input=HubIn,
    output=SubscriptionOut,
    ai=AI(
        description="Cancels the plan of a business at the end of its period: then it goes back to Free with its data.",
        risk="high",
        # Its card first says what the «Cancel the plan» dialog of Billing says.
        preview={
            "operation": "billing.plan.cancel_preview",
            "fields": ["plan", "paid_until", "then", "modules", "free_users", "free_devices", "people", "unpaid_cents"],
        },
        asks={
            "en": (
                "cancel the bar's plan",
                "I don't want to pay for Starter anymore",
                "stop charging me for the salon when the month ends",
            ),
            "es": (
                "cancela el plan del bar",
                "ya no quiero pagar el Starter",
                "dejad de cobrarme la peluquería cuando acabe el mes",
            ),
        },
    ),
)
def plan_cancel(ctx: OperationContext, data: HubIn) -> dict:
    """Cancel the plan at the end of its period: it works until then and the business goes
    back to Free, with its data. Cancelling again changes nothing."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    if not stripe_sales._paying(subscription):
        raise Conflict(
            _("This business is on Free: there is nothing to cancel."),
            code="billing.nothing_to_cancel",
        )
    if not subscription.cancel_at_period_end:
        payment_gates.require_stripe()
        # Free wins over a downgrade that waits (Stripe refuses to cancel a scheduled subscription).
        downgrades._release_pending(hub)
        with payment_gates.stripe_errors():
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": True}
            )
        live_subscriptions.apply_live(hub.id, updated)
        record_event(ctx, events.PLAN_CANCELLED, {"hub_id": str(hub.id)})
    return live_subscriptions.subscription_out(hub.id)


@operation(
    "billing.plan.keep",
    kind="command",
    permission="billing.pay",
    input=HubIn,
    output=SubscriptionOut,
    ai=AI(
        description="Undoes the cancellation of a business's plan before its period ends: it renews as before.",
        asks={
            "en": (
                "actually, keep my plan",
                "undo the cancellation of the salon's plan",
                "don't cancel my subscription after all",
            ),
            "es": (
                "al final no cancelo, mantén el plan",
                "deshaz la cancelación de la peluquería",
                "sigo con el Starter, no lo des de baja",
            ),
        },
    ),
)
def plan_keep(ctx: OperationContext, data: HubIn) -> dict:
    """Undo a cancellation before the period ends: the plan renews as before. Not with an unpaid invoice
    (pay it first: keeping would hand the plan back without paying it)."""
    hub, subscription = stripe_sales._owned(ctx, data.hub_id)
    if not stripe_sales._paying(subscription):
        raise Conflict(
            _("This business is on Free: there is nothing to keep."),
            code="billing.nothing_to_cancel",
        )
    if subscription.cancel_at_period_end:
        stripe_sales._require_paid_up(hub, subscription)
        payment_gates.require_stripe()
        with payment_gates.stripe_errors():
            updated = stripe_service.update_subscription(
                subscription.stripe_subscription_id, {"cancel_at_period_end": False}
            )
        live_subscriptions.apply_live(hub.id, updated)
        record_event(ctx, events.PLAN_KEPT, {"hub_id": str(hub.id)})
    elif downgrades.pending_change(hub) is not None:
        # A downgrade that waits for the end of the period is undone: the plan renews as it is.
        payment_gates.require_stripe()
        downgrades._release_pending(hub)
        record_event(ctx, events.PLAN_KEPT, {"hub_id": str(hub.id)})
    return live_subscriptions.subscription_out(hub.id)
