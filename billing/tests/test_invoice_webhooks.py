"""What is written of a renewal Stripe could not collect (``invoice.payment_failed``): one row per unpaid invoice,
with why it failed, how often and the card that failed, as the panel, the mails and «Pay» read it.

What it does to the business (grace, suspension, back once paid) is ``test_unpaid``.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from billing.models import Invoice, PaymentFailure
from billing.services import invoice_webhooks
from billing.tests.stripe_double import (
    connection_error,
    event,
    invalid_request,
    invoice,
    invoice_payment,
    listing,
    payment_intent,
    permission_denied,
    subscription,
)
from billing.tests.test_unpaid import days_ago, deliver

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


@pytest.fixture
def fails(running, stripe_double):
    """Stripe could not collect an invoice of ``running``'s; ``why`` is the last attempt to pay it, if any
    (``lookup``: what Stripe answers instead when it is asked)."""

    def deliver_failure(payload, why=None, *, live=None, lookup=None):
        stripe_double.answer("subscriptions.retrieve", live or subscription(status="past_due"))
        attempts = [invoice_payment("pi_1", invoice_id=payload["id"])] if why else []
        stripe_double.answer("invoice_payments.list", lookup or listing(attempts))
        stripe_double.answer("payment_intents.retrieve", why)
        return deliver(event("invoice.payment_failed", payload))

    return deliver_failure


def declined(code="card_declined", decline_code="generic_decline", payment_method="pm_old"):
    return payment_intent("pi_1", code=code, decline_code=decline_code, payment_method=payment_method)


def without_a_card(**error):
    attempt = declined(**error)
    attempt["last_payment_error"]["payment_method"] = None
    return attempt


def recorded() -> dict:
    return PaymentFailure.objects.values().get()


def new_card(method="pm_new"):
    return deliver(event("customer.updated", {"id": "cus_1", "invoice_settings": {"default_payment_method": method}}))


class TestAFirstFailure:
    def test_every_field(self, running, fails, stripe_double):
        issued = days_ago(3)
        before = timezone.now()

        assert fails(invoice("in_1", created=issued), declined()) == "processed"

        row = recorded()
        assert before <= row["failed_at"] <= timezone.now()
        assert row == {
            "id": row["id"],
            "hub_id": running.id,
            "stripe_invoice_id": "in_1",
            "stripe_subscription_id": "sub_1",
            "stripe_customer_id": "cus_1",
            "reason": "card_declined",
            "failure_code": "card_declined",
            "decline_code": "generic_decline",
            "payment_method_id": "pm_old",
            "hosted_invoice_url": "https://invoice.stripe.com/i/test_1",
            "invoice_created_at": datetime.fromtimestamp(issued, UTC),
            "failed_at": row["failed_at"],
            "attempts": 1,
            "card_changed_at": None,
            "resolved_at": None,
            "notified_at": None,
            "suspension_notified_at": None,
        }
        assert stripe_double.paths() == ["subscriptions.retrieve", "invoice_payments.list", "payment_intents.retrieve"]

    def test_its_customer_is_the_one_the_invoice_bills(self, fails):
        fails(invoice("in_1", customer="cus_before"), declined())

        assert recorded()["stripe_customer_id"] == "cus_before"

    def test_an_invoice_that_names_no_customer_is_of_its_subscriptions(self, fails):
        fails({**invoice("in_1"), "customer": None}, declined())

        assert recorded()["stripe_customer_id"] == "cus_1"

    def test_without_any_customer_it_is_recorded_too(self, fails):
        live = {**subscription(status="past_due"), "customer": None}

        assert fails({**invoice("in_1"), "customer": None}, declined(), live=live) == "processed"

        assert recorded()["stripe_customer_id"] == ""

    def test_without_a_page_to_pay_it_is_recorded_too(self, fails):
        fails({**invoice("in_1"), "hosted_invoice_url": None}, declined())

        assert recorded()["hosted_invoice_url"] == ""

    def test_stripes_codes_are_cut_to_what_fits(self, fails):
        fails(invoice("in_1"), declined(code="c" * 70, decline_code="d" * 70))

        row = recorded()
        assert (row["failure_code"], row["decline_code"]) == ("c" * 64, "d" * 64)

    @pytest.mark.parametrize("answer", [connection_error(), invalid_request(), permission_denied()])
    def test_one_stripe_does_not_say_why_is_recorded_without_it(self, fails, answer):
        assert fails(invoice("in_1"), lookup=answer) == "processed"

        row = recorded()
        assert (row["reason"], row["failure_code"], row["decline_code"], row["payment_method_id"]) == (
            "payment_failed", "", "", "",
        )

    def test_it_is_held_after_its_business(self, fails):
        """One lock order for every writer (Hub, then PaymentFailure), or two of them deadlock."""
        with CaptureQueriesContext(connection) as captured:
            fails(invoice("in_1"), declined())

        locks = [query["sql"] for query in captured.captured_queries if "FOR UPDATE" in query["sql"]]
        hub_lock = next(n for n, sql in enumerate(locks) if '"hubs_hub"' in sql)
        failure_lock = next(n for n, sql in enumerate(locks) if '"billing_paymentfailure"' in sql)
        assert hub_lock < failure_lock


class TestAnotherAttemptOfTheSameInvoice:
    def test_it_says_why_it_failed_this_time(self, fails):
        fails(invoice("in_1"), declined())

        fails(invoice("in_1"), declined("authentication_required", "", "pm_new"))

        row = recorded()
        assert (row["reason"], row["failure_code"], row["decline_code"], row["payment_method_id"]) == (
            "authentication_required", "authentication_required", "", "pm_new",
        )

    def test_its_codes_are_cut_to_what_fits(self, fails):
        fails(invoice("in_1"), declined())

        fails(invoice("in_1"), declined(code="c" * 70, decline_code="d" * 70))

        row = recorded()
        assert (row["failure_code"], row["decline_code"]) == ("c" * 64, "d" * 64)

    def test_every_attempt_counts(self, fails):
        for _attempt in range(3):
            fails(invoice("in_1"), declined())

        assert recorded()["attempts"] == 3

    def test_it_is_the_last_failure(self, fails):
        fails(invoice("in_1"), declined())
        yesterday = timezone.now() - timedelta(days=1)
        PaymentFailure.objects.update(failed_at=yesterday)

        fails(invoice("in_1"), declined())

        assert recorded()["failed_at"] > yesterday

    def test_the_sweep_deciding_again_is_not_another_attempt(self, running, fails):
        fails(invoice("in_1"), declined())
        yesterday = timezone.now() - timedelta(days=1)
        PaymentFailure.objects.update(failed_at=yesterday)

        assert invoice_webhooks.invoice_payment_failed(invoice("in_1"), replay=True) == "processed"

        row = recorded()
        assert (row["attempts"], row["failed_at"]) == (1, yesterday)

    def test_the_page_to_pay_is_the_one_stripe_says_now(self, fails):
        fails(invoice("in_1"), declined())

        fails(invoice("in_1", hosted_invoice_url="https://invoice.stripe.com/i/test_2"), declined())

        assert recorded()["hosted_invoice_url"] == "https://invoice.stripe.com/i/test_2"

    def test_without_a_page_to_pay_the_one_known_stays(self, fails):
        fails(invoice("in_1"), declined())

        fails({**invoice("in_1"), "hosted_invoice_url": None}, declined())

        assert recorded()["hosted_invoice_url"] == "https://invoice.stripe.com/i/test_1"

    def test_one_stripe_does_not_say_why_takes_its_page_to_pay_only(self, fails):
        fails(invoice("in_1"), declined())
        before = recorded()

        fails(invoice("in_1", hosted_invoice_url="https://invoice.stripe.com/i/test_2"))

        after = recorded()
        assert {field for field in after if after[field] != before[field]} == {"hosted_invoice_url", "failed_at", "attempts"}

    def test_another_invoice_of_the_business_stays_as_it_was(self, fails):
        fails(invoice("in_1"), declined())
        fails(invoice("in_2"), declined())
        before = PaymentFailure.objects.values().get(stripe_invoice_id="in_2")

        fails(invoice("in_1"), declined("expired_card", "", "pm_new"))

        assert PaymentFailure.objects.values().get(stripe_invoice_id="in_2") == before

    def test_one_redelivered_once_it_is_paid_changes_nothing(self, fails):
        fails(invoice("in_1"), declined())
        PaymentFailure.objects.update(resolved_at=timezone.now())
        before = recorded()

        fails(
            invoice("in_1", hosted_invoice_url="https://invoice.stripe.com/i/test_2"),
            declined("expired_card", "", "pm_new"),
        )

        assert recorded() == before


class TestTheCardThatFailed:
    @pytest.fixture
    def changed(self, fails):
        """The card changed after a decline: «Pay» works again."""
        fails(invoice("in_1"), declined(payment_method="pm_old"))
        new_card("pm_new")
        assert recorded()["card_changed_at"] is not None
        return recorded()["card_changed_at"]

    def test_the_old_one_failing_again_does_not_forget_the_change(self, fails, changed):
        fails(invoice("in_1"), declined(payment_method="pm_old"))

        assert recorded()["card_changed_at"] == changed

    def test_an_attempt_that_does_not_say_its_card_does_not_forget_the_change(self, fails, changed):
        fails(invoice("in_1"), without_a_card())

        row = recorded()
        assert (row["card_changed_at"], row["payment_method_id"]) == (changed, "pm_old")

    def test_the_new_one_failing_is_the_card_that_failed(self, fails, changed):
        fails(invoice("in_1"), declined(payment_method="pm_new"))

        row = recorded()
        assert (row["card_changed_at"], row["payment_method_id"]) == (None, "pm_new")


class TestAFailureOutOfDunning:
    def test_support_reads_which_and_why_it_is_ignored(self, running, fails, caplog):
        with caplog.at_level(logging.INFO, logger="billing.services"):
            assert fails(invoice("in_1"), declined(), live=subscription(status="active")) == "ignored"

        assert "[STRIPE WEBHOOK] Failure of in_1 ignored: the subscription is active now" in caplog.messages

    def test_nobody_asks_stripe_why_nor_lists_it(self, running, fails, stripe_double):
        fails(invoice("in_1"), declined(), live=subscription(status="active"))

        assert stripe_double.paths() == ["subscriptions.retrieve"]
        assert not Invoice.objects.exists()
