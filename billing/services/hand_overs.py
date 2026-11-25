"""A business handed over with a paid plan: its plan stops renewing on the previous payer's card, the new owner keeps it
with their own (``billing.plan.take_over``), and what the previous owner left open in Stripe Checkout can no longer be
paid."""

import logging
from datetime import datetime
from typing import NamedTuple

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base.navigation import BUSINESSES
from billing import events, stripe_service
from billing.models import CheckoutAttempt
from billing.schemas.checkout import CheckoutStartOut
from billing.schemas.common import HubIn
from billing.services import (
    checkouts,
    discounts,
    downgrades,
    live_subscriptions,
    payment_gates,
    promo_holds,
    stripe_customers,
    stripe_sales,
)
from billing.stripe_checkout import (
    EMBEDDED_UI_MODE,
    KIND_METADATA_KEY,
    CheckoutKind,
)
from billing.stripe_period import subscription_period
from hubs import emails as hub_emails
from hubs.queries import access_control, payers
from hubs.services import refusals
from hubs.models import Hub, HubMember, Subscription

logger = logging.getLogger("billing.services")


def end_renewal_after_hand_over(hub: Hub, new_owner) -> datetime | None:
    """The business ``hub`` was just handed over to ``new_owner`` (``hubs.ownership.accept``, in its transaction):
    a plan still charged to the card of another account's payer stops renewing there (Stripe
    ``cancel_at_period_end``). The business keeps it until the end of the period already paid, the previous payer
    is never charged again, and the new owner keeps it with their own card (``billing.plan.take_over``) or it
    goes back to Free on that date. A plan the new owner already pays is left alone, and so is one already ending.
    Stripe not answering refuses the hand-over (503): nothing changes hands.

    The end of that paid period, which the mail of the hand-over tells the previous payer; ``None`` on Free or when
    the new owner already pays it."""
    subscription = Subscription.objects.filter(hub=hub).first()
    if not stripe_sales._paying(subscription) or payers.plans_charged_to(hub.id, new_owner.pk).exists():
        return None
    if subscription.cancel_at_period_end:
        return subscription.current_period_end
    payment_gates.require_stripe()
    # Free wins over a downgrade that waits (Stripe refuses to cancel a scheduled subscription).
    downgrades._release_pending(hub)
    with payment_gates.stripe_errors():
        updated = stripe_service.update_subscription(
            subscription.stripe_subscription_id, {"cancel_at_period_end": True}
        )
    live_subscriptions.apply_live(hub.id, updated)
    logger.info("[BILLING] Hub %s handed over: its plan stops renewing on its previous payer's card", hub.id)
    return Subscription.objects.get(hub=hub).current_period_end


def billed_to_another_account(subscription: Subscription | None, profile) -> bool:
    """Whether the live plan of a business is charged to a Stripe customer that is not its payer's (``profile``):
    the card of the payer before a hand-over."""
    if not stripe_sales._paying(subscription):
        return False
    return profile is None or subscription.stripe_customer_id != profile.stripe_customer_id


def _nothing_to_take_over() -> Conflict:
    return Conflict(
        _("This business's plan is already paid with your card, or it is on Free: there is nothing to keep."),
        code="billing.nothing_to_take_over",
    )


@operation(
    "billing.plan.take_over",
    kind="command",
    permission="billing.pay",
    input=HubIn,
    output=CheckoutStartOut,
    ai=INTERNAL,  # stripe
)
def plan_take_over(ctx: OperationContext, data: HubIn) -> dict:
    """«Keep it with my card»: the new owner of a handed-over business keeps its plan and modules with
    their own payer. An Embedded Checkout of the same prices whose billing starts on the day the paid period ends
    (``billing_cycle_anchor``, no proration): nothing is charged today and nobody pays twice. Its completion
    (``checkout_completed``) moves the business to the new subscription and ends the previous one.

    Only its owner (404 without access, 403 for another role); their own payer first (409
    ``billing.payer_required``, the form of the dialog); a business on Free or already paid with this owner's
    card has nothing to keep (409 ``billing.nothing_to_take_over``); an unpaid invoice is paid first."""
    user = access_control.account_of(ctx)
    member = access_control.access(user, data.hub_id, HubMember.Role.OWNER, lock=True)
    refusals.refuse_to_change(member.hub)
    hub = Hub.objects.select_related("billing_profile").get(pk=member.hub_id)
    subscription = Subscription.objects.select_related("plan").filter(hub=hub).first()
    if not stripe_sales._paying(subscription) or payers.plans_charged_to(hub.id, user.pk).exists():
        raise _nothing_to_take_over()
    profile = hub.billing_profile
    if profile is None or profile.owner_id != user.pk:
        raise Conflict(
            _("Say who pays for this business first: its billing details are another account's."),
            code="billing.payer_required",
        )
    stripe_sales._require_paid_up(hub, subscription)
    payment_gates.require_payments()
    live = stripe_sales._live(subscription)
    if (live.get("status") or "") in stripe_sales.ENDED_STATUSES:
        raise _nothing_to_take_over()
    _start, period_end = subscription_period(live)
    line_items = []
    for line in stripe_sales._live_items(live):
        sale = stripe_sales._item_sale(subscription, line)
        if sale is None:
            raise Conflict(
                _("This business pays something we no longer sell: contact support to keep it."),
                code="billing.unknown_price",
            )
        tax_rates = stripe_sales.price_sale(hub, sale, recurring_net=stripe_sales._recurring_net(subscription, sale.interval))
        line_items.append({"price": sale.price_id, "quantity": line.get("quantity") or 1, "tax_rates": tax_rates})
    carried = discounts.takeover_discounts(subscription.stripe_subscription_id, live)
    selection = f"takeover:{subscription.stripe_subscription_id}:" + ";".join(
        f"{line['price']}={','.join(line['tax_rates'])}" for line in line_items
    ) + "".join(f":{held['coupon']}" for held in carried)
    selection = selection[:255]
    attempt = (
        CheckoutAttempt.objects.filter(
            hub=hub,
            selection=selection,
            status=CheckoutAttempt.Status.OPEN,
            created_at__gt=timezone.now() - CheckoutAttempt.REUSE_FOR,
        )
        .exclude(client_secret="")
        .order_by("-created_at")
        .first()
    )
    if attempt is None:
        attempt = _open_takeover(ctx, hub, subscription, Takeover(line_items, period_end, selection, carried))
    return {
        "flow": "checkout",
        "session_id": attempt.stripe_session_id,
        "client_secret": attempt.client_secret,
        "publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "preview": None,
    }


