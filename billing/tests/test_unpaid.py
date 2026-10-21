"""An unpaid renewal: 7 days of grace, then suspended; paid, back at once (PLAN-SAAS §3.3; lot L2-B).

Ported from ERPlora/saas (origin/develop) ``hubs/main/tests/test_unpaid_hub_is_suspended.py`` (13),
``test_paid_hub_resumes_after_payment.py`` (14), ``test_late_payment_failed_keeps_paid_plan.py`` (7),
``test_suspended_hub_lifecycle.py`` (the clock) and the invoice half of ``test_webhooks.py``, through the
webhook (``invoice.payment_failed``, ``invoice.paid``, ``customer.updated``). The rules:

- The grace runs from the FAILED INVOICE (its ``created``), never from the local period, which Stripe has
  already renewed (saas#2574): inside it the business works with «payment pending» (round 17 §2.10); past
  it, or with Stripe's final ``unpaid``, it is suspended. A later failure does not move the clock.
- The LIVE subscription decides (saas#2261): a failure delivered after the retry was collected is ignored;
  a late success while the subscription is still in dunning wakes nothing.
- Paying brings it back at once (saas#2529); Stripe not answering a paid invoice counts as paid.
- Why it is unpaid reaches the panel (mockups README §6.18): a declined card blocks «Pay» until the card
  changes (``card_changed`` after the Customer Portal), an authentication or any other failure does not.
- The money Stripe collected is checked against our engine (``vat.resolve_vat``): a subject sale with no
  tax is a structured ERROR, the alarm of a missing TaxRate.

Dropped with reason: stopping and starting the container, the suspension e-mails' Celery tasks, the 30/150/
180-day deletion notices and the start/resume endpoints of the old API (no container per business; the
Hub paints «suspended», PLAN-SAAS §2.3).
"""

import logging
import time
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from billing.models import PaymentFailure
from billing.tests.conftest import pay
from billing.tests.stripe_double import (
    DAY,
    MONTH_END,
    card_error,
    connection_error,
    event,
    invoice,
    invoice_payment,
    item,
    listing,
    payment_intent,
    signed,
    subscription,
)
from hubs import queries as hub_queries
from hubs.models import Hub, Subscription
from hubs.schemas import BusinessListIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def deliver(payload):
    body, header = signed(payload)
    response = Client().post(
        "/webhooks/stripe/",
        body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
        HTTP_HOST="localhost:8001",
    )
    assert response.status_code == 200, response.content
    return response.json()["status"]


@pytest.fixture
def running(shop):
    """A ready business paying Starter monthly (``sub_1``), active."""
    paid = pay(shop)
    Hub.objects.filter(pk=paid.pk).update(
        status=Hub.Status.ACTIVE, ready_at=timezone.now(), pending_hub_call=""
    )
    return Hub.objects.get(pk=paid.pk)


def days_ago(days):
    return int(time.time()) - int(days * DAY)


def failed(
    stripe_double,
    *,
    days=3,
    live="past_due",
    code="card_declined",
    decline="generic_decline",
    method="pm_old",
    invoice_id="in_1",
):
    stripe_double.answer("subscriptions.retrieve", subscription(status=live))
    stripe_double.answer(
        "invoice_payments.list",
        listing([invoice_payment("pi_1", invoice_id=invoice_id)]),
    )
    stripe_double.answer(
        "payment_intents.retrieve",
        payment_intent("pi_1", code=code, decline_code=decline, payment_method=method),
    )
    return deliver(
        event("invoice.payment_failed", invoice(invoice_id, created=days_ago(days)))
    )


def status_of(hub):
    return Hub.objects.get(pk=hub.pk).status


def local(hub):
    return Subscription.objects.get(hub=hub)


def row_of(user, hub):
    rows = hub_queries.business_list(ctx_for(user), BusinessListIn()).model_dump()[
        "rows"
    ]
    return next(row for row in rows if row["id"] == hub.id)


