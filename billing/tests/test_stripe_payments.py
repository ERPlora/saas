"""What Stripe collected for an invoice and what it gave back (``billing.stripe_payments``): why a payment failed
and the refund of an invoice, through the client the tests replace (``stripe_double``)."""

import pytest

from billing import stripe_payments
from billing.stripe_service import StripeRefused
from billing.tests.stripe_double import invalid_request, invoice_payment, listing, payment_intent


def test_why_an_invoice_was_not_paid(stripe_double):
    stripe_double.answer(
        "invoice_payments.list", listing([invoice_payment("pi_9", invoice_id="in_1")])
    )
    stripe_double.answer(
        "payment_intents.retrieve",
        payment_intent(
            "pi_9",
            code="card_declined",
            decline_code="stolen_card",
            payment_method="pm_1",
        ),
    )

    assert stripe_payments.payment_failure_of("in_1") == {
        "code": "card_declined",
        "decline_code": "stolen_card",
        "payment_method": "pm_1",
    }
    assert stripe_double.last("invoice_payments.list").params["invoice"] == "in_1"


def test_an_invoice_without_a_payment_attempt_has_no_reason(stripe_double):
    stripe_double.answer("invoice_payments.list", listing([]))

    assert stripe_payments.payment_failure_of("in_1") is None


def paid(pi_id, cents, *, status="paid"):
    return {**invoice_payment(pi_id, invoice_id="in_1"), "status": status, "amount_paid": cents}


def test_what_an_invoice_collected_is_refunded_once_per_payment(stripe_double):
    """Each paid PaymentIntent of the invoice, in full; a payment that never collected is not refunded."""
    stripe_double.answer("invoice_payments.list", listing([paid("pi_1", 3629), paid("pi_2", 0, status="canceled")]))
    stripe_double.answer("refunds.create", {"id": "re_1", "object": "refund", "status": "succeeded"})

    assert stripe_payments.refund_invoice("in_1", key="refund-cs_1", metadata={"hub_id": "h"}) == 3629

    (call,) = stripe_double.calls_to("refunds.create")
    assert call.params == {"payment_intent": "pi_1", "reason": "requested_by_customer", "metadata": {"hub_id": "h"}}
    assert call.options == {"idempotency_key": "refund-cs_1-pi_1"}


def test_a_charge_stripe_already_refunded_counts_as_refunded(stripe_double):
    """A redelivery after Stripe forgot the idempotency key (24 hours): the second refund is refused, not lost."""
    stripe_double.answer("invoice_payments.list", listing([paid("pi_1", 3629)]))
    stripe_double.answer(
        "refunds.create", invalid_request(code="charge_already_refunded", message="Charge has already been refunded.")
    )

    assert stripe_payments.refund_invoice("in_1", key="refund-cs_1", metadata={}) == 3629


def test_any_other_refusal_of_a_refund_is_raised(stripe_double):
    stripe_double.answer("invoice_payments.list", listing([paid("pi_1", 3629)]))
    stripe_double.answer("refunds.create", invalid_request(code="resource_missing", message="No such payment_intent"))

    with pytest.raises(StripeRefused):
        stripe_payments.refund_invoice("in_1", key="refund-cs_1", metadata={})
