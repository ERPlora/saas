"""Writes of billing in Stripe: a business handed over with a paid plan, the webhook and the sweeps that apply the live
subscription, and ERPlora's invoices, credit notes and OSS notices. Buying, changing and cancelling, the VAT number of a
payer, its VIES verdict and the tax of a sale live in their own modules of this package."""

import logging
import uuid
from collections import Counter
from collections.abc import Callable
from functools import partial
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import NamedTuple

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, OperationError
from live.errors import NotFound as NotFoundError
from live.operations import INTERNAL, operation
from live.outbox import notify, record_event

from apps.models import Module
from base.navigation import BILLING, BUSINESSES
from billing import events, platform_contract, queries, stripe_service, vat, vies
from billing.models import (
    CheckoutAttempt,
    Invoice,
    InvoiceCounter,
    InvoiceLine,
    OssNotice,
    PaymentFailure,
    VatCheck,
    WebhookEvent,
)
from billing.money import from_cents, to_cents
from billing.schemas import (
    CheckoutRefundRecordIn,
    CheckoutRefundRecordOut,
    CreditNoteRecordIn,
    FiscalAnswerIn,
    FiscalAnswerOut,
    InvoicePayIn,
    InvoicePayOut,
    InvoiceRecordIn,
    InvoiceRecordOut,
    RefundRecordIn,
    CheckoutStartOut,
    HubIn,
    ModuleIn,
    PortalOpenIn,
    PortalOpenOut,
    SubscriptionOut,
)
from billing.services import (
    checkouts,
    discounts,
    downgrades,
    invoice_discounts,
    live_subscriptions,
    payer_vat_numbers,
    payment_gates,
    plan_changes,
    price_checks,
    promo_codes,
    promo_holds,
    sale_tax,
    staff_test_clocks,
    stripe_customers,
    stripe_sales,
    stripe_sync,
    unpaid_notices,
    vat_clearance,
)
from billing.stripe_checkout import (
    EMBEDDED_UI_MODE,
    KIND_METADATA_KEY,
    CheckoutKind,
    checkout_session_kind,
)
from billing.stripe_keys import StripeKeyMode
from billing.stripe_period import subscription_period
from hubs import emails as hub_emails
from hubs import hub_client
from hubs.queries import access_control, membership, payers
from hubs.services import exclusive_runs, hub_callbacks, refusals, suspensions
from hubs.models import BillingProfile, Hub, HubMember, Subscription, SubscriptionItem
from hubs.hub_client import HubRefused, HubUnavailable

logger = logging.getLogger("billing.services")


# --- A business handed over with a paid plan ----------------------------------------------------------


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
    if not access_control.is_writable(member.hub):
        raise refusals.business_deleted()
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
        sale = _item_sale(subscription, line)
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


def _takeover_completed(hub: Hub, session: dict, subscription_id: str, replaced: str) -> str:
    """The new owner kept the plan with their card: the business moves to the new subscription and the
    previous one, on the previous payer's card, ends now without a refund (the business is using the period it
    paid; the new one bills from its end). Stripe not answering raises: nothing moves and Stripe delivers it
    again. A redelivery finds the business moved and ends nothing twice."""
    with stripe_sync.holding(hub.id):
        local = Subscription.objects.filter(hub=hub).first()
        if local is None or local.stripe_subscription_id != subscription_id:
            live = stripe_service.retrieve_subscription(subscription_id)
            live_subscriptions.apply_live(hub.id, live)
            if replaced and replaced != subscription_id:
                discounts.move_redemption(replaced, live)
                previous = stripe_service.retrieve_subscription(replaced)
                if (previous.get("status") or "") not in stripe_sales.ENDED_STATUSES:
                    stripe_service.cancel_subscription(replaced)
            logger.info("[BILLING] Hub %s kept its plan with its new owner's card: %s ends", hub.id, replaced)
        CheckoutAttempt.objects.filter(stripe_session_id=session.get("id")).exclude(
            status=CheckoutAttempt.Status.COMPLETED
        ).update(status=CheckoutAttempt.Status.COMPLETED, completed_at=timezone.now(), updated_at=timezone.now())
    return "completed"


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


@operation(
    "billing.portal.open",
    kind="command",
    permission="billing.pay",
    input=PortalOpenIn,
    output=PortalOpenOut,
    ai=INTERNAL,  # stripe
)
def portal_open(ctx: OperationContext, data: PortalOpenIn) -> dict:
    """Stripe's Customer Portal for the payer of the business: cards and Stripe's receipts (the panel opens
    it only on the web; the apps sell nothing)."""
    hub, _subscription = stripe_sales._owned(ctx, data.hub_id)
    payment_gates.require_stripe()
    if not settings.STRIPE_PORTAL_CONFIGURATION:
        logger.error(
            "[BILLING] STRIPE_PORTAL_CONFIGURATION is empty: the Customer Portal does not open"
        )
        raise OperationError(
            _("Payment details cannot be managed right now. Try again later."),
            code="billing.portal_unavailable",
            status=503,
        )
    customer = hub.billing_profile.stripe_customer_id if hub.billing_profile else ""
    if not customer:
        raise Conflict(
            _("The payment details appear here after the first payment."),
            code="billing.no_customer",
        )
    with payment_gates.stripe_errors():
        session = stripe_service.create_portal_session(
            customer,
            return_url=f"{hub_emails.base_url(ctx.request)}{BILLING}",
            configuration=settings.STRIPE_PORTAL_CONFIGURATION,
        )
    record_event(ctx, events.PORTAL_OPENED, {"hub_id": str(hub.id)})
    return {"url": session["url"]}


# --- The webhook: each Stripe event once, the live subscription applied ------------------------------

CLAIMED, DUPLICATE, IN_PROGRESS = "claimed", "duplicate", "in_progress"


def claim_event(event_id: str, event_type: str) -> str:
    """Decide whether this delivery processes the event: ``CLAIMED`` (process it, then ``finish_event``),
    ``DUPLICATE`` (processed already) or ``IN_PROGRESS`` (another delivery holds it; Stripe retries). The
    row is created or locked in one transaction, so of two simultaneous deliveries only one claims it; a
    claim older than ``CLAIM_LEASE`` (a process that died) is taken over."""
    now = timezone.now()
    with transaction.atomic():
        row, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={"event_type": event_type, "processing_since": now, "attempts": 1},
        )
        if created:
            return CLAIMED
        if row.success:
            return DUPLICATE
        if (
            row.processing_since is not None
            and row.processing_since > now - WebhookEvent.CLAIM_LEASE
        ):
            return IN_PROGRESS
        WebhookEvent.objects.filter(pk=row.pk).update(
            processing_since=now, attempts=F("attempts") + 1
        )
        return CLAIMED


def finish_event(
    event_id: str, *, success: bool, outcome: str, error: str = ""
) -> None:
    """Release the claim with how the processing ended; a failure stays claimable for Stripe's retry."""
    WebhookEvent.objects.filter(event_id=event_id).update(
        success=success,
        outcome=outcome[:32],
        error_message=error,
        processing_since=None,
        processed_at=timezone.now(),
    )


#: How long an event's row is kept: Stripe resends an event for 3 days at most and keeps it 30, so
#: an older row never guards a delivery again.
WEBHOOK_EVENT_RETENTION = timedelta(days=30)


def purge_webhook_events() -> int:
    """saas-cron, ``manage.py purge_webhook_events``: forget the events received more than
    ``WEBHOOK_EVENT_RETENTION`` ago, processed or not. How many were deleted."""
    deleted, _ = WebhookEvent.objects.filter(received_at__lt=timezone.now() - WEBHOOK_EVENT_RETENTION).delete()
    return deleted


#: The events ERPlora's Stripe endpoint sends to ``/webhooks/stripe/``: what ``process_stripe_event``
#: handles, and the one list ``audit_stripe_webhooks`` compares the endpoint with every day;
#: ``billing/README.md`` and ``billing/webhooks.py`` cite it instead of repeating it. ``invoice.payment_succeeded`` is
#: handled as ``invoice.paid`` but not subscribed: one notice per payment is enough.
STRIPE_WEBHOOK_EVENTS = (
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
    "invoice.paid",
    "invoice.payment_failed",
    "invoice.voided",
    "invoice.marked_uncollectible",
    "credit_note.created",
    "credit_note.voided",
    "charge.refunded",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.updated",
)


def process_stripe_event(event: dict) -> str:  # noqa: C901, PLR0911
    """Process one signed Stripe event; its outcome (``completed``, ``processed``, ``ignored``, ``unknown``,
    ``invalid``, ``pending``…). Raises when it must be retried (Stripe did not answer a read the event needs)."""
    obj = (event.get("data") or {}).get("object") or {}
    match event.get("type"):
        case "checkout.session.completed" | "checkout.session.async_payment_succeeded":
            return checkout_completed(obj)
        case "checkout.session.async_payment_failed":
            return checkout_closed(obj, CheckoutAttempt.Status.FAILED)
        case "checkout.session.expired":
            return checkout_closed(obj, CheckoutAttempt.Status.EXPIRED)
        case "invoice.paid" | "invoice.payment_succeeded":
            return invoice_paid(obj)
        case "invoice.payment_failed":
            return invoice_payment_failed(obj)
        case "invoice.voided" | "invoice.marked_uncollectible":
            return invoice_voided(obj)
        case "credit_note.created":
            return credit_note_created(obj)
        case "credit_note.voided":
            return credit_note_voided(obj)
        case "charge.refunded":
            return charge_refunded(obj)
        case "customer.subscription.created" | "customer.subscription.updated":
            return subscription_updated(obj)
        case "customer.subscription.deleted":
            return subscription_deleted(obj)
        case "customer.updated":
            return customer_updated(obj)
    return "ignored"


def _hub_named(hub_id) -> Hub | None:
    try:
        return Hub.objects.filter(pk=hub_id).first() if hub_id else None
    except ValueError, TypeError, DjangoValidationError:
        return None


def _checkout_paid(session: dict) -> bool:
    """A complete checkout is not always a settled payment: ``paid``, or nothing to pay now (a trial)."""
    status = session.get("payment_status")
    if status == "paid":
        return True
    return (
        status == "no_payment_required"
        and session.get("mode") == "subscription"
        and bool(session.get("subscription"))
    )


def checkout_completed(session: dict) -> str:
    """A business paid in the Embedded Checkout: its subscription, read LIVE, is applied, the attempt is
    completed and its promo code counted, once whatever the redeliveries."""
    metadata = session.get("metadata") or {}
    if checkout_session_kind(metadata) is CheckoutKind.UNKNOWN:
        return "ignored"
    hub = _hub_named(metadata.get("hub_id"))
    if hub is None or not session.get("subscription"):
        logger.error(
            "[STRIPE WEBHOOK] Checkout %s names no business of ours: %s",
            session.get("id"),
            metadata,
        )
        return "invalid"
    if not _checkout_paid(session):
        return "pending"
    subscription_id = session["subscription"]
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id["id"]
    with stripe_sync.holding(hub.id):
        attempt = CheckoutAttempt.objects.select_related("owner").filter(stripe_session_id=session.get("id")).first()
        # One already applied is a redelivery, whoever owns the business now: it is left to the paths below.
        if (
            attempt is not None
            and attempt.owner_id is not None
            and attempt.status != CheckoutAttempt.Status.COMPLETED
            and attempt.owner_id != membership.owner_id(hub.id)
        ):
            return _end_not_owner(hub, attempt, session, subscription_id)
        if checkout_session_kind(metadata) is CheckoutKind.PLAN_TAKEOVER:
            return _takeover_completed(hub, session, subscription_id, metadata.get("replaces") or "")
        return _complete_checkout(hub, session, subscription_id)


