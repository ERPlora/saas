"""Stripe's single webhook, ``POST /webhooks/stripe/`` (PLAN-SAAS §4; lot L2-B).

Ported from ERPlora/saas ``hubs/main/webhooks.py`` and its tests (origin/develop): ``test_webhooks.py`` (23),
``test_webhooks_sdk15_compat.py`` (1), ``test_late_subscription_updated_follows_live.py`` (6),
``test_live_period_read_from_subscription_item.py`` (6), ``dashboard/billing/tests/test_checkout_session_routing.py``
(12) and the end of ``test_hub_delete_cancels_billing.py``. The four routes of the old SaaS are ONE now:

- Only Stripe's signature opens it (the real check, ``stripe.Webhook``, against events signed as Stripe
  signs them): anything else is 400; without a webhook secret, 503.
- Each event is processed once (``WebhookEvent``, saas#2530): a duplicate answers 200 without running it, a
  delivery being processed elsewhere 409 (Stripe retries), a failure 500 and stays claimable.
- Stripe redelivers late and in any order (saas#2321): what is written is the LIVE subscription (read again
  with ``subscriptions.retrieve``), never the event's snapshot, unless Stripe does not answer.
- What it learns goes through ``hubs.subscription.apply``: the plan, the modules, the period, and the
  snapshot pushed to the Hub after the COMMIT.

Dropped with reason: the deploy of a container after the first payment, its resize after a change and the
reduced «suspension» subscription of a cancelled plan (no container per business, PLAN §14; a plan that
ends goes back to Free, PLAN-SAAS §3.3); the module and Connect routes and the assistant's (one route); the
invoice written on ``checkout.session.completed`` (ERPlora's invoice is written on ``invoice.paid``, lot L3-C:
``test_invoice_recording``).
"""

import json
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from billing import services
from billing.models import CheckoutAttempt, PromoCode, WebhookEvent
from billing.tests.conftest import pay
from billing.tests.stripe_double import (
    MONTH_END,
    MONTH_START,
    checkout_session,
    connection_error,
    event,
    invoice,
    item,
    signed,
    subscription,
)
from hubs.models import Hub, Subscription, SubscriptionItem

pytestmark = pytest.mark.django_db

URL = "/webhooks/stripe/"
HOST = "localhost:8001"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def deliver(payload: dict, *, secret=None, client=None):
    body, header = signed(payload) if secret is None else signed(payload, secret=secret)
    client = client or Client(enforce_csrf_checks=True)
    return client.post(
        URL,
        body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=header,
        HTTP_HOST=HOST,
    )


def local(hub):
    return Subscription.objects.select_related("plan", "trial_plan").get(hub=hub)


def plan_session(hub, **fields):
    metadata = {
        "kind": "hub_plan",
        "hub_id": str(hub.id),
        "plan": "starter",
        "billing_interval": "month",
    }
    return checkout_session(
        metadata={**metadata, **fields.pop("metadata", {})}, **fields
    )


# --- The door ----------------------------------------------------------------------------------------


