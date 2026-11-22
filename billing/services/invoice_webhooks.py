"""A Stripe invoice paid or not collected, from the webhook: ERPlora's invoice recorded with the live subscription
applied, or the business in dunning with why its renewal failed."""

import logging

from django.db.models import F
from django.utils import timezone

from billing import stripe_payments, stripe_service
from billing.models import PaymentFailure
from billing.schemas.invoice_records import InvoiceRecordIn
from billing.services import (
    invoice_recording,
    invoice_sealing,
    live_subscriptions,
    stripe_sales,
    stripe_sync,
    webhook_targets,
)
from hubs.services import hub_callbacks
from hubs.models import Hub, Subscription

logger = logging.getLogger("billing.services")


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


def _invoice_business(invoice: dict) -> tuple[Hub | None, str]:
    """The business an invoice bills, and its Stripe subscription. Known by the subscription, or — when the
    invoice comes ahead of its ``checkout.session.completed`` (Stripe does not order events) — by the
    ``hub_id`` its subscription's metadata carries, for a business that has no other subscription."""
    subscription_id = invoice_subscription(invoice)
    local = webhook_targets._local_subscription(subscription_id)
    if local is not None:
        return local.hub, subscription_id
    details = (invoice.get("parent") or {}).get("subscription_details") or {}
    named = webhook_targets._hub_named((details.get("metadata") or {}).get("hub_id"))
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
    invoice = invoice_recording._with_all_lines(invoice)
    charged_at = invoice_sealing._moment_or_none((invoice.get("status_transitions") or {}).get("paid_at")) or timezone.now()
    verified, consultation = invoice_recording._payer_clearance(hub, charged_at)
    with stripe_sync.holding(hub.id):
        # Stripe not answering raises: its retry reads the truth (a paid invoice may be a proration or an
        # older one, and guessing «active» woke businesses still in dunning).
        live = stripe_service.retrieve_subscription(subscription_id)
        PaymentFailure.objects.filter(
            stripe_invoice_id=invoice.get("id"), resolved_at__isnull=True
        ).update(resolved_at=timezone.now())
        live_subscriptions.apply_live(hub.id, live)
        invoice_recording.invoice_record(
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
    named = webhook_targets._hub_named(((invoice.get("parent") or {}).get("subscription_details") or {}).get("metadata", {}).get("hub_id")
                       or (invoice.get("metadata") or {}).get("hub_id"))
    if named is None:
        if int(invoice.get("total") or 0) == 0:
            return "unknown" if subscription_id else "ignored"
        logger.error(
            "[INVOICE] Stripe invoice %s (subscription %s) was paid and no business of ours is known for it",
            invoice.get("id"), subscription_id or "-", extra={"event": "billing.unplaced_payment"},
        )
        raise UnplacedPayment(invoice.get("id"))
    invoice = invoice_recording._with_all_lines(invoice)
    charged_at = invoice_sealing._moment_or_none((invoice.get("status_transitions") or {}).get("paid_at")) or timezone.now()
    verified, consultation = invoice_recording._payer_clearance(named, charged_at)
    with stripe_sync.holding(named.id):
        invoice_recording.invoice_record(
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
        why = stripe_payments.payment_failure_of(invoice["id"])
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
    invoice_recording.invoice_record(
        hub_callbacks.system_ctx_for(hub.id), InvoiceRecordIn(hub_id=hub.id, invoice=invoice, status="open")
    )
    return "processed"