def _complete_checkout(hub: Hub, session: dict, subscription_id: str) -> str:
    """The subscription the checkout paid for, applied (unless the business pays another one), the attempt
    completed and its promo code counted, with when its discount ends."""
    local = Subscription.objects.filter(hub=hub).first()
    if (
        local is not None
        and local.stripe_subscription_id
        and local.stripe_subscription_id != subscription_id
        and local.status not in stripe_sales.ENDED_STATUSES
    ):
        return _end_duplicate(hub, local, session, subscription_id)
    live = stripe_service.retrieve_subscription(subscription_id)
    live_subscriptions.apply_live(hub.id, live)
    completed = (
        CheckoutAttempt.objects.filter(stripe_session_id=session.get("id"))
        .exclude(status=CheckoutAttempt.Status.COMPLETED)
        .update(
            status=CheckoutAttempt.Status.COMPLETED,
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
    )
    code = (session.get("metadata") or {}).get("promo_code")
    if completed and code:
        customer = live.get("customer")
        promo_holds.use(
            code,
            hub=hub,
            customer=customer["id"] if isinstance(customer, dict) else customer or "",
            session=session.get("id") or "",
            live=live,
        )
    return "completed"


def _end_duplicate(
    hub: Hub, local: Subscription, session: dict, subscription_id: str
) -> str:
    """A second checkout paid for a business that pays already: the subscription it has stays; the new one
    ends now, its unused time credited to the customer, and support is told (the refund is theirs)."""
    logger.error(
        "[BILLING] Hub %s paid checkout %s while it already pays %s: the new subscription %s is ended now with "
        "its unused time as credit. Refund it if the customer asks",
        hub.id,
        session.get("id"),
        local.stripe_subscription_id,
        subscription_id,
        extra={"event": "billing.duplicate_subscription", "hub_id": str(hub.id)},
    )
    stripe_service.cancel_subscription(subscription_id, credit_unused=True)
    CheckoutAttempt.objects.filter(stripe_session_id=session.get("id")).update(
        status=CheckoutAttempt.Status.COMPLETED,
        completed_at=timezone.now(),
        updated_at=timezone.now(),
    )
    return "duplicate_subscription"


#: The webhook's outcome of a checkout paid by somebody who no longer owns the business.
NOT_OWNER = "not_owner"


def _end_not_owner(hub: Hub, attempt: CheckoutAttempt, session: dict, subscription_id: str) -> str:
    """A checkout paid by somebody who no longer owns the business (handed over while it was open): it
    is not applied. Its subscription ends now and what it charged is refunded in full (Stripe's
    «Cancel + refund»; ``charge.refunded`` makes the rectifying invoice), the attempt says ``refunded`` (its audit
    trail keeps when) and its payer is told after the COMMIT. Once: a redelivery finds it refunded. Stripe not
    answering raises, so nothing is marked and Stripe delivers it again (the refund is idempotent)."""
    if attempt.status == CheckoutAttempt.Status.REFUNDED:
        return NOT_OWNER
    live = stripe_service.retrieve_subscription(subscription_id)
    if (live.get("status") or "") not in stripe_sales.ENDED_STATUSES:
        stripe_service.cancel_subscription(subscription_id)
    invoice = live.get("latest_invoice") or ""
    if isinstance(invoice, dict):
        invoice = invoice.get("id") or ""
    refunded = (
        stripe_service.refund_invoice(
            invoice,
            key=f"refund-{session.get('id')}",
            metadata={"hub_id": str(hub.id), "checkout_session": session.get("id") or "", "reason": NOT_OWNER},
        )
        if invoice
        else 0
    )
    checkout_refund_record(
        system_context(Scope("user", str(attempt.owner_id))),
        CheckoutRefundRecordIn(attempt_id=attempt.id, refunded=refunded),
    )
    logger.error(
        "[BILLING] Hub %s: checkout %s was paid by account %s, which no longer owns it. Subscription %s ended and "
        "%s cents refunded",
        hub.id,
        session.get("id"),
        attempt.owner_id,
        subscription_id,
        refunded,
        extra={"event": "billing.checkout_not_owner", "hub_id": str(hub.id)},
    )
    return NOT_OWNER


@operation(
    "billing.checkout.refund_record",
    kind="command",
    permission="billing.manage",
    input=CheckoutRefundRecordIn,
    output=CheckoutRefundRecordOut,
    ai=INTERNAL,  # platform
)
def checkout_refund_record(ctx: OperationContext, data: CheckoutRefundRecordIn) -> dict:
    """A checkout already ended and refunded in Stripe because its payer no longer owned the business (the platform
    only, from the webhook; no route): the attempt says ``refunded`` (its audit trail keeps when), the event goes
    to the payer's channel and the payer is told by mail after the COMMIT."""
    attempt = CheckoutAttempt.objects.select_for_update().get(pk=data.attempt_id)
    attempt.status = CheckoutAttempt.Status.REFUNDED
    attempt.completed_at = timezone.now()
    attempt.save(update_fields=["status", "completed_at", "updated_at"])
    promo_holds.release(attempt=attempt)
    record_event(
        ctx,
        events.CHECKOUT_REFUNDED,
        {"hub_id": str(attempt.hub_id), "attempt": str(attempt.id), "refunded": data.refunded},
    )
    transaction.on_commit(partial(_tell_refunded, attempt.owner_id, attempt.hub_id, data.refunded), robust=True)
    return {"attempt_id": attempt.id, "status": attempt.status}


def _tell_refunded(account_id, hub_id, cents: int) -> None:
    """The mail to the payer of a checkout ended because they no longer owned the business (after the COMMIT).
    One that cannot leave is logged (``billing.emails``): the refund and its rectifying invoice in Billing are
    the record."""
    from django.contrib.auth import get_user_model

    from billing import emails

    account = get_user_model().objects.filter(pk=account_id).first()
    hub = Hub.objects.filter(pk=hub_id).first()
    if account is None or hub is None:
        logger.error("[BILLING] Nobody to tell of the refund of hub %s to account %s", hub_id, account_id)
        return
    try:
        emails.send_checkout_refunded(hub, to=account.email, language=account.language, amount=from_cents(cents))
    except emails.MailNotSent:
        return


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


def checkout_closed(session: dict, status: str) -> str:
    """A checkout whose delayed payment failed, or that expired unpaid: its attempt is closed (the next
    start opens a new session); the business does not change."""
    if checkout_session_kind(session.get("metadata")) is CheckoutKind.UNKNOWN:
        return "ignored"
    CheckoutAttempt.objects.filter(
        stripe_session_id=session.get("id"), status=CheckoutAttempt.Status.OPEN
    ).update(status=status, updated_at=timezone.now())
    promo_holds.release(session=session.get("id") or "")
    return status


def invoice_subscription(invoice: dict) -> str:
    """The subscription an invoice bills: under ``parent.subscription_details`` since the 2025 API, at the
    root before (events of an older endpoint)."""
    parent = invoice.get("parent") or {}
    found = (
        (parent.get("subscription_details") or {}).get("subscription")
        or invoice.get("subscription")
        or ""
    )
    return found["id"] if isinstance(found, dict) else found


def _local_subscription(subscription_id: str) -> Subscription | None:
    if not subscription_id:
        return None
    return (
        Subscription.objects.select_related("hub", "plan")
        .filter(stripe_subscription_id=subscription_id)
        .first()
    )


def _invoice_business(invoice: dict) -> tuple[Hub | None, str]:
    """The business an invoice bills, and its Stripe subscription. Known by the subscription, or — when the
    invoice comes ahead of its ``checkout.session.completed`` (Stripe does not order events) — by the
    ``hub_id`` its subscription's metadata carries, for a business that has no other subscription."""
    subscription_id = invoice_subscription(invoice)
    local = _local_subscription(subscription_id)
    if local is not None:
        return local.hub, subscription_id
    details = (invoice.get("parent") or {}).get("subscription_details") or {}
    named = _hub_named((details.get("metadata") or {}).get("hub_id"))
    if (
        subscription_id
        and named is not None
        and not Subscription.objects.filter(hub=named)
        .exclude(stripe_subscription_id="")
        .exists()
    ):
        return named, subscription_id
    return None, subscription_id


def invoice_paid(invoice: dict) -> str:
    """A renewal (or any invoice of the subscription) was paid: its failure is resolved and the LIVE
    subscription applied, which takes a business with a payment pending or suspended back once Stripe says
    it is paid. A late success of an older invoice while the subscription is still in dunning
    changes nothing. Stripe not answering is retried by Stripe (500), never guessed.

    In the same transaction ERPlora's invoice is recorded and numbered (``billing.invoice.record``):
    when anything fails, neither the subscription nor the invoice nor its number is written. Its lines and the
    payer's VIES verdict are read before the business is locked (they may ask Stripe and VIES)."""
    hub, subscription_id = _invoice_business(invoice)
    if hub is None:
        return _invoice_paid_elsewhere(invoice, subscription_id)
    invoice = _with_all_lines(invoice)
    charged_at = _moment_or_none((invoice.get("status_transitions") or {}).get("paid_at")) or timezone.now()
    verified, consultation = _payer_clearance(hub, charged_at)
    with stripe_sync.holding(hub.id):
        # Stripe not answering raises: its retry reads the truth (a paid invoice may be a proration or an
        # older one, and guessing «active» woke businesses still in dunning).
        live = stripe_service.retrieve_subscription(subscription_id)
        PaymentFailure.objects.filter(
            stripe_invoice_id=invoice.get("id"), resolved_at__isnull=True
        ).update(resolved_at=timezone.now())
        live_subscriptions.apply_live(hub.id, live)
        invoice_record(
            hub_callbacks.system_ctx_for(hub.id),
            InvoiceRecordIn(
                hub_id=hub.id,
                invoice=invoice,
                status="paid",
                tax_id_verified=verified,
                vat_consultation_number=consultation,
            ),
        )
    return "processed"


class UnplacedPayment(Exception):
    """Stripe collected money on an invoice no business of ERPlora's can be found for: never forgotten, the
    webhook answers 500 (Stripe retries for three days) and the ERROR tells support."""


def _invoice_paid_elsewhere(invoice: dict, subscription_id: str) -> str:
    """A paid invoice that is not of a business's current subscription: the first invoice of
    a duplicate checkout (cancelled with its unused time as credit, ``_end_duplicate``) is still money of that
    business, invoiced to it without touching its plan. One nobody can place raises."""
    named = _hub_named(((invoice.get("parent") or {}).get("subscription_details") or {}).get("metadata", {}).get("hub_id")
                       or (invoice.get("metadata") or {}).get("hub_id"))
    if named is None:
        if int(invoice.get("total") or 0) == 0:
            return "unknown" if subscription_id else "ignored"
        logger.error(
            "[INVOICE] Stripe invoice %s (subscription %s) was paid and no business of ours is known for it",
            invoice.get("id"), subscription_id or "-", extra={"event": "billing.unplaced_payment"},
        )
        raise UnplacedPayment(invoice.get("id"))
    invoice = _with_all_lines(invoice)
    charged_at = _moment_or_none((invoice.get("status_transitions") or {}).get("paid_at")) or timezone.now()
    verified, consultation = _payer_clearance(named, charged_at)
    with stripe_sync.holding(named.id):
        invoice_record(
            hub_callbacks.system_ctx_for(named.id),
            InvoiceRecordIn(
                hub_id=named.id, invoice=invoice, status="paid", tax_id_verified=verified,
                vat_consultation_number=consultation,
            ),
        )
    return "processed"


#: Declines the same card may pass on a retry (the bank said «not now», not «never»): «Pay» stays enabled.
SOFT_DECLINES = frozenset(
    {
        "insufficient_funds",
        "try_again_later",
        "processing_error",
        "approve_with_id",
        "reenter_transaction",
        "issuer_not_available",
        "card_velocity_exceeded",
        "withdrawal_count_limit_exceeded",
        "duplicate_transaction",
    }
)


def _failure_reason(why: dict | None) -> str:
    """Why a renewal failed, as the panel needs it: ``card_declined`` only when the card will not pay as it
    is (a true decline, an expired or mistyped card: «Pay» waits for another card), ``authentication_required``
    (the customer confirms it), ``payment_failed`` otherwise."""
    if why is None:
        return PaymentFailure.Reason.PAYMENT_FAILED
    code, decline = why.get("code"), why.get("decline_code")
    if "authentication_required" in (code, decline):
        return PaymentFailure.Reason.AUTHENTICATION_REQUIRED
    if code in stripe_sales.CARD_REFUSED_CODES and decline not in SOFT_DECLINES:
        return PaymentFailure.Reason.CARD_DECLINED
    return PaymentFailure.Reason.PAYMENT_FAILED


def invoice_payment_failed(invoice: dict, *, replay: bool = False) -> str:
    """A renewal could not be collected: why (``PaymentFailure``) and the business in dunning. The LIVE
    subscription decides: outside ``past_due``/``unpaid`` what Stripe says now is written and the
    event is ignored; inside, 7 days of grace from the failed invoice, then suspended (``unpaid``: at once).
    Stripe not answering raises: Stripe retries the event, the sweep its next pass.
    ``replay``: the sweep deciding again, not another failed attempt."""
    hub, subscription_id = _invoice_business(invoice)
    if hub is None:
        return "unknown" if subscription_id else "ignored"
    with stripe_sync.holding(hub.id):
        return _record_failure(hub, subscription_id, invoice, replay=replay)


def _record_failure(
    hub: Hub, subscription_id: str, invoice: dict, *, replay: bool
) -> str:
    # Stripe not answering raises (Stripe retries the event; the sweep, its next pass): a failure is never
    # applied «as it came», which suspended businesses on stale events.
    live = stripe_service.retrieve_subscription(subscription_id)
    live_status = live.get("status")
    if live_status not in stripe_sales.DUNNING_STATUSES:
        # Paid (or ended) meanwhile: what Stripe says now is written, whatever this event said.
        logger.info(
            "[STRIPE WEBHOOK] Failure of %s ignored: the subscription is %s now",
            invoice.get("id"),
            live_status,
        )
        live_subscriptions.apply_live(hub.id, live)
        return "ignored"
    try:
        why = stripe_service.payment_failure_of(invoice["id"])
    except stripe_service.StripeUnavailable, stripe_service.StripeRefused:
        why = None
    now = timezone.now()
    reason = _failure_reason(why)
    issued = stripe_sync._moment(invoice.get("created")) or now
    failure, created = PaymentFailure.objects.select_for_update().get_or_create(
        stripe_invoice_id=invoice["id"],
        defaults={
            "hub": hub,
            "stripe_subscription_id": subscription_id,
            "stripe_customer_id": invoice.get("customer") or live.get("customer") or "",
            "reason": reason,
            "failure_code": (why or {}).get("code", "")[:64],
            "decline_code": (why or {}).get("decline_code", "")[:64],
            "payment_method_id": (why or {}).get("payment_method", ""),
            "hosted_invoice_url": invoice.get("hosted_invoice_url") or "",
            "invoice_created_at": issued,
            "failed_at": now,
        },
    )
    if not created and failure.resolved_at is not None:
        # Paid already: a redelivered failure of it never reopens it.
        pass
    elif not created:
        known = {
            "hosted_invoice_url": invoice.get("hosted_invoice_url")
            or failure.hosted_invoice_url
        }
        if why is not None:
            # What Stripe says now; a lookup that failed never erases what was known.
            changed_card = (
                why.get("payment_method")
                and why["payment_method"] != failure.payment_method_id
            )
            known.update(
                reason=reason,
                failure_code=why.get("code", "")[:64],
                decline_code=why.get("decline_code", "")[:64],
                payment_method_id=why.get("payment_method", "")
                or failure.payment_method_id,
                card_changed_at=None if changed_card else failure.card_changed_at,
            )
        if not replay:
            # Another failed attempt of Stripe's; the sweep only replays to decide, it is not one.
            known.update(failed_at=now, attempts=F("attempts") + 1)
        PaymentFailure.objects.filter(pk=failure.pk).update(**known)
    live_subscriptions.apply_live(hub.id, live)
    # Listed in Billing as «not collected», with «Pay»; numbered once it is paid.
    invoice_record(
        hub_callbacks.system_ctx_for(hub.id), InvoiceRecordIn(hub_id=hub.id, invoice=invoice, status="open")
    )
    return "processed"


def subscription_updated(obj: dict) -> str:
    """A subscription changed (plan, items, status, period, cancellation): the LIVE one is applied;
    Stripe not answering → the event as it came. The first event of a new subscription finds its business
    by the ``hub_id`` of its metadata, only if that business has no other subscription."""
    subscription_id = obj.get("id") or ""
    subscription = _local_subscription(subscription_id)
    hub = subscription.hub if subscription is not None else None
    if hub is None:
        named = _hub_named((obj.get("metadata") or {}).get("hub_id"))
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
    subscription = _local_subscription(obj.get("id") or "")
    if subscription is None:
        return "unknown"
    with stripe_sync.holding(subscription.hub_id):
        live_subscriptions.apply_state(subscription.hub, live_subscriptions.ended_state(subscription.hub))
    return "processed"


# --- saas-cron: manage.py sync_subscriptions ----------------------------------------------------------

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


# --- The rate of a live subscription ------------------------------------------------------------------

#: Stripe statuses whose next invoice is still going to be charged.
RETAX_STATUSES = ("active", "trialing", "past_due")
#: The counts of a daily pass; ``refused`` and ``errors`` make the run fail after its pass (``task_failed``).
RETAX_COUNTS = ("retaxed", "unchanged", "skipped", "refused", "errors")


def _item_sale(subscription: Subscription, line: dict) -> stripe_sales.Sale | None:
    """What an item of the live subscription sells (its plan or its module, at its interval), or ``None`` for
    a price no plan nor module has."""
    price_id = (line.get("price") or {}).get("id", "")
    found = queries.plan_for_price(price_id)
    if found is not None:
        plan, interval = found
        return stripe_sales.Sale(
            "plan",
            plan.slug,
            interval,
            price_id,
            Decimal((plan.price_annual if interval == "year" else plan.price_monthly) or 0),
            vat.SAAS_SUBSCRIPTION_CATEGORY,
            plan=plan,
        )
    found = queries.module_for_price(price_id)
    if found is not None:
        module, interval = found
        cents = module.price_annual_cents if interval == "year" else module.price_monthly_cents
        return stripe_sales.Sale(
            "module",
            module.slug,
            interval,
            price_id,
            Decimal(cents) / 100,
            vat.SOFTWARE_LICENSE_CATEGORY,
            module=module,
        )
    logger.warning(
        "[BILLING] Item %s of %s bills price %s, which no plan nor module has: its rate is left alone",
        line.get("id"),
        subscription.stripe_subscription_id,
        price_id,
    )
    return None


def retax_subscription(hub: Hub) -> str:
    """Hand Stripe the rates the payer's place calls for today on every item of the business's live
    subscription: the checkout fixes a rate per item and Stripe charges it on every renewal, so a payer who
    moves (Madrid → Las Palmas), proves a VAT number, or a year that crosses the OSS threshold would keep the
    old one. The same engine as the sale (``price_sale``); the next invoice takes the new rate,
    the paid period is not touched (no proration).

    ``retaxed`` · ``unchanged`` (Stripe already holds them: nothing sent) · ``skipped`` (no live Stripe
    subscription, or one still charged to another account's card: its tax is that payer's) ·
    ``refused`` (the place is not sold to now: an ERROR, and the old rates stay until the billing details are
    fixed). With a downgrade waiting in a schedule, its phases are retaxed instead (``_retax_schedule``). Stripe
    failing raises (``stripe_errors``)."""
    subscription = Subscription.objects.filter(hub=hub).select_related("plan").first()
    if (
        subscription is None
        or not subscription.stripe_subscription_id
        or subscription.status not in RETAX_STATUSES
    ):
        return "skipped"
    hub = Hub.objects.select_related("billing_profile").get(pk=hub.pk)
    if billed_to_another_account(subscription, hub.billing_profile):
        return "skipped"
    payment_gates.require_stripe()
    pending = downgrades.pending_change(hub)
    if pending is not None:
        return _retax_schedule(hub, subscription, pending.stripe_schedule_id)
    live = stripe_sales._live(subscription)
    changes = []
    for line in stripe_sales._live_items(live):
        sale = _item_sale(subscription, line)
        if sale is None:
            continue
        try:
            due = stripe_sales.price_sale(
                hub, sale, recurring_net=stripe_sales._recurring_net(subscription, sale.interval), renewing=True
            )
        except Conflict as refused:
            return _retax_refused(hub, sale.kind, refused)
        held = [rate["id"] if isinstance(rate, dict) else rate for rate in line.get("tax_rates") or []]
        if sorted(held) != sorted(due):
            changes.append({"id": line["id"], "tax_rates": stripe_sync._rates_param(due)})
    if not changes:
        return "unchanged"
    with payment_gates.stripe_errors():
        stripe_service.update_subscription(
            subscription.stripe_subscription_id,
            {"items": changes, "proration_behavior": "none"},
        )
    logger.info("[BILLING] Hub %s retaxed: %s", hub.id, changes)
    return "retaxed"


def _retax_refused(hub: Hub, kind: str, refused: Conflict) -> str:
    logger.error(
        "[BILLING] %s of hub %s cannot be retaxed (%s): Stripe keeps charging its old rate",
        kind,
        hub.id,
        refused.code,
        extra={"event": "billing.retax_refused", "hub_id": str(hub.id), "code": refused.code},
    )
    return "refused"


def _retax_schedule(hub: Hub, subscription: Subscription, schedule_id: str) -> str:
    """A downgrade waiting in a Stripe schedule: the first invoice of the new plan is billed by its next phase,
    whose items carry the rates fixed when it was scheduled. Every phase still to run is re-stated with
    today's rates (a phase over is left out; the current one keeps its start) and its discounts. Phases are
    re-stated whole, so no rate is an empty list there, and changing the current phase changes the subscription
    at once (checked against Stripe's test API). A price no plan nor module has keeps its rates."""
    with payment_gates.stripe_errors():
        schedule = stripe_service.retrieve_schedule(schedule_id)
    now = int(timezone.now().timestamp())
    phases = []
    changed = False
    for phase in schedule.get("phases") or []:
        if phase.get("end_date") is not None and phase["end_date"] <= now:
            continue
        restated = _restated_items(hub, subscription, phase)
        if restated is None:
            return "refused"
        items, retaxed = restated
        changed = changed or retaxed
        phases.append(_restated_phase(phase, items))
    if not changed:
        return "unchanged"
    with payment_gates.stripe_errors():
        stripe_service.update_schedule(schedule_id, {"end_behavior": "release", "phases": phases})
    logger.info("[BILLING] Hub %s retaxed the phases of schedule %s", hub.id, schedule_id)
    return "retaxed"


def _restated_items(hub: Hub, subscription: Subscription, phase: dict) -> tuple[list[dict], bool] | None:
    """The items of a phase with today's rates, and whether any changed; ``None`` when one cannot be retaxed."""
    sales = []
    for item in phase.get("items") or []:
        price = item["price"] if isinstance(item["price"], str) else item["price"]["id"]
        held = [rate["id"] if isinstance(rate, dict) else rate for rate in item.get("tax_rates") or []]
        sales.append((price, item.get("quantity") or 1, held, _item_sale(subscription, {"price": {"id": price}})))
    # What a renewal of that phase charges, net: the 400 € of the simplified invoice is on the whole of it.
    recurring = sum((sale.net for _price, _quantity, _held, sale in sales if sale is not None), Decimal("0"))
    items = []
    changed = False
    for price, quantity, held, sale in sales:
        due = held
        if sale is not None:
            try:
                due = stripe_sales.price_sale(hub, sale, recurring_net=recurring, renewing=True)
            except Conflict as refused:
                _retax_refused(hub, sale.kind, refused)
                return None
        changed = changed or sorted(held) != sorted(due)
        items.append({"price": price, "quantity": quantity, "tax_rates": due})
    return items, changed


def _restated_phase(phase: dict, items: list[dict]) -> dict:
    restated = {"items": items, "start_date": phase["start_date"], "proration_behavior": "none"}
    if phase.get("end_date") is not None:
        restated["end_date"] = phase["end_date"]
    if phase.get("trial_end"):
        restated["trial_end"] = phase["trial_end"]
    restated["discounts"] = discounts.held_discounts(phase)
    return restated


def retax_payer(profile_id) -> None:
    """After the owner saves the billing details (on commit): the payer's Stripe customer takes them
    and every business this payer pays is retaxed. A failure is logged and never
    stops the other: the next checkout brings the customer up to date (``ensure_customer``), the daily pass
    (``retax_subscriptions``) retaxes again."""
    paid = list(Hub.objects.filter(billing_profile_id=profile_id).order_by("pk"))
    try:
        stripe_customers.push_payer_to_stripe(profile_id)
    except Exception:  # noqa: BLE001 - the save stands; the next checkout updates the customer
        logger.exception(
            "[BILLING] The Stripe customer of payer %s did not take the new billing details",
            profile_id,
            extra={"event": "billing.customer_push_failed", "hub_id": str(paid[0].id) if paid else ""},
        )
    for hub in paid:
        try:
            retax_subscription(hub)
        except Exception:  # noqa: BLE001 - the save stands; the daily pass retaxes it
            logger.exception(
                "[BILLING] Hub %s could not be retaxed after its billing details changed",
                hub.id,
                extra={"event": "billing.retax_failed", "hub_id": str(hub.id)},
            )


def retax_live_subscriptions() -> Counter:
    """One daily pass: every live Stripe subscription takes the rates of today (an address change whose push
    failed, the OSS threshold crossed or a new year back to origin, a rate the table schedules). One business
    never stops the others."""
    counts = Counter({key: 0 for key in RETAX_COUNTS})
    live = (
        Subscription.objects.filter(status__in=RETAX_STATUSES)
        .exclude(stripe_subscription_id="")
        .select_related("hub")
        .order_by("pk")
    )
    for subscription in live:
        try:
            counts[retax_subscription(subscription.hub)] += 1
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception(
                "[BILLING] %s could not be retaxed",
                subscription.stripe_subscription_id,
                extra={"event": "billing.retax_failed", "hub_id": str(subscription.hub_id)},
            )
            counts["errors"] += 1
    return counts


# --- saas-cron: manage.py sweep_unpaid ----------------------------------------------------------------

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


def sweep_unpaid() -> Counter:  # noqa: C901, PLR0912, PLR0915
    """One pass of ``sweep_unpaid``: every business in dunning still running is replayed with its
    OLDEST open invoice through ``invoice_payment_failed`` (the live subscription decides; ``unpaid`` at once,
    else past the grace; one suspension), and the Stripe subscription of every deleted business is
    cancelled now. One business never stops the others; Stripe missing or failing for one is an error."""
    counts = Counter({key: 0 for key in SWEEP_COUNTS})
    configured = stripe_service.key_mode() is not StripeKeyMode.UNKNOWN
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
                invoice_payment_failed(
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
    # The businesses suspended too long: the notices of day 30 and 150 and the deletion
    # on day 180, which the loop below ends in Stripe in this same pass.
    counts.update(suspensions.age_suspended())
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
    # The payers of deleted accounts, once nothing more can be charged to them.
    departed = BillingProfile.objects.filter(forget_after__isnull=False).order_by("pk").values_list("pk", flat=True)
    for profile_id in list(departed):
        try:
            outcome = forget_departed_payer(profile_id)
        except Exception:  # noqa: BLE001 - one payer never stops the pass; it is retried on the next one
            logger.exception("[UNPAID SWEEP] The payer %s of a deleted account could not be forgotten", profile_id)
            counts["errors"] += 1
            continue
        if outcome == PAYER_FORGOTTEN:
            counts["payers_forgotten"] += 1
    # A mail of the unpaid episode that could not leave is sent again here.
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


# --- The payer of an account that deleted itself ------------------------------------------------------
#
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
            invoice_voided(stripe_service.void_invoice(stripe_invoice_id))
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


# --- ERPlora's invoices: the number -------------------------------------------------------------------

#: The series of each kind of document: a rectifying invoice has its own (RD 1619/2012, art. 15.5).
INVOICE_SERIES = {Invoice.Kind.INVOICE: "ERP", Invoice.Kind.CREDIT_NOTE: "ERPR"}


def invoice_today() -> date:
    """The issue date of an invoice numbered now (the tests set it)."""
    return timezone.localdate()


def issue_number(kind: str) -> tuple[str, int, str, date]:
    """The next number of ``kind``'s series and its issue date: ``(series, sequence, "ERP-2026-00123", date)``.

    ``fiscal_counter``: the series' row is locked in the transaction that records the
    invoice, and only then the date is read, so a number that waited for another one never carries an earlier
    date; a new year starts at 1. A second invoice waits for the first one's COMMIT, and a
    ROLLBACK gives the number back: no gap, no duplicate (a Postgres sequence would leave a hole). Refused
    outside a transaction: a number given alone is a hole the day its invoice fails.
    """
    if connection.get_autocommit():
        raise RuntimeError("An invoice number is only given inside the transaction that records its invoice")
    series = INVOICE_SERIES[kind]
    table = InvoiceCounter._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table} (id, series, year, last_number) VALUES (%s, %s, 0, 0) ON CONFLICT (series) DO NOTHING",
            [uuid.uuid7(), series],
        )
        cursor.execute(f"SELECT year, last_number FROM {table} WHERE series = %s FOR UPDATE", [series])
        year, last_number = cursor.fetchone()
        on = invoice_today()
        sequence = last_number + 1 if year == on.year else 1
        cursor.execute(
            f"UPDATE {table} SET year = %s, last_number = %s WHERE series = %s RETURNING last_number",
            [on.year, sequence, series],
        )
        sequence = cursor.fetchone()[0]
    return series, sequence, f"{series}-{on.year}-{sequence:05d}", on