class Takeover(NamedTuple):
    """The checkout of a new owner keeping the plan: its lines, the end of the paid period it bills from, its
    selection and what it carries of the business's discount."""

    line_items: list[dict]
    period_end: int
    selection: str
    discounts: list[dict]


def _open_takeover(ctx, hub: Hub, subscription: Subscription, takeover: Takeover):
    checkouts._expire_other_sessions(hub, takeover.selection)
    customer = stripe_customers.ensure_customer(hub)
    attempt = CheckoutAttempt.objects.create(
        hub=hub,
        owner=access_control.account_of(ctx),
        kind=CheckoutAttempt.Kind.TAKEOVER,
        plan_slug=subscription.plan.slug if subscription.plan else "",
        billing_interval=subscription.billing_interval,
        selection=takeover.selection,
    )
    base = hub_emails.base_url(ctx.request)
    params = {
        "ui_mode": EMBEDDED_UI_MODE,
        "mode": "subscription",
        "customer": customer,
        "customer_update": {"name": "auto", "address": "auto"},
        "line_items": takeover.line_items,
        "metadata": {
            KIND_METADATA_KEY: CheckoutKind.PLAN_TAKEOVER.value,
            "hub_id": str(hub.id),
            "replaces": subscription.stripe_subscription_id,
            "attempt": str(attempt.id),
        },
        "subscription_data": {
            "description": f"ERPlora — {hub.name}",
            "metadata": {"hub_id": str(hub.id)},
            # Billed from the day the paid period ends, nothing before it: the business uses what was paid.
            "billing_cycle_anchor": takeover.period_end,
            "proration_behavior": "none",
        },
        "redirect_on_completion": "if_required",
        "return_url": f"{base}{BUSINESSES}/{hub.id}/summary?checkout={{CHECKOUT_SESSION_ID}}",
        "locale": "auto",
        "billing_address_collection": "required",
        "tax_id_collection": {"enabled": False},
        "integration_identifier": checkouts.INTEGRATION_IDENTIFIER,
    }
    if takeover.discounts:
        params["discounts"] = takeover.discounts
    with payment_gates.stripe_errors():
        session = stripe_service.create_checkout_session(params, idempotency_key=f"checkout-{attempt.id}")
    attempt.stripe_session_id = session["id"]
    attempt.client_secret = session.get("client_secret") or ""
    attempt.save(update_fields=["stripe_session_id", "client_secret", "updated_at"])
    record_event(
        ctx,
        events.CHECKOUT_STARTED,
        {"hub_id": str(hub.id), "kind": "takeover", "attempt": str(attempt.id)},
    )
    return attempt


def expire_open_checkouts(hub_id) -> None:
    """After a hand-over's COMMIT (``hubs.ownership.accept``): the Checkout Sessions the business had open (its
    previous owner's) can no longer be paid (Stripe's ``expire``). One Stripe no longer lets expire (paid meanwhile)
    is left to the webhook, which refunds a payment of somebody who no longer owns it (``_end_not_owner``); Stripe
    away is logged as an error and changes nothing else: the hand-over is done either way."""
    for attempt in CheckoutAttempt.objects.filter(hub_id=hub_id, status=CheckoutAttempt.Status.OPEN).exclude(
        stripe_session_id=None
    ):
        try:
            stripe_service.expire_checkout_session(attempt.stripe_session_id)
        except stripe_service.StripeRefused as refused:
            logger.info(
                "[BILLING] Checkout %s of hub %s is not open any more (%s): the webhook decides",
                attempt.stripe_session_id,
                hub_id,
                refused.code,
            )
            continue
        except (stripe_service.StripeUnavailable, stripe_service.StripeNotConfigured) as failed:
            logger.error(
                "[BILLING] Checkout %s of hub %s stays open after its hand-over: %s. A payment of it is refunded by "
                "the webhook",
                attempt.stripe_session_id,
                hub_id,
                failed,
                extra={"event": "billing.checkout_not_expired", "hub_id": str(hub_id)},
            )
            continue
        attempt.status = CheckoutAttempt.Status.EXPIRED
        attempt.save(update_fields=["status", "updated_at"])
        promo_holds.release(attempt=attempt)