class TestAFailedRenewal:
    def test_inside_the_grace_the_business_works_with_payment_pending(
        self, running, owner, stripe_double
    ):
        assert failed(stripe_double, days=3) == "processed"

        assert (status_of(running), local(running).status) == (
            Hub.Status.PAST_DUE,
            "past_due",
        )
        row = row_of(owner, running)
        assert (row["can_open"], row["unpaid_reason"]) == (True, "card_declined")
        assert abs(row["unpaid_since"].timestamp() - days_ago(3)) < 5
        assert row["pay_url"] == "https://invoice.stripe.com/i/test_1"

    def test_eight_days_after_the_failed_invoice_it_is_suspended(
        self, running, stripe_double
    ):
        # The local period was renewed by Stripe already: only the invoice counts.
        Subscription.objects.filter(hub=running).update(
            current_period_end=timezone.now() + timedelta(days=22)
        )

        failed(stripe_double, days=8)

        assert status_of(running) == Hub.Status.SUSPENDED

    def test_stripes_unpaid_is_the_final_verdict_and_suspends_at_once(
        self, running, stripe_double
    ):
        failed(stripe_double, days=1, live="unpaid")

        assert (status_of(running), local(running).status) == (
            Hub.Status.SUSPENDED,
            "unpaid",
        )

    def test_a_later_failure_does_not_move_the_clock(self, running, stripe_double):
        failed(stripe_double, days=8)
        first = PaymentFailure.objects.get()

        failed(stripe_double, days=8)

        again = PaymentFailure.objects.get()
        assert (again.invoice_created_at, again.attempts) == (
            first.invoice_created_at,
            2,
        )
        assert status_of(running) == Hub.Status.SUSPENDED

    def test_the_suspension_reaches_the_hub(
        self, running, stripe_double, hub_double, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            failed(stripe_double, days=9)

        assert hub_double.calls_to("PUT", "/state")[-1].body["status"] == "suspended"

    @pytest.mark.parametrize(
        "live", ["active", "trialing", "canceled", "incomplete_expired"]
    )
    def test_a_failure_delivered_after_the_subscription_left_dunning_is_ignored(
        self, running, stripe_double, live
    ):
        assert failed(stripe_double, days=9, live=live) == "ignored"

        # Nothing is suspended nor recorded; what is written is what Stripe says now (an ended one is Free).
        assert status_of(running) == Hub.Status.ACTIVE
        assert local(running).status == ("trialing" if live == "trialing" else "active")
        assert PaymentFailure.objects.count() == 0

    def test_stripe_not_answering_is_left_to_its_retry(self, running, stripe_double):
        """Changed from the old SaaS (review of L2-B): applying a failure «as it came» suspended businesses on
        a stale event. Without the live subscription nothing is written; Stripe retries (500)."""
        stripe_double.answer("subscriptions.retrieve", connection_error())
        stripe_double.answer("invoice_payments.list", listing([]))
        body, header = signed(event("invoice.payment_failed", invoice("in_1", created=days_ago(9))))

        response = Client().post("/webhooks/stripe/", body, content_type="application/json",
                                 HTTP_STRIPE_SIGNATURE=header, HTTP_HOST="localhost:8001")

        assert response.status_code == 500
        assert (status_of(running), local(running).unpaid_reason) == (Hub.Status.ACTIVE, "")
        assert PaymentFailure.objects.count() == 0

    def test_a_failure_redelivered_after_the_invoice_was_paid_does_not_reopen_it(self, running, stripe_double):
        failed(stripe_double, days=2, invoice_id="in_1")
        PaymentFailure.objects.update(resolved_at=timezone.now())

        failed(stripe_double, days=2, invoice_id="in_1")

        assert PaymentFailure.objects.get().resolved_at is not None

    def test_an_authentication_does_not_block_paying(self, running, stripe_double):
        failed(stripe_double, code="card_declined", decline="authentication_required")

        assert local(running).unpaid_reason == "authentication_required"

    @pytest.mark.parametrize("code", ["expired_card", "incorrect_cvc"])
    def test_a_card_that_will_not_pay_again_blocks_paying_with_it(
        self, running, stripe_double, code
    ):
        failed(stripe_double, code=code, decline="")

        assert local(running).unpaid_reason == "card_declined"

    @pytest.mark.parametrize("decline", ["insufficient_funds", "try_again_later", "processing_error"])
    def test_a_decline_the_same_card_may_pass_later_does_not_block_paying(self, running, stripe_double, decline):
        """Review of L2-B: only a card that will not pay as it is blocks «Pay» (mockups README §6.18)."""
        failed(stripe_double, code="card_declined", decline=decline)

        assert local(running).unpaid_reason == "payment_failed"

    @pytest.mark.parametrize("decline", ["do_not_honor", "lost_card", "stolen_card", "generic_decline"])
    def test_a_true_decline_blocks_paying_with_that_card(self, running, stripe_double, decline):
        failed(stripe_double, code="card_declined", decline=decline)

        assert local(running).unpaid_reason == "card_declined"

    def test_a_failure_without_an_attempt_is_a_payment_failed(
        self, running, stripe_double
    ):
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))
        stripe_double.answer("invoice_payments.list", listing([]))

        deliver(event("invoice.payment_failed", invoice("in_1", created=days_ago(1))))

        assert local(running).unpaid_reason == "payment_failed"

    def test_an_invoice_of_a_subscription_nobody_knows(self, stripe_double):
        assert (
            deliver(
                event(
                    "invoice.payment_failed",
                    invoice("in_9", subscription_id="sub_nobody"),
                )
            )
            == "unknown"
        )
        assert stripe_double.calls == []

    def test_an_invoice_without_a_subscription_is_not_ours(self, stripe_double):
        payload = invoice("in_9")
        payload["parent"] = None

        assert deliver(event("invoice.payment_failed", payload)) == "ignored"

    def test_an_event_of_an_older_endpoint_still_names_its_subscription(
        self, running, stripe_double
    ):
        payload = invoice("in_1", created=days_ago(2))
        payload["parent"] = None
        payload["subscription"] = "sub_1"
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))
        stripe_double.answer("invoice_payments.list", listing([]))

        deliver(event("invoice.payment_failed", payload))

        assert status_of(running) == Hub.Status.PAST_DUE