# --- ERPlora's invoices: recorded from Stripe ---------------------------------------------------------
#
# The Stripe receipt is not the legal invoice. A paid Stripe invoice becomes ERPlora's ``Invoice`` in the
# webhook's transaction (the row is what makes it durable), numbered here and issued by ERPlora's platform
# hub, which chains it in VeriFactu (``post_platform_invoice``, after the COMMIT). An unpaid one is listed
# without a number («Not collected», «Pay»); a credit note is a rectifying invoice of its own series.


def _with_all_lines(invoice: dict) -> dict:
    """The Stripe invoice with every line in ``lines.data`` (the event embeds only the first ones)."""
    lines = stripe_service.invoice_lines(invoice)
    return {**invoice, "lines": {"object": "list", "data": lines, "has_more": False}}


class VatProofUnavailable(Exception):
    """VIES could not answer and no verdict on file says how the payer's VAT number stood when it was charged:
    the invoice waits (the webhook answers 500 and Stripe retries) rather than guess."""


def _payer_clearance(hub: Hub, charged_at: datetime) -> tuple[bool, str]:
    """Whether the payer's VAT number grants the reverse charge on a sale charged at ``charged_at``, and the
    VIES consultation number that proves it. Asked before the business is locked (VIES may take seconds).

    Judged as of the charge: the last verdict VIES gave until then decides, even one older
    than the 30 days a SALE trusts (the proof travels with the invoice; a later outage of VIES cannot turn a
    verified intra-EU B2B sale into a Spanish one). With no verdict before the charge, VIES is asked now; if it
    cannot answer, ``VatProofUnavailable``: never Spanish VAT because VIES was down. Only a number of ANOTHER
    member state is ever judged: a national or a non-EU one cannot be reverse charged."""
    profile = hub.billing_profile
    if profile is None or not profile.tax_id:
        return False, ""
    country = (profile.billing_country or "").strip().upper()
    issuer = vat_clearance._issuer_country()
    value = vies.with_country_prefix(profile.tax_id, country, issuer_country=issuer)
    if (
        not value
        or country == issuer
        or country not in vat.EU_VAT_RATES
        or vies.is_uk_vat_number(value)
        or vies.is_domestic_vat_number(value, issuer_country=issuer, customer_country=country)
    ):
        return False, ""
    verdict = queries.vat_verdict_as_of(value, charged_at)
    if verdict is not None:
        if verdict.status == VatCheck.VERIFIED:
            return True, verdict.consultation_number
        return False, ""
    clearance = vat_clearance.clear_tax_id_for_stripe(value, customer_country=country)
    if clearance.verified:
        return True, (clearance.check.consultation_number if clearance.check is not None else "")
    if clearance.status == vat_clearance.CLEARANCE_INVALID:
        return False, ""
    logger.error(
        "[INVOICE] VIES cannot answer about %s and nothing on file proves it: the invoice of hub %s waits",
        value, hub.id, extra={"event": "billing.invoice_waits_for_vies"},
    )
    raise VatProofUnavailable(value)


