"""The events ERPlora's Stripe endpoint sends, each one handed to its handler."""

from collections.abc import Callable

from billing.models import CheckoutAttempt
from billing.services import (
    checkout_webhooks,
    invoice_recording,
    invoice_webhooks,
    rectifying_invoices,
    subscription_webhooks,
)

#: What each event does with its object. The handler is looked up on its module when the event arrives.
_HANDLERS: dict[str, Callable[[dict], str]] = {
    "checkout.session.completed": lambda obj: checkout_webhooks.checkout_completed(obj),
    "checkout.session.async_payment_succeeded": lambda obj: checkout_webhooks.checkout_completed(obj),
    "checkout.session.async_payment_failed": lambda obj: checkout_webhooks.checkout_closed(
        obj, CheckoutAttempt.Status.FAILED
    ),
    "checkout.session.expired": lambda obj: checkout_webhooks.checkout_closed(obj, CheckoutAttempt.Status.EXPIRED),
    "invoice.paid": lambda obj: invoice_webhooks.invoice_paid(obj),
    "invoice.payment_succeeded": lambda obj: invoice_webhooks.invoice_paid(obj),
    "invoice.payment_failed": lambda obj: invoice_webhooks.invoice_payment_failed(obj),
    "invoice.voided": lambda obj: invoice_recording.invoice_voided(obj),
    "invoice.marked_uncollectible": lambda obj: invoice_recording.invoice_voided(obj),
    "credit_note.created": lambda obj: rectifying_invoices.credit_note_created(obj),
    "credit_note.voided": lambda obj: rectifying_invoices.credit_note_voided(obj),
    "charge.refunded": lambda obj: rectifying_invoices.charge_refunded(obj),
    "customer.subscription.created": lambda obj: subscription_webhooks.subscription_updated(obj),
    "customer.subscription.updated": lambda obj: subscription_webhooks.subscription_updated(obj),
    "customer.subscription.deleted": lambda obj: subscription_webhooks.subscription_deleted(obj),
    "customer.updated": lambda obj: subscription_webhooks.customer_updated(obj),
}

#: The events ERPlora's Stripe endpoint sends to ``/webhooks/stripe/``: the one list ``audit_stripe_webhooks`` compares
#: the endpoint with every day; ``billing/README.md`` and ``billing/webhooks.py`` cite it instead of repeating it.
#: ``invoice.payment_succeeded`` is handled as ``invoice.paid`` but not subscribed: one notice per payment is enough.
STRIPE_WEBHOOK_EVENTS = tuple(event_type for event_type in _HANDLERS if event_type != "invoice.payment_succeeded")


def process_stripe_event(event: dict) -> str:
    """Process one signed Stripe event; its outcome (``completed``, ``processed``, ``ignored``, ``unknown``,
    ``invalid``, ``pending``…). Raises when it must be retried (Stripe did not answer a read the event needs)."""
    obj = (event.get("data") or {}).get("object") or {}
    handler = _HANDLERS.get(event.get("type"))
    return handler(obj) if handler else "ignored"
