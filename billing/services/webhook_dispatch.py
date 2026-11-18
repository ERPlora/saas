"""The events ERPlora's Stripe endpoint sends, each one handed to its handler."""

from billing.models import CheckoutAttempt
from billing.services import (
    checkout_webhooks,
    invoice_recording,
    invoice_webhooks,
    rectifying_invoices,
    subscription_webhooks,
)


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
            return checkout_webhooks.checkout_completed(obj)
        case "checkout.session.async_payment_failed":
            return checkout_webhooks.checkout_closed(obj, CheckoutAttempt.Status.FAILED)
        case "checkout.session.expired":
            return checkout_webhooks.checkout_closed(obj, CheckoutAttempt.Status.EXPIRED)
        case "invoice.paid" | "invoice.payment_succeeded":
            return invoice_webhooks.invoice_paid(obj)
        case "invoice.payment_failed":
            return invoice_webhooks.invoice_payment_failed(obj)
        case "invoice.voided" | "invoice.marked_uncollectible":
            return invoice_recording.invoice_voided(obj)
        case "credit_note.created":
            return rectifying_invoices.credit_note_created(obj)
        case "credit_note.voided":
            return rectifying_invoices.credit_note_voided(obj)
        case "charge.refunded":
            return rectifying_invoices.charge_refunded(obj)
        case "customer.subscription.created" | "customer.subscription.updated":
            return subscription_webhooks.subscription_updated(obj)
        case "customer.subscription.deleted":
            return subscription_webhooks.subscription_deleted(obj)
        case "customer.updated":
            return subscription_webhooks.customer_updated(obj)
    return "ignored"