def _moment_or_none(value) -> datetime | None:
    return stripe_sync._moment(int(value)) if value else None


def _price_of(line: dict) -> str:
    """The Stripe price a line bills: under ``pricing.price_details`` since the 2025 API, ``price`` before."""
    price = ((line.get("pricing") or {}).get("price_details") or {}).get("price") or line.get("price") or ""
    return price.get("id", "") if isinstance(price, dict) else price


def _is_proration(line: dict) -> bool:
    details = (line.get("parent") or {}).get("subscription_item_details") or {}
    return bool(details.get("proration") or line.get("proration"))


def _line_tax_cents(line: dict) -> int:
    """The tax Stripe charged on a line (``taxes`` since the 2025 API, ``tax_amounts`` before)."""
    taxes = line.get("taxes")
    if taxes is None:
        taxes = line.get("tax_amounts") or []
    return sum(int(tax.get("amount") or 0) for tax in taxes)


def _item_of(price_id: str) -> tuple[str, str, str]:
    """What a line sells: ``(kind, slug, tax category)``."""
    if (found := queries.plan_for_price(price_id)) is not None:
        return InvoiceLine.ItemKind.PLAN, found[0].slug, vat.SAAS_SUBSCRIPTION_CATEGORY
    if (found := queries.module_for_price(price_id)) is not None:
        return InvoiceLine.ItemKind.MODULE, found[0].slug, vat.SOFTWARE_LICENSE_CATEGORY
    return InvoiceLine.ItemKind.OTHER, "", vat.SAAS_SUBSCRIPTION_CATEGORY


