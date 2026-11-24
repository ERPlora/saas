"""Each event of Stripe goes to its own handler, with the event's object, and what the handler says is the outcome; an
event nobody handles is ``ignored``. The handlers are replaced here: what each one does is its own module's."""

import pytest

from billing.services import (
    checkout_webhooks,
    invoice_recording,
    invoice_webhooks,
    rectifying_invoices,
    subscription_webhooks,
    webhook_dispatch,
)

#: The handlers of the events, by the module they live in.
HANDLERS = (
    (checkout_webhooks, ("checkout_completed", "checkout_closed")),
    (invoice_webhooks, ("invoice_paid", "invoice_payment_failed")),
    (invoice_recording, ("invoice_voided",)),
    (rectifying_invoices, ("credit_note_created", "credit_note_voided", "charge_refunded")),
    (subscription_webhooks, ("subscription_updated", "subscription_deleted", "customer_updated")),
)
OBJECT = {"id": "obj_1"}

#: What each event calls and what it hands over.
CALLS = {
    "checkout.session.completed": ("checkout_completed", OBJECT),
    "checkout.session.async_payment_succeeded": ("checkout_completed", OBJECT),
    "checkout.session.async_payment_failed": ("checkout_closed", OBJECT, "failed"),
    "checkout.session.expired": ("checkout_closed", OBJECT, "expired"),
    "invoice.paid": ("invoice_paid", OBJECT),
    "invoice.payment_succeeded": ("invoice_paid", OBJECT),
    "invoice.payment_failed": ("invoice_payment_failed", OBJECT),
    "invoice.voided": ("invoice_voided", OBJECT),
    "invoice.marked_uncollectible": ("invoice_voided", OBJECT),
    "credit_note.created": ("credit_note_created", OBJECT),
    "credit_note.voided": ("credit_note_voided", OBJECT),
    "charge.refunded": ("charge_refunded", OBJECT),
    "customer.subscription.created": ("subscription_updated", OBJECT),
    "customer.subscription.updated": ("subscription_updated", OBJECT),
    "customer.subscription.deleted": ("subscription_deleted", OBJECT),
    "customer.updated": ("customer_updated", OBJECT),
}


@pytest.fixture
def called(monkeypatch):
    calls = []
    for module, names in HANDLERS:
        for name in names:
            monkeypatch.setattr(module, name, lambda *args, name=name: calls.append((name, *args)) or f"{name} did it")
    return calls


@pytest.mark.parametrize(("event_type", "call"), CALLS.items())
def test_each_event_goes_to_its_handler_and_its_word_is_the_outcome(called, event_type, call):
    outcome = webhook_dispatch.process_stripe_event({"type": event_type, "data": {"object": OBJECT}})

    assert called == [call]
    assert outcome == f"{call[0]} did it"


def test_the_endpoint_is_sent_all_of_them_but_the_second_notice_of_a_payment():
    assert list(webhook_dispatch.STRIPE_WEBHOOK_EVENTS) == [
        event_type for event_type in CALLS if event_type != "invoice.payment_succeeded"
    ]


@pytest.mark.parametrize("data", [{}, {"data": None}, {"data": {}}, {"data": {"object": None}}])
def test_an_event_without_an_object_hands_over_an_empty_one(called, data):
    webhook_dispatch.process_stripe_event({"type": "invoice.paid", **data})

    assert called == [("invoice_paid", {})]


@pytest.mark.parametrize("event", [{"type": "payment_intent.created"}, {"type": None}, {}])
def test_an_event_nobody_handles_is_ignored(called, event):
    assert webhook_dispatch.process_stripe_event({**event, "data": {"object": OBJECT}}) == "ignored"
    assert called == []
