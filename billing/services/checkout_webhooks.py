"""A Checkout Session's outcome, from the webhook: a paid one applied once (a new owner keeping the plan too), one
paid by somebody who no longer owns the business ended and refunded, and one failed or expired closed."""

import logging
from functools import partial

from django.db import transaction
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.operations import INTERNAL, operation
from live.outbox import record_event

from billing import emails, events, stripe_payments, stripe_service
from billing.models import CheckoutAttempt
from billing.money import from_cents
from billing.schemas.invoice_records import CheckoutRefundRecordIn, CheckoutRefundRecordOut
from billing.services import discounts, live_subscriptions, promo_holds, stripe_sales, stripe_sync, webhook_targets
from billing.stripe_checkout import CheckoutKind, checkout_session_kind
from hubs.queries import membership
from hubs.models import Hub, Subscription

logger = logging.getLogger("billing.services")


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
    hub = webhook_targets._hub_named(metadata.get("hub_id"))
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
        stripe_payments.refund_invoice(
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

    account = get_user_model().objects.filter(pk=account_id).first()
    hub = Hub.objects.filter(pk=hub_id).first()
    if account is None or hub is None:
        logger.error("[BILLING] Nobody to tell of the refund of hub %s to account %s", hub_id, account_id)
        return
    try:
        emails.send_checkout_refunded(hub, to=account.email, language=account.language, amount=from_cents(cents))
    except emails.MailNotSent:
        return


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