def _nominal_rate(breakdown: vat.VatBreakdown, category: str) -> Decimal:
    """The rate of the rule in force for what is sold where the sale is taxed (the declared rate: Stripe's
    effective one moves a hundredth with the rounding)."""
    rate = vat.vat_rate_for(country=breakdown.tax_country, region=breakdown.tax_region, category_key=category)
    return rate if rate is not None else breakdown.rate


def _sealed_amounts(amount: int, tax: int, *, treatment: str, rate: Decimal, reconciled: bool) -> tuple[Decimal, int, int]:
    """``(rate, net, tax)`` of a line in cents, by the qualification of the sale: without a rate (reverse
    charge, not subject) all of it is base; reconciled (Stripe charged no tax on a subject sale) the VAT comes
    out of the amount charged; otherwise Stripe's amounts rule."""
    if treatment not in vat.TREATMENTS_WITH_RATE:
        return Decimal("0.00"), amount + tax, 0
    if reconciled:
        base, _quota = vat.split_gross(from_cents(amount + tax), rate)
        net = to_cents(base)
        return rate, net, amount + tax - net
    return rate, amount, tax


def _payer_snapshot(hub: Hub, *, verified: bool, consultation: str) -> dict:
    """The payer as it is today (``hubs.BillingProfile``), copied onto the invoice: an edit of the profile
    never rewrites an issued invoice."""
    profile = hub.billing_profile
    if profile is None:
        return {"payer_name": "", "language": hub.language or settings.LANGUAGE_CODE}
    owner = profile.owner
    country = (profile.billing_country or "").strip().upper()
    tax_id = vies.normalise(profile.tax_id)
    return {
        "billing_profile": profile,
        "payer_account": owner,
        "payer_name": profile.billing_name or (owner.get_full_name() if owner else "") or "",
        "payer_tax_id": tax_id,
        "payer_tax_id_type": vat.tax_id_type_for(country) if tax_id else "",
        "payer_tax_id_verified": verified,
        "vat_consultation_number": consultation if verified else "",
        "payer_address": profile.billing_address or "",
        "payer_city": profile.billing_city or "",
        "payer_postal_code": (profile.billing_postal_code or "").strip().upper(),
        "payer_country": country,
        "payer_email": profile.billing_email or (owner.email if owner else ""),
        "language": (getattr(owner, "language", "") or hub.language or settings.LANGUAGE_CODE),
    }


@operation(
    "billing.invoice.record",
    kind="command",
    permission="billing.manage",
    input=InvoiceRecordIn,
    output=InvoiceRecordOut,
    ai=INTERNAL,  # platform
)
def invoice_record(ctx: OperationContext, data: InvoiceRecordIn) -> dict:
    """The webhook's door to ERPlora's invoices (the platform only; no route): a Stripe invoice of a
    business, ``open`` (listed, not collected), ``paid`` (numbered and issued) or ``void`` (Stripe gave up).
    Idempotent by the Stripe invoice: a paid one is never recorded twice, nor reopened."""
    hub = Hub.objects.select_related("billing_profile__owner").get(pk=data.hub_id)
    stripe_invoice = data.invoice
    existing = (
        Invoice.objects.select_for_update()
        .filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice.get("id") or "")
        .first()
    )
    if data.status == "void":
        return _void(ctx, existing)
    if existing is not None and existing.payment_status == Invoice.PaymentStatus.PAID:
        return _record_out(existing, "duplicate")
    total = int(stripe_invoice.get("total") or 0)
    if total < 0 and data.status == "paid":
        return _record_negative(ctx, hub, stripe_invoice)
    if total <= 0 and not invoice_discounts.is_fully_discounted(stripe_invoice):
        return _record_out(existing, "ignored")
    if data.status == "open":
        return _record_open(ctx, hub, stripe_invoice, existing)
    return _record_paid(ctx, hub, data, existing)


def _record_out(invoice: Invoice | None, outcome: str) -> dict:
    return {
        "id": invoice.id if invoice else None,
        "number": invoice.number if invoice else "",
        "payment_status": invoice.payment_status if invoice else "",
        "outcome": outcome,
    }


def _stripe_fields(stripe_invoice: dict) -> dict:
    return {
        "stripe_number": (stripe_invoice.get("number") or "")[:64],
        "hosted_invoice_url": stripe_invoice.get("hosted_invoice_url") or "",
        "billed_at": _moment_or_none(stripe_invoice.get("created")),
        "currency": (stripe_invoice.get("currency") or "eur").upper(),
    }


def _record_open(ctx, hub: Hub, stripe_invoice: dict, existing: Invoice | None) -> dict:
    """An unpaid Stripe invoice, listed with what it asks (no number: one is given at the payment)."""
    if existing is not None:
        if existing.payment_status == Invoice.PaymentStatus.OPEN:
            Invoice.objects.filter(pk=existing.pk).update(
                hosted_invoice_url=stripe_invoice.get("hosted_invoice_url") or existing.hosted_invoice_url,
                updated_at=timezone.now(),
            )
        return _record_out(existing, "duplicate")
    total = int(stripe_invoice["total"])
    tax = plan_changes.tax_cents_of(stripe_invoice)
    profile = hub.billing_profile
    listed = Invoice.objects.create(
        kind=Invoice.Kind.INVOICE,
        hub=hub,
        business_name=hub.name,
        billing_profile=profile,
        payer_account=profile.owner if profile else None,
        stripe_invoice_id=stripe_invoice["id"],
        payment_status=Invoice.PaymentStatus.OPEN,
        net_cents=total - tax,
        tax_cents=tax,
        total_cents=total,
        **_stripe_fields(stripe_invoice),
    )
    _record_invoice_event(ctx, listed, events.INVOICE_RECORDED,
                          {"id": str(listed.id), "hub_id": str(hub.id), "payment_status": "open"})
    return _record_out(listed, "listed")


def _void(ctx, existing: Invoice | None) -> dict:
    """Stripe voided (or gave up on) an unpaid invoice: it leaves «not collected». A paid one never changes."""
    if existing is None or existing.payment_status != Invoice.PaymentStatus.OPEN:
        return _record_out(existing, "ignored")
    Invoice.objects.filter(pk=existing.pk).update(payment_status=Invoice.PaymentStatus.VOID, updated_at=timezone.now())
    _record_invoice_event(ctx, existing, events.INVOICE_VOIDED, {"id": str(existing.id), "hub_id": str(existing.hub_id)})
    existing.payment_status = Invoice.PaymentStatus.VOID
    return _record_out(existing, "voided")


def _sealed_line(position: int, line: dict, breakdown: vat.VatBreakdown) -> InvoiceLine:
    """A Stripe line as a line of ERPlora's invoice: what it sells, its discount and its base, rate and quota sealed."""
    kind, slug, category = _item_of(_price_of(line))
    amount, discount = invoice_discounts.line_amounts(line)
    rate, net, tax = _sealed_amounts(
        amount,
        _line_tax_cents(line),
        treatment=breakdown.treatment,
        rate=_nominal_rate(breakdown, category) if breakdown.is_subject else Decimal("0.00"),
        reconciled=breakdown.vat_included_reconciled,
    )
    period = line.get("period") or {}
    return InvoiceLine(
        position=position,
        description=(line.get("description") or slug or _("Subscription"))[:255],
        item_kind=kind,
        item_slug=slug,
        quantity=max(int(line.get("quantity") or 1), 1),
        proration=_is_proration(line),
        period_start=_moment_or_none(period.get("start")),
        period_end=_moment_or_none(period.get("end")),
        tax_category_id=category,
        tax_treatment=breakdown.treatment,
        tax_rate=rate,
        net_cents=net,
        tax_cents=tax,
        total_cents=net + tax,
        discount_cents=discount,
        stripe_line_id=line.get("id") or "",
    )


def _record_paid(ctx, hub: Hub, data: InvoiceRecordIn, existing: Invoice | None) -> dict:
    """A paid Stripe invoice becomes ERPlora's invoice: the payer sealed, the qualification of the sale and
    each line's base, rate and quota sealed, the next number of the series; issued after the COMMIT."""
    stripe_invoice = data.invoice
    total = int(stripe_invoice["total"])
    payer = queries.payer_of(hub)
    breakdown = vat.resolve_vat(
        from_cents(total),
        customer_country=payer.country,
        customer_postal_code=payer.postal_code,
        customer_tax_id=payer.tax_id,
        customer_tax_id_type=payer.tax_id_type,
        customer_tax_id_verified=data.tax_id_verified,
        category_key=vat.SAAS_SUBSCRIPTION_CATEGORY,
        tax_cents=plan_changes.tax_cents_of(stripe_invoice),
        tax_included=False,
    )
    lines = [
        _sealed_line(position, line, breakdown)
        for position, line in enumerate((stripe_invoice.get("lines") or {}).get("data") or [], start=1)
    ]
    if not lines:
        # Stripe always bills a line; without one the whole amount is one line of the subscription.
        lines.append(
            InvoiceLine(
                position=1,
                description=_("Subscription"),
                tax_category_id=vat.SAAS_SUBSCRIPTION_CATEGORY,
                tax_treatment=breakdown.treatment,
                tax_rate=breakdown.rate,
                net_cents=to_cents(breakdown.base),
                tax_cents=to_cents(breakdown.tax),
                total_cents=total,
            )
        )
    net_cents = sum(line.net_cents for line in lines)
    tax_cents = sum(line.tax_cents for line in lines)
    _require_adds_up(stripe_invoice.get("id"), net_cents + tax_cents, total, hub.id)
    now = timezone.now()
    series, sequence, number, today = issue_number(Invoice.Kind.INVOICE)
    values = {
        "kind": Invoice.Kind.INVOICE,
        "hub": hub,
        "business_name": hub.name,
        "stripe_invoice_id": stripe_invoice["id"],
        **_stripe_fields(stripe_invoice),
        **_payer_snapshot(hub, verified=data.tax_id_verified, consultation=data.vat_consultation_number),
        "series": series,
        "sequence": sequence,
        "number": number,
        "issued_on": today,
        "payment_status": Invoice.PaymentStatus.PAID,
        "paid_at": _moment_or_none((stripe_invoice.get("status_transitions") or {}).get("paid_at")) or now,
        "net_cents": net_cents,
        "tax_cents": tax_cents,
        "total_cents": net_cents + tax_cents,
        "tax_treatment": breakdown.treatment,
        "tax_country": breakdown.tax_country,
        "tax_rate": _nominal_rate(breakdown, vat.SAAS_SUBSCRIPTION_CATEGORY) if breakdown.is_subject else Decimal("0.00"),
        "vat_included_reconciled": breakdown.vat_included_reconciled,
        "fiscal_status": Invoice.FiscalStatus.ISSUING,
        "fiscal_status_at": now,
        "next_post_at": now,
    }
    if existing is None:
        invoice = Invoice.objects.create(**values)
    else:
        invoice = existing
        for field, value in values.items():
            setattr(invoice, field, value)
        invoice.save()
        invoice.lines.all().delete()
    for line in lines:
        line.invoice = invoice
    InvoiceLine.objects.bulk_create(lines)
    _record_invoice_event(ctx, invoice, events.INVOICE_RECORDED,
                          {"id": str(invoice.id), "hub_id": str(hub.id), "payment_status": "paid"})
    transaction.on_commit(partial(_post_quietly, invoice.id), robust=True)
    _note_oss_threshold_quietly(invoice)
    return _record_out(invoice, "numbered")