class TestTheCardChanges:
    def test_a_new_default_card_lets_the_owner_pay(self, running, owner, stripe_double):
        failed(stripe_double, method="pm_old")
        customer = {
            "id": "cus_1",
            "object": "customer",
            "invoice_settings": {"default_payment_method": "pm_new"},
        }

        assert deliver(event("customer.updated", customer)) == "processed"

        assert row_of(owner, running)["unpaid_reason"] == "card_changed"
        assert PaymentFailure.objects.get().card_changed_at is not None

    def test_a_new_card_on_the_subscription_lets_the_owner_pay(self, running, owner, stripe_double):
        failed(stripe_double, method="pm_old")
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due", default_payment_method="pm_new"))

        deliver(event("customer.subscription.updated", subscription(status="past_due")))

        assert row_of(owner, running)["unpaid_reason"] == "card_changed"

    def test_a_failure_whose_card_is_unknown_is_not_taken_for_a_change(self, running, owner, stripe_double):
        """Without the card that failed, any default card would look «new» (review of L2-B)."""
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))
        stripe_double.answer("invoice_payments.list", connection_error())
        deliver(event("invoice.payment_failed", invoice("in_1", created=days_ago(1))))
        PaymentFailure.objects.update(reason="card_declined")
        Subscription.objects.filter(hub=running).update(unpaid_reason="card_declined")

        deliver(event("customer.updated", {"id": "cus_1", "invoice_settings": {"default_payment_method": "pm_any"}}))

        assert local(running).unpaid_reason == "card_declined"

    def test_a_retry_that_cannot_say_why_keeps_what_was_known(self, running, stripe_double):
        failed(stripe_double, method="pm_old")
        stripe_double.answer("invoice_payments.list", connection_error())

        deliver(event("invoice.payment_failed", invoice("in_1", created=days_ago(3))))

        failure = PaymentFailure.objects.get()
        assert (failure.reason, failure.payment_method_id, failure.attempts) == ("card_declined", "pm_old", 2)

    def test_the_business_is_locked_before_its_failures(self, running, stripe_double):
        """One lock order for every writer (Hub, then PaymentFailure), or two of them deadlock."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        failed(stripe_double, method="pm_old")

        with CaptureQueriesContext(connection) as queries:
            deliver(event("customer.updated", {"id": "cus_1", "invoice_settings": {"default_payment_method": "pm_new"}}))

        sql = [query["sql"] for query in queries.captured_queries]
        hub_lock = next(n for n, text in enumerate(sql) if "FOR UPDATE" in text and '"hubs_hub"' in text)
        failure_write = next(n for n, text in enumerate(sql) if text.startswith('UPDATE "billing_paymentfailure"'))
        assert hub_lock < failure_write

    def test_the_same_card_again_changes_nothing(self, running, stripe_double):
        failed(stripe_double, method="pm_old")
        customer = {
            "id": "cus_1",
            "object": "customer",
            "invoice_settings": {"default_payment_method": "pm_old"},
        }

        assert deliver(event("customer.updated", customer)) == "ignored"
        assert local(running).unpaid_reason == "card_declined"

    def test_the_new_card_declined_too_blocks_again(self, running, stripe_double):
        failed(stripe_double, method="pm_old")
        deliver(
            event(
                "customer.updated",
                {
                    "id": "cus_1",
                    "invoice_settings": {"default_payment_method": "pm_new"},
                },
            )
        )

        failed(stripe_double, method="pm_new")

        assert local(running).unpaid_reason == "card_declined"


class TestPayingBringsItBack:
    def suspended(self, running, stripe_double):
        failed(stripe_double, days=9)
        assert status_of(running) == Hub.Status.SUSPENDED

    def test_the_business_is_active_again_and_nothing_is_owed(
        self, running, owner, stripe_double
    ):
        self.suspended(running, stripe_double)
        stripe_double.answer("subscriptions.retrieve", subscription(status="active"))

        assert (
            deliver(
                event("invoice.paid", invoice("in_1", status="paid", amount_paid=3629))
            )
            == "processed"
        )

        assert (status_of(running), local(running).status) == (
            Hub.Status.ACTIVE,
            "active",
        )
        row = row_of(owner, running)
        assert (row["unpaid_reason"], row["unpaid_since"], row["pay_url"]) == (
            None,
            None,
            None,
        )
        assert PaymentFailure.objects.get().resolved_at is not None

    def test_the_renewal_takes_the_period_of_the_live_subscription(
        self, running, stripe_double
    ):
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[item("si_plan", "price_starter_month")]),
        )

        deliver(event("invoice.paid", invoice("in_2", status="paid", amount_paid=3629)))

        assert int(local(running).current_period_end.timestamp()) == MONTH_END

    def test_a_late_payment_of_an_older_invoice_wakes_nothing_while_still_in_dunning(
        self, running, stripe_double
    ):
        self.suspended(running, stripe_double)
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))

        deliver(
            event("invoice.paid", invoice("in_old", status="paid", amount_paid=3629))
        )

        assert status_of(running) == Hub.Status.SUSPENDED

    def test_stripe_not_answering_a_paid_invoice_is_left_to_its_retry(self, running, stripe_double):
        """Changed from the old SaaS (review of L2-B): without the live subscription a paid invoice may be a
        proration or an older one; guessing «active» and a period woke businesses still in dunning. Stripe
        retries the event (500) and the next delivery reads the truth."""
        self.suspended(running, stripe_double)
        stripe_double.answer("subscriptions.retrieve", connection_error())
        body, header = signed(event("invoice.paid", invoice("in_1", status="paid", amount_paid=3629)))

        response = Client().post("/webhooks/stripe/", body, content_type="application/json",
                                 HTTP_STRIPE_SIGNATURE=header, HTTP_HOST="localhost:8001")

        assert response.status_code == 500
        assert status_of(running) == Hub.Status.SUSPENDED
        assert PaymentFailure.objects.get().resolved_at is None

    def test_only_the_business_that_paid_comes_back(
        self, running, owner, stripe_double, plans
    ):
        from hubs.tests.conftest import create_business

        other = pay(create_business(owner, name="Otro Bar"), sub_id="sub_other")
        Hub.objects.filter(pk=other.pk).update(
            status=Hub.Status.SUSPENDED, ready_at=timezone.now()
        )
        self.suspended(running, stripe_double)
        stripe_double.answer("subscriptions.retrieve", subscription(status="active"))

        deliver(event("invoice.paid", invoice("in_1", status="paid", amount_paid=3629)))

        assert (status_of(running), status_of(other)) == (
            Hub.Status.ACTIVE,
            Hub.Status.SUSPENDED,
        )


class TestThePayerIsTold:
    """BILLING-F16 (saas#2593): the market tells the customer as soon as a renewal fails (Shopify, Square,
    Lightspeed, WooCommerce), with the way to pay and the day the business stops, and again when it stops. Once
    per unpaid invoice and once per suspension, after the COMMIT; a mail that could not leave is sent by the
    next ``sweep_unpaid``. Each mail names what it is in ``X-ERPlora-Notice``."""

    @pytest.fixture
    def told(self, django_capture_on_commit_callbacks, mailoutbox):
        def run(stripe_double, **failure):
            with django_capture_on_commit_callbacks(execute=True):
                failed(stripe_double, **failure)
            return [message.extra_headers.get("X-ERPlora-Notice") for message in mailoutbox]

        return run

    def test_a_failed_renewal_tells_the_payer_how_to_pay(self, running, told, stripe_double, mailoutbox):
        assert told(stripe_double, days=3) == ["billing.payment_failed"]

        message = mailoutbox[0]
        assert message.to == ["owner@example.com"]
        assert f"https://erplora.com/billing/invoices?business={running.id}" in message.body
        assert PaymentFailure.objects.get().notified_at is not None

    def test_another_failed_attempt_of_the_same_invoice_tells_nothing_more(self, running, told, stripe_double):
        told(stripe_double, days=3)

        assert told(stripe_double, days=3) == ["billing.payment_failed"]

    def test_a_new_unpaid_invoice_is_told_too(self, running, told, stripe_double):
        told(stripe_double, days=3)

        assert told(stripe_double, days=1, invoice_id="in_2") == ["billing.payment_failed"] * 2

    def test_the_suspension_is_told_once(self, running, told, stripe_double):
        told(stripe_double, days=3)
        # An older invoice unpaid too: past the grace, so the business is suspended (a later failure of the
        # same invoice never moves the clock).
        assert told(stripe_double, days=9, invoice_id="in_0") == [
            "billing.payment_failed",
            "billing.business_suspended",
        ]

        assert told(stripe_double, days=10, invoice_id="in_00") == [
            "billing.payment_failed",
            "billing.business_suspended",
        ]

    def test_a_first_failure_past_the_grace_tells_only_the_suspension(self, running, told, stripe_double):
        assert told(stripe_double, days=9) == ["billing.business_suspended"]

        assert PaymentFailure.objects.get().notified_at is not None

    def test_stripes_final_verdict_tells_the_suspension(self, running, told, stripe_double):
        assert told(stripe_double, days=1, live="unpaid") == ["billing.business_suspended"]

    def test_the_payers_own_address_for_invoices_gets_it(self, running, told, stripe_double, mailoutbox):
        running.billing_profile.billing_email = "accounts@example.com"
        running.billing_profile.save()

        told(stripe_double, days=3)

        assert mailoutbox[0].to == ["accounts@example.com"]

    def test_a_mail_that_could_not_leave_is_sent_by_the_sweep(
        self, running, told, stripe_double, mailoutbox, monkeypatch, django_capture_on_commit_callbacks
    ):
        from billing import services

        def down(*args, **kwargs):
            raise OSError("smtp down")

        with monkeypatch.context() as patched:
            patched.setattr("django.core.mail.EmailMessage.send", down)
            assert told(stripe_double, days=3) == []
        assert PaymentFailure.objects.get().notified_at is None

        stripe_double.answer("invoices.list", listing([]))
        with django_capture_on_commit_callbacks(execute=True):
            counts = services.sweep_unpaid()

        assert [message.extra_headers["X-ERPlora-Notice"] for message in mailoutbox] == ["billing.payment_failed"]
        assert (counts["notified"], counts["mail_failed"]) == (1, 0)

    def test_a_mail_still_down_makes_the_sweep_fail(self, running, told, stripe_double, monkeypatch):
        from billing import services

        def down(*args, **kwargs):
            raise OSError("smtp down")

        monkeypatch.setattr("django.core.mail.EmailMessage.send", down)
        told(stripe_double, days=3)
        stripe_double.answer("invoices.list", listing([]))

        assert services.sweep_unpaid()["mail_failed"] == 1

    def test_paying_closes_the_episode_and_a_later_one_is_told_again(
        self, running, told, stripe_double, django_capture_on_commit_callbacks
    ):
        told(stripe_double, days=9)
        stripe_double.answer("subscriptions.retrieve", subscription(status="active"))
        with django_capture_on_commit_callbacks(execute=True):
            deliver(event("invoice.paid", invoice("in_1", status="paid", amount_paid=3629)))

        assert told(stripe_double, days=1, invoice_id="in_2") == [
            "billing.business_suspended",
            "billing.payment_failed",
        ]


class TestTheMoneyCollectedIsAudited:
    def test_a_subject_sale_charged_without_tax_is_an_alarm(
        self, running, stripe_double, caplog
    ):
        stripe_double.answer("subscriptions.retrieve", subscription())

        with caplog.at_level(logging.ERROR, logger="billing.vat"):
            deliver(
                event(
                    "invoice.paid",
                    invoice("in_2", status="paid", amount_paid=2999, tax=0),
                )
            )

        assert any(
            getattr(record, "event", "")
            == "fiscal.vat.stripe_charged_no_tax_on_subject_sale"
            for record in caplog.records
        )

    def test_a_sale_charged_with_our_rate_is_quiet(
        self, running, stripe_double, caplog
    ):
        stripe_double.answer("subscriptions.retrieve", subscription())

        with caplog.at_level(logging.ERROR):
            deliver(
                event(
                    "invoice.paid",
                    invoice("in_2", status="paid", amount_paid=3629, tax=630),
                )
            )

        assert not [
            record for record in caplog.records if record.levelno >= logging.ERROR
        ]


def test_a_declined_card_on_a_change_never_marks_the_business_unpaid(
    running, owner, inventory, stripe_double
):
    """``error_if_incomplete``: a change whose payment fails leaves no invoice behind to chase."""
    from billing import services
    from billing.schemas import CheckoutConfirmIn
    from billing.tests.conftest import ctx_for as billing_ctx

    stripe_double.answer("subscriptions.retrieve", subscription())
    stripe_double.answer("subscription_items.create", card_error())

    with pytest.raises(Exception):
        services.checkout_confirm(
            billing_ctx(owner),
            CheckoutConfirmIn(hub_id=running.id, module="inventory", proration_date=1),
        )

    assert status_of(running) == Hub.Status.ACTIVE
    assert PaymentFailure.objects.count() == 0