class TestTheDoor:
    def test_an_event_nobody_handles_is_acknowledged(self):
        response = deliver(
            event(
                "product.created",
                {"id": "prod_1", "object": "product"},
                event_id="evt_x",
            )
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ignored", "event_id": "evt_x"}
        row = WebhookEvent.objects.get(event_id="evt_x")
        assert (row.event_type, row.success, row.outcome) == (
            "product.created",
            True,
            "ignored",
        )

    def test_a_bad_signature_is_refused_and_nothing_is_recorded(self):
        response = deliver(
            event("invoice.paid", {"id": "in_1"}), secret="whsec_somebody_else"
        )

        assert response.status_code == 400
        assert WebhookEvent.objects.count() == 0

    def test_a_body_that_is_not_an_event_is_refused(self):
        response = Client().post(
            URL,
            b"nope",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1,v1=x",
            HTTP_HOST=HOST,
        )

        assert response.status_code == 400

    def test_only_post(self):
        response = Client().get(URL, HTTP_HOST=HOST)

        assert response.status_code == 405

    def test_without_the_webhook_secret_stripe_is_told_to_come_back(self, settings):
        settings.STRIPE_WEBHOOK_SECRET = ""

        response = deliver(event("invoice.paid", {"id": "in_1"}))

        assert response.status_code == 503

    def test_the_same_event_twice_is_processed_once(self, monkeypatch):
        runs = []
        monkeypatch.setattr(
            services,
            "process_stripe_event",
            lambda received: runs.append(received["id"]) or "processed",
        )
        payload = event("invoice.paid", {"id": "in_1"}, event_id="evt_twice")

        first = deliver(payload)
        second = deliver(payload)

        assert (first.status_code, second.status_code) == (200, 200)
        assert second.json() == {"status": "duplicate", "event_id": "evt_twice"}
        assert runs == ["evt_twice"]

    def test_an_event_another_delivery_is_processing_is_left_to_stripes_retry(
        self, monkeypatch
    ):
        WebhookEvent.objects.create(
            event_id="evt_busy",
            event_type="invoice.paid",
            processing_since=timezone.now(),
        )
        monkeypatch.setattr(
            services,
            "process_stripe_event",
            lambda received: pytest.fail("processed twice"),
        )

        response = deliver(event("invoice.paid", {"id": "in_1"}, event_id="evt_busy"))

        assert response.status_code == 409
        assert response.json()["status"] == "in_progress"

    def test_a_claim_left_by_a_dead_process_is_taken_over(self, monkeypatch):
        stale = timezone.now() - WebhookEvent.CLAIM_LEASE - timedelta(seconds=1)
        WebhookEvent.objects.create(
            event_id="evt_stale", event_type="invoice.paid", processing_since=stale
        )
        monkeypatch.setattr(
            services, "process_stripe_event", lambda received: "processed"
        )

        response = deliver(event("invoice.paid", {"id": "in_1"}, event_id="evt_stale"))

        assert response.status_code == 200
        assert WebhookEvent.objects.get(event_id="evt_stale").success is True

    def test_a_failure_answers_500_and_the_retry_processes_it(self, monkeypatch):
        def boom(received):
            raise RuntimeError("the database went away")

        monkeypatch.setattr(services, "process_stripe_event", boom)
        payload = event("invoice.paid", {"id": "in_1"}, event_id="evt_fail")

        failed = deliver(payload)

        assert failed.status_code == 500
        row = WebhookEvent.objects.get(event_id="evt_fail")
        assert (
            row.success,
            row.processing_since,
            "went away" in row.error_message,
        ) == (False, None, True)
        monkeypatch.setattr(
            services, "process_stripe_event", lambda received: "processed"
        )
        assert deliver(payload).status_code == 200
        assert WebhookEvent.objects.get(event_id="evt_fail").attempts == 2


# --- checkout.session.completed ----------------------------------------------------------------------


class TestACompletedCheckout:
    def live_starter(self, stripe_double, **extra):
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                "sub_new",
                customer="cus_new",
                items=[item("si_plan", "price_starter_month")],
                **extra,
            ),
        )

    def test_the_business_is_on_the_plan_it_paid_for(
        self, shop, stripe_double, hub_double, django_capture_on_commit_callbacks
    ):
        Hub.objects.filter(pk=shop.pk).update(
            status=Hub.Status.ACTIVE, ready_at=timezone.now(), pending_hub_call=""
        )
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription("sub_new", customer="cus_new", items=[item("si_plan", "price_standard_month")]),
        )

        with django_capture_on_commit_callbacks(execute=True):
            response = deliver(
                event(
                    "checkout.session.completed",
                    plan_session(shop, subscription_id="sub_new", metadata={"plan": "standard"}),
                )
            )

        assert response.json()["status"] == "completed"
        mine = local(shop)
        assert (
            mine.plan.slug,
            mine.status,
            mine.billing_interval,
        ) == ("standard", "active", "month")
        assert (
            mine.stripe_subscription_id,
            mine.stripe_customer_id,
        ) == ("sub_new", "cus_new")
        # The period of the current API lives on the subscription item (saas#2328).
        assert int(mine.current_period_start.timestamp()) == MONTH_START
        assert int(mine.current_period_end.timestamp()) == MONTH_END
        assert mine.trial_plan is None
        assert stripe_double.last("subscriptions.retrieve").args == ("sub_new",)
        assert (
            hub_double.calls_to("PUT", "/state")[-1].body["plan"]["slug"] == "standard"
        )

    def test_an_annual_price_is_an_annual_plan(self, shop, stripe_double):
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                "sub_new",
                items=[item("si_plan", "price_starter_year", interval="year")],
            ),
        )

        deliver(
            event(
                "checkout.session.completed",
                plan_session(shop, subscription_id="sub_new"),
            )
        )

        assert local(shop).billing_interval == "year"

    def test_the_trial_stripe_gave_is_kept(self, shop, stripe_double):
        trial_end = int((timezone.now() + timedelta(days=12)).timestamp())
        self.live_starter(
            stripe_double, status="trialing", trial=(MONTH_START, trial_end)
        )

        deliver(
            event(
                "checkout.session.completed",
                plan_session(shop, subscription_id="sub_new"),
            )
        )

        mine = local(shop)
        assert (mine.status, int(mine.trial_end.timestamp())) == (
            "trialing",
            trial_end,
        )

    def test_the_checkout_is_completed_and_its_promo_code_counted_once(
        self, shop, stripe_double
    ):
        PromoCode.objects.create(code="canary_2026", trial_days=30)
        attempt = CheckoutAttempt.objects.create(
            hub=shop,
            kind="plan",
            plan_slug="starter",
            selection="x",
            stripe_session_id="cs_test_1",
            promo_code="canary_2026",
        )
        self.live_starter(stripe_double)
        session = plan_session(
            shop, subscription_id="sub_new", metadata={"promo_code": "canary_2026"}
        )

        deliver(event("checkout.session.completed", session))
        deliver(
            event("checkout.session.completed", session)
        )  # another event of the same session

        attempt.refresh_from_db()
        assert attempt.status == "completed" and attempt.completed_at is not None
        assert PromoCode.objects.get().redemption_count == 1

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
    def test_a_module_bought_on_free_keeps_the_sign_up_trial(
        self, shop, inventory, stripe_double
    ):
        trial_end = local(shop).trial_end
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                "sub_new", items=[item("si_inventory", "price_inventory_month")]
            ),
        )
        session = checkout_session(
            metadata={
                "kind": "module_purchase",
                "hub_id": str(shop.id),
                "module": "inventory",
            },
            subscription_id="sub_new",
        )

        deliver(event("checkout.session.completed", session))

        mine = local(shop)
        assert (
            mine.plan.slug,
            mine.trial_plan.slug,
            mine.trial_end,
        ) == ("free", "starter", trial_end)
        item_row = SubscriptionItem.objects.get(subscription=mine)
        assert (item_row.module_slug, item_row.source, item_row.stripe_item_id) == (
            "inventory",
            "purchase",
            "si_inventory",
        )

    def test_a_second_subscription_for_a_paying_business_is_cancelled_not_applied(self, shop, stripe_double, caplog):
        """Two checkouts paid for one business (review of L2-B): the one the business already has stays; the
        new one is ended at once with a credit for the time not used, and support hears of it."""
        paid = pay(shop, sub_id="sub_1")
        stripe_double.answer("subscriptions.retrieve", subscription("sub_dup", items=[item("si_x", "price_standard_month")]))
        stripe_double.answer("subscriptions.cancel", subscription("sub_dup", status="canceled"))

        with caplog.at_level("ERROR", logger="billing.services"):
            response = deliver(event("checkout.session.completed", plan_session(paid, subscription_id="sub_dup")))

        assert response.json()["status"] == "duplicate_subscription"
        cancelled = stripe_double.last("subscriptions.cancel")
        assert (cancelled.args, cancelled.params) == (("sub_dup",), {"prorate": True, "invoice_now": True})
        assert (local(paid).stripe_subscription_id, local(paid).plan.slug) == ("sub_1", "starter")
        assert any("sub_dup" in record.getMessage() for record in caplog.records)

    def test_the_live_read_happens_under_the_business_lock(self, shop, stripe_double):
        """A webhook reads the live subscription only once it holds the business's row, so an operation in
        between (a cancellation) is never overwritten by an older read (review of L2-B)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        locked_before_reading = []

        with CaptureQueriesContext(connection) as queries:

            def read(call):
                locked_before_reading.append(
                    any("FOR UPDATE" in query["sql"] and '"hubs_hub"' in query["sql"] for query in queries.captured_queries)
                )
                return subscription("sub_new", items=[item("si_plan", "price_starter_month")])

            stripe_double.answer("subscriptions.retrieve", read)
            deliver(event("checkout.session.completed", plan_session(shop, subscription_id="sub_new")))

        assert locked_before_reading == [True]

    def test_a_session_that_is_not_ours_is_ignored(self, shop, stripe_double):
        session = checkout_session(
            metadata={"kind": "assistant_subscription", "hub_id": str(shop.id)}
        )

        response = deliver(event("checkout.session.completed", session))

        assert response.json()["status"] == "ignored"
        assert stripe_double.calls == []
        assert local(shop).plan.slug == "free"

    @pytest.mark.parametrize(
        "hub_id", [None, "not-a-uuid", "0193f0a0-0000-7000-8000-000000000000"]
    )
    def test_a_session_without_a_business_is_acknowledged_without_effect(
        self, stripe_double, hub_id
    ):
        metadata = {"kind": "hub_plan"} | ({"hub_id": hub_id} if hub_id else {})

        response = deliver(
            event("checkout.session.completed", checkout_session(metadata=metadata))
        )

        assert (response.status_code, response.json()["status"]) == (200, "invalid")
        assert stripe_double.calls == []

    def test_a_payment_still_settling_changes_nothing_yet(self, shop, stripe_double):
        session = plan_session(shop, payment_status="unpaid")

        response = deliver(event("checkout.session.completed", session))

        assert response.json()["status"] == "pending"
        assert stripe_double.calls == []

    def test_a_trial_with_nothing_to_pay_now_is_ready(self, shop, stripe_double):
        self.live_starter(stripe_double, status="trialing")

        response = deliver(
            event(
                "checkout.session.completed",
                plan_session(
                    shop,
                    subscription_id="sub_new",
                    payment_status="no_payment_required",
                ),
            )
        )

        assert response.json()["status"] == "completed"
        assert local(shop).stripe_subscription_id == "sub_new"

    def test_stripe_not_answering_is_retried_by_stripe(self, shop, stripe_double):
        stripe_double.answer("subscriptions.retrieve", connection_error())

        response = deliver(
            event(
                "checkout.session.completed",
                plan_session(shop, subscription_id="sub_new"),
            )
        )

        assert response.status_code == 500
        assert local(shop).stripe_subscription_id == ""

    def test_a_delayed_payment_that_failed_closes_the_attempt(self, shop):
        attempt = CheckoutAttempt.objects.create(
            hub=shop,
            kind="plan",
            plan_slug="starter",
            selection="x",
            stripe_session_id="cs_test_1",
        )

        deliver(event("checkout.session.async_payment_failed", plan_session(shop)))

        attempt.refresh_from_db()
        assert attempt.status == "failed"
        assert local(shop).plan.slug == "free"

    def test_an_expired_session_is_not_reused(self, shop):
        attempt = CheckoutAttempt.objects.create(
            hub=shop,
            kind="plan",
            plan_slug="starter",
            selection="x",
            stripe_session_id="cs_test_1",
        )

        deliver(
            event(
                "checkout.session.expired",
                plan_session(shop, status="expired", payment_status="unpaid"),
            )
        )

        attempt.refresh_from_db()
        assert attempt.status == "expired"


# --- customer.subscription.* -------------------------------------------------------------------------


class TestTheLiveSubscriptionDecides:
    def test_a_late_update_writes_the_live_status_plan_and_period(
        self, shop, stripe_double
    ):
        paid = pay(shop)
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                items=[item("si_plan", "price_standard_month")], status="active"
            ),
        )
        stale = subscription(
            items=[item("si_plan", "price_starter_month")], status="past_due"
        )

        deliver(event("customer.subscription.updated", stale))

        subscription_row = local(paid)
        assert (subscription_row.plan.slug, subscription_row.status) == (
            "standard",
            "active",
        )
        assert int(subscription_row.current_period_end.timestamp()) == MONTH_END

    def test_the_live_state_newer_than_the_event_is_written(self, shop, stripe_double):
        paid = pay(shop, plan="standard")
        stripe_double.answer("subscriptions.retrieve", subscription(status="unpaid"))

        deliver(
            event(
                "customer.subscription.updated",
                subscription(items=[item("si_plan", "price_standard_month")]),
            )
        )

        assert (local(paid).plan.slug, local(paid).status) == ("starter", "unpaid")
        assert Hub.objects.get(pk=paid.pk).status == Hub.Status.SUSPENDED

    def test_stripe_not_answering_is_left_to_its_retry(self, shop, stripe_double):
        """Changed from the old SaaS (review of L2-B): the event's snapshot may be stale; nothing is applied
        without the live subscription, and Stripe retries (500)."""
        paid = pay(shop)
        stripe_double.answer("subscriptions.retrieve", connection_error())

        response = deliver(event("customer.subscription.updated", subscription(items=[item("si_plan", "price_standard_month")])))

        assert response.status_code == 500
        assert local(paid).plan.slug == "starter"

    def test_an_unknown_subscription_is_not_read_from_stripe(self, stripe_double):
        response = deliver(
            event("customer.subscription.updated", subscription("sub_nobody"))
        )

        assert response.json()["status"] == "unknown"
        assert stripe_double.calls == []

    def test_the_first_event_of_a_new_subscription_finds_its_business(
        self, shop, stripe_double
    ):
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription("sub_new", metadata={"hub_id": str(shop.id)}),
        )

        deliver(
            event(
                "customer.subscription.created",
                subscription("sub_new", metadata={"hub_id": str(shop.id)}),
            )
        )

        assert local(shop).stripe_subscription_id == "sub_new"

    def test_a_first_paid_invoice_ahead_of_its_checkout_finds_its_business(self, shop, stripe_double):
        """Review of L2-B: Stripe does not order events; ``invoice.paid`` may come before
        ``checkout.session.completed``, and its subscription's metadata names the business."""
        from billing.tests.stripe_double import invoice

        stripe_double.answer("subscriptions.retrieve", subscription("sub_new", metadata={"hub_id": str(shop.id)}))
        paid = invoice("in_first", subscription_id="sub_new", status="paid", amount_paid=0, tax=0)
        paid["parent"]["subscription_details"]["metadata"] = {"hub_id": str(shop.id)}

        assert deliver(event("invoice.paid", paid)).json()["status"] == "processed"
        assert local(shop).stripe_subscription_id == "sub_new"

    def test_a_subscription_of_another_business_is_never_adopted(
        self, shop, stripe_double
    ):
        paid = pay(shop, sub_id="sub_mine")

        response = deliver(
            event(
                "customer.subscription.updated",
                subscription("sub_other", metadata={"hub_id": str(paid.id)}),
            )
        )

        assert response.json()["status"] == "unknown"
        assert local(paid).stripe_subscription_id == "sub_mine"

    def test_an_incomplete_first_payment_changes_nothing(self, shop, stripe_double):
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                "sub_new", status="incomplete", metadata={"hub_id": str(shop.id)}
            ),
        )

        response = deliver(
            event(
                "customer.subscription.created",
                subscription("sub_new", metadata={"hub_id": str(shop.id)}),
            )
        )

        assert response.json()["status"] == "pending"
        assert local(shop).plan.slug == "free"

    def test_an_unknown_price_does_not_change_the_plan(self, shop, stripe_double):
        paid = pay(shop)
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[item("si_x", "price_nobody_sells")]),
        )

        deliver(event("customer.subscription.updated", subscription()))

        assert local(paid).plan.slug == "starter"

    def test_an_old_price_still_brings_the_status_and_the_period(self, shop, stripe_double):
        """BILLING-F21 (saas#2540): after a plan's price changes, its subscribers keep the old one; their
        dunning and their period must still reach erplora.com, with the plan left as it was."""
        paid = pay(shop)
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[item("si_x", "price_nobody_sells")], status="past_due"),
        )

        deliver(event("customer.subscription.updated", subscription()))

        row = local(paid)
        assert (row.plan.slug, row.status) == ("starter", "past_due")
        assert int(row.current_period_end.timestamp()) == MONTH_END

    def test_a_cancellation_made_in_stripe_is_seen(self, shop, stripe_double):
        """BILLING-F21 (saas#2540): a plan cancelled outside the panel (Stripe's dashboard) is cancelled here too,
        so the panel offers «Keep the plan» and stops promising a next invoice."""
        paid = pay(shop)
        stripe_double.answer("subscriptions.retrieve", subscription(cancel_at_period_end=True))

        deliver(event("customer.subscription.updated", subscription()))

        assert local(paid).cancel_at_period_end is True

    def test_the_zero_invoice_of_a_trial_leaves_it_on_trial(self, shop, stripe_double):
        """BILLING-F20 (saas#2540): the 0 € invoice a trial starts with is paid at once; the subscription Stripe
        holds is still trialing, and that is what erplora.com keeps (never «active» before the first charge)."""
        paid = pay(shop)
        stripe_double.answer(
            "subscriptions.retrieve", subscription(status="trialing", trial=(MONTH_START, MONTH_END))
        )

        deliver(event("invoice.paid", invoice(status="paid", amount_due=0, amount_paid=0, tax=0, billing_reason="subscription_create")))

        assert local(paid).status == "trialing"

    def test_the_end_of_the_subscription_takes_the_business_back_to_free(
        self, shop, inventory, stripe_double
    ):
        paid = pay(shop, modules=["inventory"], status="past_due", unpaid_reason="card_declined")
        Hub.objects.filter(pk=paid.pk).update(status=Hub.Status.SUSPENDED, ready_at=timezone.now())

        deliver(event("customer.subscription.deleted", subscription(status="canceled")))

        subscription_row = local(paid)
        assert (
            subscription_row.plan.slug,
            subscription_row.stripe_subscription_id,
            subscription_row.status,
        ) == (
            "free",
            "",
            "active",
        )
        assert subscription_row.items.get().valid_until <= timezone.now()
        assert Hub.objects.get(pk=paid.pk).status == Hub.Status.ACTIVE

    def test_the_end_of_a_deleted_business_creates_nothing_and_moves_nothing(
        self, shop, stripe_double
    ):
        paid = pay(shop)
        Hub.objects.filter(pk=paid.pk).update(
            status=Hub.Status.DELETING, deletion_requested_at=timezone.now()
        )

        deliver(event("customer.subscription.deleted", subscription(status="canceled")))

        assert Hub.objects.get(pk=paid.pk).status == Hub.Status.DELETING
        assert local(paid).stripe_subscription_id == ""
        assert stripe_double.calls == []

    def test_the_end_of_an_unknown_subscription_is_acknowledged(self, stripe_double):
        response = deliver(
            event(
                "customer.subscription.deleted",
                subscription("sub_nobody", status="canceled"),
            )
        )

        assert response.json()["status"] == "unknown"


def test_an_event_body_is_read_as_plain_json_whatever_the_sdk_version(
    shop, stripe_double
):
    """saas#2321 (``test_webhooks_sdk15_compat``): the handlers read dicts, never ``StripeObject.get()``."""
    paid = pay(shop)
    stripe_double.answer(
        "subscriptions.retrieve",
        subscription(items=[item("si_plan", "price_standard_month")]),
    )
    payload = event("customer.subscription.updated", subscription())

    response = deliver(json.loads(json.dumps(payload)))

    assert response.status_code == 200
    assert local(paid).plan.slug == "standard"