# --- The team's notices of the OSS threshold ----------------------------------------------------------

#: The share of the threshold whose passing tells the team to register in the OSS (it takes days).
OSS_WARNING_PERCENT = 80


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
    from billing import emails

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


class InvoiceDoesNotAddUp(Exception):
    """The lines of a Stripe document do not add up to what it charged or credited: nothing is invoiced (a 500
    for Stripe's retry and support's ERROR), never a different amount."""


class RectifiedInvoiceMissing(Exception):
    """A credit note, a refund or a negative invoice whose invoice ERPlora has not recorded (yet): Stripe does not
    order its events, so the webhook answers 500 and Stripe retries."""


def _require_adds_up(source, lines_total: int, stripe_total: int, hub_id) -> None:
    if lines_total != stripe_total:
        logger.error(
            "[INVOICE] The lines of Stripe's %s add up to %s, Stripe charged %s: nothing is invoiced",
            source, lines_total, stripe_total,
            extra={"event": "fiscal.invoice.lines_do_not_add_up", "hub_id": str(hub_id)},
        )
        raise InvoiceDoesNotAddUp(source)


def rectification_type(reason: str | None) -> str:
    """VeriFactu's type of a rectifying invoice for Stripe's reason: a refund, a duplicate, a price change or an
    order change modify the base (art. 80.1, 80.2 LIVA, or an error): R1; a fraudulent charge, R4 (other)."""
    return Invoice.RectificationType.R4 if reason == "fraudulent" else Invoice.RectificationType.R1


def _rectifying_lines(original: Invoice, items: list[dict]) -> list[InvoiceLine]:
    """The lines of a rectifying invoice, negative where they give money back, sealed with the qualification of
    the invoice they rectify (a rectifying invoice keeps it) and the rate of the line they correct. ``items``:
    ``{amount, tax, description, quantity, price, stripe_line_id, split}``; ``split`` = the amount has the VAT
    inside (a refund): it is taken out at that rate."""
    sources = list(original.lines.all())
    lines = []
    for position, item in enumerate(items, start=1):
        kind, slug, category = _item_of(item.get("price") or "")
        source = next((line for line in sources if line.stripe_line_id and line.stripe_line_id == item.get("source_line")), None)
        source = source or next((line for line in sources if slug and line.item_slug == slug), None)
        rate, net, tax = _sealed_amounts(
            item["amount"],
            item["tax"],
            treatment=original.tax_treatment,
            rate=source.tax_rate if source is not None else original.tax_rate,
            reconciled=item.get("split", False) or (original.vat_included_reconciled and not item["tax"]),
        )
        lines.append(
            InvoiceLine(
                position=position,
                description=(item.get("description") or (source.description if source else "") or _("Credit"))[:255],
                item_kind=source.item_kind if source else kind,
                item_slug=source.item_slug if source else slug,
                quantity=max(int(item.get("quantity") or 1), 1),
                proration=bool(item.get("proration")),
                period_start=item.get("period_start") or (source.period_start if source else None),
                period_end=item.get("period_end") or (source.period_end if source else None),
                tax_category_id=source.tax_category_id if source else category,
                tax_treatment=original.tax_treatment,
                tax_rate=rate,
                net_cents=net,
                tax_cents=tax,
                total_cents=net + tax,
                stripe_line_id=item.get("stripe_line_id") or "",
            )
        )
    return lines


def _rectify(ctx, original: Invoice, *, source_id: str, items: list[dict], expected_total: int, rtype: str,  # noqa: PLR0913
             reason: str, stripe_number: str = "", billed_at: datetime | None = None) -> dict:
    """A rectifying invoice of ``original`` (``ERPR`` series, its qualification and recipient), once per Stripe
    ``source_id``; its lines must add up to what Stripe gave back, or nothing is invoiced. Issued after the
    COMMIT."""
    existing = Invoice.objects.filter(kind=Invoice.Kind.CREDIT_NOTE, stripe_source_id=source_id).first()
    if existing is not None:
        return _record_out(existing, "duplicate")
    lines = _rectifying_lines(original, items)
    net_cents = sum(line.net_cents for line in lines)
    tax_cents = sum(line.tax_cents for line in lines)
    _require_adds_up(source_id, net_cents + tax_cents, expected_total, original.hub_id)
    now = timezone.now()
    series, sequence, number, today = issue_number(Invoice.Kind.CREDIT_NOTE)
    copied = {
        field: getattr(original, field)
        for field in (
            "hub_id", "business_name", "billing_profile_id", "payer_account_id", "payer_name", "payer_tax_id",
            "payer_tax_id_type", "payer_tax_id_verified", "vat_consultation_number", "payer_address", "payer_city",
            "payer_postal_code", "payer_country", "payer_email", "language", "currency", "tax_treatment",
            "tax_country", "tax_rate", "stripe_invoice_id",
        )
    }
    rectifying = Invoice.objects.create(
        kind=Invoice.Kind.CREDIT_NOTE,
        rectifies=original,
        stripe_source_id=source_id,
        stripe_number=(stripe_number or "")[:64],
        billed_at=billed_at,
        rectification_type=rtype,
        rectification_reason=(reason or "")[:255],
        series=series,
        sequence=sequence,
        number=number,
        issued_on=today,
        payment_status=Invoice.PaymentStatus.PAID,
        paid_at=now,
        net_cents=net_cents,
        tax_cents=tax_cents,
        total_cents=net_cents + tax_cents,
        fiscal_status=Invoice.FiscalStatus.ISSUING,
        fiscal_status_at=now,
        next_post_at=now,
        **copied,
    )
    for line in lines:
        line.invoice = rectifying
    InvoiceLine.objects.bulk_create(lines)
    _record_invoice_event(ctx, rectifying, events.CREDIT_NOTE_RECORDED, {"id": str(rectifying.id),
                                                                         "rectifies": str(original.id)})
    transaction.on_commit(partial(_post_quietly, rectifying.id), robust=True)
    return _record_out(rectifying, "numbered")


def _stripe_items(stripe_lines: list[dict], *, sign: int) -> list[dict]:
    """Stripe's lines (of an invoice or a credit note) as the items of a rectifying invoice; ``sign`` -1 for a
    credit note, whose amounts Stripe gives positive."""
    items = []
    for line in stripe_lines:
        period = line.get("period") or {}
        items.append(
            {
                "amount": sign * int(line.get("amount") or 0),
                "tax": sign * _line_tax_cents(line),
                "description": line.get("description") or "",
                "quantity": line.get("quantity") or 1,
                "price": _price_of(line),
                "proration": _is_proration(line),
                "period_start": _moment_or_none(period.get("start")),
                "period_end": _moment_or_none(period.get("end")),
                "source_line": line.get("invoice_line_item") or "",
                "stripe_line_id": line.get("id") or "",
            }
        )
    return items


def _record_negative(ctx, hub: Hub, stripe_invoice: dict) -> dict:
    """A Stripe invoice of a negative total (a proration credit larger than what it bills; legacy or manual:
    downgrades wait for the end of the period) rectifies the invoice whose period its credited lines belong to
    R1, a modification of the price (art. 80.2 LIVA)."""
    lines = (stripe_invoice.get("lines") or {}).get("data") or []
    credited = [
        _moment_or_none((line.get("period") or {}).get("start"))
        for line in lines
        if int(line.get("amount") or 0) < 0
    ]
    moment = min((when for when in credited if when is not None), default=None)
    found = (
        InvoiceLine.objects.select_related("invoice")
        .filter(
            invoice__hub=hub,
            invoice__kind=Invoice.Kind.INVOICE,
            invoice__payment_status=Invoice.PaymentStatus.PAID,
            period_start__lte=moment,
            period_end__gt=moment,
        )
        .order_by("-invoice__issued_on", "-invoice__sequence")
        .first()
        if moment is not None
        else None
    )
    if found is None:
        logger.error(
            "[INVOICE] Stripe invoice %s of hub %s credits a period ERPlora has not invoiced",
            stripe_invoice.get("id"), hub.id, extra={"event": "fiscal.credit.unknown_invoice"},
        )
        raise RectifiedInvoiceMissing(stripe_invoice.get("id"))
    return _rectify(
        ctx,
        found.invoice,
        source_id=stripe_invoice["id"],
        items=_stripe_items(lines, sign=1),
        expected_total=int(stripe_invoice["total"]),
        rtype=Invoice.RectificationType.R1,
        reason=stripe_invoice.get("description") or "proration",
        stripe_number=stripe_invoice.get("number") or "",
        billed_at=_moment_or_none(stripe_invoice.get("created")),
    )


def invoice_voided(stripe_invoice: dict) -> str:
    """Stripe voided an unpaid invoice, or gave up on it (``marked_uncollectible``): it leaves «not collected»
    (it is no longer payable). An invoice ERPlora does not list is ignored."""
    listed = (
        Invoice.objects.filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice.get("id") or "")
        .values_list("hub_id", "payment_status")
        .first()
    )
    if listed is None or listed[1] != Invoice.PaymentStatus.OPEN or listed[0] is None:
        return "ignored"
    out = invoice_record(
        hub_callbacks.system_ctx_for(listed[0]), InvoiceRecordIn(hub_id=listed[0], invoice=stripe_invoice, status="void")
    )
    return "processed" if out.outcome == "voided" else "ignored"


# --- Credit notes and refunds: rectifying invoices -------------------------------------------------------


def _issued_invoice(stripe_invoice_id: str) -> Invoice | None:
    return (
        Invoice.objects.filter(
            kind=Invoice.Kind.INVOICE, stripe_invoice_id=stripe_invoice_id, payment_status=Invoice.PaymentStatus.PAID
        )
        .only("id", "hub_id", "payer_account_id")
        .first()
    )


def _missing_original(what: str, stripe_invoice_id: str):
    logger.error(
        "[INVOICE] %s rectifies Stripe invoice %s, which ERPlora has not invoiced (yet): Stripe retries",
        what, stripe_invoice_id, extra={"event": "fiscal.credit.unknown_invoice"},
    )
    return RectifiedInvoiceMissing(stripe_invoice_id)


def credit_note_created(credit_note: dict) -> str:
    """A credit note of a paid invoice (``credit_note.created``) becomes a rectifying invoice of its own series.
    Ahead of its invoice (Stripe does not order events) it raises: Stripe retries."""
    rectified = credit_note.get("invoice") or ""
    if isinstance(rectified, dict):
        rectified = rectified.get("id") or ""
    original = _issued_invoice(rectified)
    if original is None:
        raise _missing_original(f"Credit note {credit_note.get('id')}", rectified)
    # The event is a snapshot of when it was created: a note voided since (``credit_note.voided``, possible while its
    # invoice was open, when this event was still waiting for it) is no rectification, so it is read LIVE.
    if stripe_service.retrieve_credit_note(credit_note["id"]).get("status") == "void":
        logger.warning("[INVOICE] Credit note %s was voided in Stripe: no rectifying invoice", credit_note["id"])
        return "ignored"
    lines = stripe_service.credit_note_lines(credit_note)
    credit_note_record(
        _invoice_ctx(original),
        CreditNoteRecordIn(credit_note={**credit_note, "lines": {"object": "list", "data": lines, "has_more": False}}),
    )
    return "processed"


def credit_note_voided(credit_note: dict) -> str:
    """A credit note voided in Stripe (``credit_note.voided``). Stripe voids one only while its invoice is
    OPEN, and a rectifying invoice is recorded here only for a PAID one, so normally there is none: ``voided``, and its
    ``credit_note.created`` never records it (read live there). Nothing fiscal is done on its own: a rectifying
    invoice recorded anyway is never modified (a record sent to the AEAT is corrected with a new one) and the team is
    told by mail to correct it by hand: ``needs_review``. A mail that cannot leave raises, so Stripe retries it."""
    from billing import emails

    rectifying = (
        Invoice.objects.filter(kind=Invoice.Kind.CREDIT_NOTE, stripe_source_id=credit_note.get("id") or "")
        .only("id", "number", "series", "sequence", "fiscal_status", "rectifies_id", "total_cents")
        .first()
    )
    if rectifying is None:
        logger.info("[INVOICE] Credit note %s voided in Stripe: it was never a rectifying invoice", credit_note.get("id"))
        return "voided"
    logger.error(
        "[INVOICE] Credit note %s voided in Stripe after it became rectifying invoice %s: correct it by hand",
        credit_note.get("id"), rectifying.number, extra={"event": "fiscal.credit.voided_after_rectifying"},
    )
    emails.send_credit_note_voided(rectifying, credit_note.get("id") or "")
    return "needs_review"


@operation(
    "billing.credit_note.record",
    kind="command",
    permission="billing.manage",
    input=CreditNoteRecordIn,
    output=InvoiceRecordOut,
    ai=INTERNAL,  # platform
)
def credit_note_record(ctx: OperationContext, data: CreditNoteRecordIn) -> dict:
    """A Stripe credit note as a rectifying invoice (the platform only; no route): negative amounts, the
    qualification and the payer of the invoice it rectifies, its type (``rectification_type``) and reason
    (the memo, or Stripe's reason); issued after the COMMIT. Idempotent by the credit note."""
    credit_note = data.credit_note
    rectified = credit_note.get("invoice") or ""
    if isinstance(rectified, dict):
        rectified = rectified.get("id") or ""
    original = (
        Invoice.objects.select_for_update()
        .filter(kind=Invoice.Kind.INVOICE, stripe_invoice_id=rectified, payment_status=Invoice.PaymentStatus.PAID)
        .first()
    )
    if original is None:
        raise _missing_original(f"Credit note {credit_note.get('id')}", rectified)
    lines = (credit_note.get("lines") or {}).get("data") or []
    items = _stripe_items(lines, sign=-1) or [
        {"amount": -(int(credit_note.get("total") or 0) - plan_changes.tax_cents_of(credit_note)), "tax": -plan_changes.tax_cents_of(credit_note)}
    ]
    return _rectify(
        ctx,
        original,
        source_id=credit_note["id"],
        items=items,
        expected_total=-int(credit_note.get("total") or 0),
        rtype=rectification_type(credit_note.get("reason")),
        reason=credit_note.get("memo") or credit_note.get("reason") or "credit_note",
        stripe_number=credit_note.get("number") or "",
        billed_at=_moment_or_none(credit_note.get("created")),
    )


def charge_refunded(charge: dict) -> str:
    """Money given back without a credit note (``charge.refunded``; a refund in the Dashboard): each refund is a
    rectifying invoice of the invoice the charge paid, its gross split at that invoice's rate.
    A refund a credit note covers is that credit note's; one still pending waits for its next event; a charge
    that paid no invoice of Stripe is not ours."""
    intent = charge.get("payment_intent") or ""
    if isinstance(intent, dict):
        intent = intent.get("id") or ""
    stripe_invoice_id = stripe_service.invoice_paid_by(intent) if intent else None
    if not stripe_invoice_id:
        return "ignored"
    original = _issued_invoice(stripe_invoice_id)
    if original is None:
        raise _missing_original(f"Refund of charge {charge.get('id')}", stripe_invoice_id)
    covered = stripe_service.credit_note_refund_ids(stripe_invoice_id)
    for refund in stripe_service.charge_refunds(charge["id"]):
        if refund.get("status") != "succeeded" or refund["id"] in covered:
            continue
        refund_record(_invoice_ctx(original), RefundRecordIn(invoice_id=original.id, refund=refund))
    return "processed"


@operation(
    "billing.refund.record",
    kind="command",
    permission="billing.manage",
    input=RefundRecordIn,
    output=InvoiceRecordOut,
    ai=INTERNAL,  # platform
)
def refund_record(ctx: OperationContext, data: RefundRecordIn) -> dict:
    """A Stripe refund without a credit note as a rectifying invoice of ``invoice_id`` (the platform only; no
    route): one line with the gross refunded, the VAT taken out at the invoice's rate. Idempotent by the refund."""
    original = Invoice.objects.select_for_update().get(pk=data.invoice_id)
    refund = data.refund
    amount = int(refund.get("amount") or 0)
    return _rectify(
        ctx,
        original,
        source_id=refund["id"],
        items=[{"amount": -amount, "tax": 0, "description": _("Refund"), "split": True}],
        expected_total=-amount,
        rtype=rectification_type(refund.get("reason")),
        reason=refund.get("reason") or "refund",
        billed_at=_moment_or_none(refund.get("created")),
    )


def _record_invoice_event(ctx: OperationContext, invoice: Invoice, name: str, payload: dict) -> None:
    """Record an event of an invoice in the command's channel and tell, after the COMMIT, the other account that
    sees it too (its payer and its business's owner): both their Billing lists re-run."""
    record_event(ctx, name, payload)
    owner = membership.owner_id(invoice.hub_id) if invoice.hub_id else None
    viewers = {str(account) for account in (invoice.payer_account_id, owner) if account}
    for key in sorted(viewers - {ctx.scope.key}):
        transaction.on_commit(partial(notify, Scope("user", key), [name]), robust=True)


def _invoice_ctx(invoice: Invoice) -> OperationContext:
    """The platform acting on an invoice, in its payer's channel (its Billing lists re-run)."""
    if invoice.payer_account_id:
        return system_context(Scope("user", str(invoice.payer_account_id)))
    if invoice.hub_id:
        return hub_callbacks.system_ctx_for(invoice.hub_id)
    return system_context(Scope("user", "system"))


# --- The platform hub issues them ---------------------------------------------------------------------

#: What one post of an invoice came to: answered (its status stored), the Hub away (retried), the Hub
#: refusing it (kept with its code, retried: the run fails), or nothing to post (not paid).
POSTED, UNREACHABLE, REFUSED, NOTHING_TO_POST = "posted", "unreachable", "refused", "nothing_to_post"
#: The statuses the platform hub answers (``Invoice.FiscalStatus`` without «not issued»).
PLATFORM_STATUSES = frozenset({"issuing", "issued", "accepted", "accepted_with_errors", "rejected"})
#: Issued by the platform hub: it has the QR and the PDF.
ISSUED_STATUSES = frozenset({"issued", "accepted", "accepted_with_errors"})
#: The wait before posting again an invoice the Hub did not take: one ``reconcile_platform_invoices`` run
#: (15 minutes) after the first failure, doubling, never more than 6 hours.
PLATFORM_FIRST_WAIT = timedelta(minutes=15)
PLATFORM_LONGEST_WAIT = timedelta(hours=6)
#: An invoice still «issuing» after this long is stuck: the reconcile run fails (the ``task_failed`` alarm).
PLATFORM_STUCK_AFTER = timedelta(hours=1)


def platform_backoff(attempts: int) -> timedelta:
    """How long an invoice waits after its ``attempts``-th failed post."""
    return min(PLATFORM_FIRST_WAIT * 2 ** max(attempts - 1, 0), PLATFORM_LONGEST_WAIT)


def platform_payload(invoice: Invoice) -> dict:
    """The body of ``POST /internal/platform/invoices``: the whole invoice, so the platform hub issues it in
    VeriFactu and prints its PDF without asking the SaaS anything. Keyed by ``id`` (idempotent)."""
    rectified = invoice.rectifies
    return {
        "id": str(invoice.id),
        "kind": invoice.kind,
        "series": invoice.series,
        "number": invoice.number,
        "issued_on": platform_contract.day(invoice.issued_on),
        "stripe_invoice_id": invoice.stripe_invoice_id,
        "stripe_source_id": invoice.stripe_source_id,
        "rectification": (
            {"type": invoice.rectification_type, "reason": invoice.rectification_reason}
            if invoice.kind == Invoice.Kind.CREDIT_NOTE
            else None
        ),
        "currency": invoice.currency,
        "language": invoice.language,
        "net_cents": invoice.net_cents,
        "tax_cents": invoice.tax_cents,
        "total_cents": invoice.total_cents,
        "tax_treatment": invoice.tax_treatment,
        "tax_country": invoice.tax_country,
        "tax_rate": str(invoice.tax_rate),
        "vat_included_reconciled": invoice.vat_included_reconciled,
        "vat_included_because_unverified": invoice.vat_included_because_unverified,
        "business": {"id": str(invoice.hub_id) if invoice.hub_id else None, "name": invoice.business_name},
        "recipient": {
            "name": invoice.payer_name,
            "tax_id": invoice.payer_tax_id,
            "tax_id_type": invoice.payer_tax_id_type,
            "tax_id_verified": invoice.payer_tax_id_verified,
            "vat_consultation_number": invoice.vat_consultation_number,
            "address": invoice.payer_address,
            "city": invoice.payer_city,
            "postal_code": invoice.payer_postal_code,
            "country": invoice.payer_country,
            "email": invoice.payer_email,
        },
        "lines": [
            {
                "position": line.position,
                "description": line.description,
                "item_kind": line.item_kind,
                "item_slug": line.item_slug,
                "quantity": line.quantity,
                "proration": line.proration,
                "period_start": platform_contract.day(line.period_start),
                "period_end": platform_contract.day(line.period_end),
                "tax_category": line.tax_category_id,
                "tax_treatment": line.tax_treatment or invoice.tax_treatment,
                "tax_rate": str(line.tax_rate),
                "net_cents": line.net_cents,
                "tax_cents": line.tax_cents,
                "total_cents": line.total_cents,
                "discount_cents": line.discount_cents,
            }
            for line in invoice.lines.order_by("position")
        ],
        "rectifies": (
            {"id": str(rectified.id), "number": rectified.number, "issued_on": platform_contract.day(rectified.issued_on)}
            if rectified is not None
            else None
        ),
    }


def _answer_of(body) -> dict | None:
    """The platform hub's answer as ``FiscalAnswerIn``, or ``None`` for one the SaaS does not know."""
    body = body if isinstance(body, dict) else {}
    status = body.get("status")
    if status not in PLATFORM_STATUSES:
        return None
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    return {
        "status": status,
        "qr": str(body.get("qr") or ""),
        "error_code": str(error.get("code") or "")[:64],
        "error": str(error.get("message") or ""),
    }


def post_platform_invoice(invoice_id) -> str:
    """Post a paid invoice to ERPlora's platform hub (``POST /internal/platform/invoices``) and store what
    it answers. Outside any transaction (a call to the Hub never holds the database). Idempotent on the
    Hub's side by the invoice's id: posting it again answers what it has."""
    invoice = Invoice.objects.select_related("rectifies").filter(pk=invoice_id).first()
    if invoice is None or invoice.payment_status != Invoice.PaymentStatus.PAID or not invoice.number:
        return NOTHING_TO_POST
    try:
        answer = hub_client.post_platform_invoice(platform_payload(invoice))
    except HubUnavailable as failed:
        _post_failed(invoice, str(failed))
        return UNREACHABLE
    except HubRefused as refused:
        logger.error(
            "[INVOICE] The platform hub refused invoice %s: %s", invoice.number, refused,
            extra={"event": "billing.platform_invoice_refused", "code": refused.code},
        )
        _post_failed(invoice, str(refused), code=refused.code, message=refused.message)
        return REFUSED
    known = _answer_of(answer.body)
    if known is None:
        logger.error("[INVOICE] The platform hub answered %r for invoice %s", answer.body, invoice.number)
        _post_failed(invoice, f"unknown answer: {answer.body!r}"[:255])
        return UNREACHABLE
    Invoice.objects.filter(pk=invoice.pk).update(
        post_attempts=F("post_attempts") + 1, next_post_at=None, last_post_error=""
    )
    invoice_apply_fiscal_status(_invoice_ctx(invoice), FiscalAnswerIn(id=invoice.id, **known))
    return POSTED


def _post_failed(invoice: Invoice, error: str, *, code: str = "", message: str = "") -> None:
    attempts = invoice.post_attempts + 1
    logger.warning("[INVOICE] Invoice %s owed to the platform hub (attempt %s): %s", invoice.number, attempts, error)
    fields = {
        "post_attempts": attempts,
        "last_post_error": error[:255],
        "next_post_at": timezone.now() + platform_backoff(attempts),
        "updated_at": timezone.now(),
    }
    if code:
        fields.update(fiscal_error_code=code[:64], fiscal_error=message)
    Invoice.objects.filter(pk=invoice.pk).update(**fields)


def refresh_platform_invoice(invoice_id) -> str:
    """Ask the platform hub how an issued invoice stands (``GET /internal/platform/invoices/{id}``): the AEAT
    accepts or rejects it after the Hub issued it. Returns its fiscal status now, or ``unreachable`` /
    ``refused``."""
    invoice = Invoice.objects.filter(pk=invoice_id).first()
    if invoice is None:
        return NOTHING_TO_POST
    try:
        answer = hub_client.get_platform_invoice(str(invoice.id))
    except HubUnavailable:
        return UNREACHABLE
    except HubRefused as refused:
        logger.error("[INVOICE] The platform hub does not know invoice %s: %s", invoice.number, refused)
        return REFUSED
    known = _answer_of(answer.body)
    if known is None:
        logger.warning("[INVOICE] The platform hub answered %r for invoice %s", answer.body, invoice.number)
        return invoice.fiscal_status
    return invoice_apply_fiscal_status(_invoice_ctx(invoice), FiscalAnswerIn(id=invoice.id, **known)).fiscal_status


@operation(
    "billing.invoice.apply_fiscal_status",
    kind="command",
    permission="billing.manage",
    input=FiscalAnswerIn,
    output=FiscalAnswerOut,
    ai=INTERNAL,  # platform
)
def invoice_apply_fiscal_status(ctx: OperationContext, data: FiscalAnswerIn) -> dict:
    """What the platform hub says of an invoice, stored as it says it (the platform only; no route). «Issuing»
    never moves an invoice back; a rejection is an ERROR for support (the Hub corrects it with a new record,
    and its next answer replaces this one). The first time it is issued, its payer gets an e-mail."""
    invoice = Invoice.objects.select_for_update().get(pk=data.id)
    status = invoice.fiscal_status if data.status == "issuing" else data.status
    fields = {"fiscal_status": status, "qr": data.qr or invoice.qr, "fiscal_error_code": data.error_code,
              "fiscal_error": data.error}
    changed = any(getattr(invoice, field) != value for field, value in fields.items())
    if not changed:
        return {"id": invoice.id, "fiscal_status": invoice.fiscal_status, "changed": False}
    first_issue = invoice.fiscal_status not in ISSUED_STATUSES and status in ISSUED_STATUSES
    now = timezone.now()
    Invoice.objects.filter(pk=invoice.pk).update(**fields, fiscal_status_at=now, updated_at=now)
    if status == Invoice.FiscalStatus.REJECTED:
        logger.error(
            "[INVOICE] The AEAT rejected invoice %s: %s %s", invoice.number, data.error_code, data.error,
            extra={"event": "billing.platform_invoice_rejected", "invoice": invoice.number},
        )
    _record_invoice_event(ctx, invoice, events.INVOICE_FISCAL_STATUS_CHANGED, {"id": str(invoice.id), "status": status})
    if first_issue and invoice.emailed_at is None:
        transaction.on_commit(partial(_email_quietly, invoice.id), robust=True)
    return {"id": invoice.id, "fiscal_status": status, "changed": True}


def _post_quietly(invoice_id) -> None:
    try:
        post_platform_invoice(invoice_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the invoice; it stays «issuing»
        logger.exception("[INVOICE] Posting invoice %s to the platform hub crashed", invoice_id)


#: What sending the payer's mail of an invoice came to.
MAILED, MAIL_SKIPPED, MAIL_FAILED = "mailed", "mail_skipped", "mail_failed"


def send_invoice_mail(invoice_id) -> str:
    """Send the payer the mail of an issued invoice (``billing.emails``) and mark it sent. Nothing to send
    (nobody to send it to) is done too; a mail that cannot leave stays owed for ``reconcile_platform_invoices``."""
    from billing import emails

    invoice = Invoice.objects.select_related("hub", "payer_account").get(pk=invoice_id)
    try:
        sent = emails.send_invoice_issued(invoice)
    except emails.MailNotSent:
        return MAIL_FAILED
    Invoice.objects.filter(pk=invoice_id).update(emailed_at=timezone.now())
    return MAILED if sent else MAIL_SKIPPED


def _email_quietly(invoice_id) -> None:
    try:
        send_invoice_mail(invoice_id)
    except Exception:  # noqa: BLE001 - a mail never undoes the invoice; the reconcile run sends it again
        logger.exception("[INVOICE] The e-mail of invoice %s could not be sent", invoice_id)


#: The counts of a ``reconcile_platform_invoices`` run; the failing ones make it exit with an error.
PLATFORM_COUNTS = (
    "posted", "accepted", "waiting", "mailed", "unreachable", "refused", "rejected", "stuck", "mail_failed", "errors",
    "cut_short",
)
PLATFORM_FAILING = ("unreachable", "refused", "rejected", "stuck", "mail_failed", "errors")


def reconcile_platform_invoices(now: datetime | None = None, go_on: Callable[[], bool] | None = None) -> Counter:  # noqa: C901, PLR0912
    """One pass of ``reconcile_platform_invoices`` (the ``saas-worker``, every 15 minutes): post again every
    «issuing» invoice whose wait passed, ask the platform hub about every issued (or rejected) one until the AEAT
    accepts it, and count the ones «issuing» for longer than ``PLATFORM_STUCK_AFTER``. One invoice never stops the
    others. ``go_on`` (the worker's stop request and the round's time budget) is asked before each call to the Hub
    or mail: once it says no, the pass ends after the invoice in course (``cut_short`` 1, the rest in the next pass);
    the count of the stuck ones is always made."""
    now = now or timezone.now()
    counts = Counter({key: 0 for key in PLATFORM_COUNTS})

    def more() -> bool:
        if not counts["cut_short"] and go_on is not None and not go_on():
            counts["cut_short"] = 1
        return not counts["cut_short"]

    paid = Invoice.objects.filter(payment_status=Invoice.PaymentStatus.PAID).exclude(number="")
    due = (
        paid.filter(fiscal_status=Invoice.FiscalStatus.ISSUING)
        .filter(Q(next_post_at__isnull=True) | Q(next_post_at__lte=now))
        .order_by("series", "issued_on", "sequence")
        .values_list("id", flat=True)
    )
    for invoice_id in () if counts["cut_short"] else list(due):
        if not more():
            break
        try:
            outcome = post_platform_invoice(invoice_id)
        except Exception:  # noqa: BLE001 - one invoice never stops the pass; it stays owed
            logger.exception("[INVOICE] Posting invoice %s crashed", invoice_id)
            counts["errors"] += 1
            continue
        if outcome != NOTHING_TO_POST:
            counts[outcome] += 1
    asked = paid.filter(fiscal_status__in=[Invoice.FiscalStatus.ISSUED, Invoice.FiscalStatus.REJECTED]).values_list(
        "id", flat=True
    )
    for invoice_id in () if counts["cut_short"] else list(asked):
        if not more():
            break
        try:
            status = refresh_platform_invoice(invoice_id)
        except Exception:  # noqa: BLE001 - one invoice never stops the pass
            logger.exception("[INVOICE] Asking about invoice %s crashed", invoice_id)
            counts["errors"] += 1
            continue
        if status in (UNREACHABLE, REFUSED):
            counts[status] += 1
        elif status == Invoice.FiscalStatus.REJECTED:
            counts["rejected"] += 1
        elif status == Invoice.FiscalStatus.ISSUED:
            counts["waiting"] += 1
        else:
            counts["accepted"] += 1
    counts["stuck"] = paid.filter(
        fiscal_status=Invoice.FiscalStatus.ISSUING, fiscal_status_at__lte=now - PLATFORM_STUCK_AFTER
    ).count()
    unmailed = paid.filter(fiscal_status__in=ISSUED_STATUSES, emailed_at__isnull=True).values_list("id", flat=True)
    for invoice_id in () if counts["cut_short"] else list(unmailed):
        if not more():
            break
        outcome = send_invoice_mail(invoice_id)
        if outcome == MAIL_FAILED:
            counts["mail_failed"] += 1
        elif outcome == MAILED:
            counts["mailed"] += 1
    return counts


def platform_run_failed(counts: Counter) -> bool:
    return any(counts[key] for key in PLATFORM_FAILING)


def reconcile_platform_invoices_exclusively(go_on: Callable[[], bool] | None = None) -> Counter | None:
    """One pass of ``reconcile_platform_invoices`` under its lock: its counts, or ``None`` when another run holds the
    lock (and this one did nothing). What the command and the ``saas-worker`` (every 15 minutes, ``base.worker``,
    with its ``go_on``) both run."""
    with exclusive_runs.run_exclusively("reconcile_platform_invoices") as mine:
        return reconcile_platform_invoices(go_on=go_on) if mine else None


# --- «Pay» an invoice not collected -----------------------------------------------------------------


@operation(
    "billing.invoice.pay",
    kind="command",
    permission="billing.pay",
    input=InvoicePayIn,
    output=InvoicePayOut,
    ai=INTERNAL,  # stripe
)
def invoice_pay(ctx: OperationContext, data: InvoicePayIn) -> dict:
    """Stripe's page to pay an invoice not collected (the panel opens it only on the web; the apps sell
    nothing). Only its payer pays it; with a card the bank declined, «Pay» waits until the
    card changes (409 ``billing.card_change_required``)."""
    user = access_control.account_of(ctx)
    invoice = queries.invoice_of(user, data.id)
    if invoice.payment_status == Invoice.PaymentStatus.PAID:
        raise Conflict(_("This invoice is paid already."), code="billing.invoice_paid")
    if invoice.payment_status == Invoice.PaymentStatus.VOID or not invoice.hosted_invoice_url:
        raise Conflict(_("This invoice was cancelled: there is nothing to pay."), code="billing.invoice_void")
    if not queries.pays_for(user, invoice):
        raise Conflict(
            _("Only the account that pays this business can pay its invoices."), code="billing.payer_required"
        )
    if queries.card_change_required(invoice):
        raise Conflict(
            _("The bank declined the card. Change the card first, then pay the invoice."),
            code="billing.card_change_required",
        )
    return {"url": invoice.hosted_invoice_url}

