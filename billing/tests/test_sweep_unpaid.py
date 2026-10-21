"""``manage.py sweep_unpaid``: the safety net of unpaid plans and deleted businesses (``saas-cron``; lot L2-B).

Ported from ERPlora/saas ``hubs/main/tests/test_unpaid_plan_sweep.py`` (12, saas#2594) with its recorded
Stripe fixtures (``fixtures/stripe_unpaid_plan/``: a test-clock renewal that failed once) and the Stripe half
of ``test_hub_delete_cancels_billing.py`` (9 × 5 paths):

- The webhook only acts when Stripe sends an event, and how many retries Stripe makes (and what it does
  once they are spent) is set in its dashboard: retries that end before the 7 days leave the subscription
  ``past_due`` and send nothing more. The sweep replays each business in dunning with its OLDEST open
  invoice through the same rules as ``invoice.payment_failed`` (the live subscription decides; ``unpaid`` at
  once; else past the grace; one suspension).
- A deleted business stops paying: its Stripe subscription is cancelled NOW (``resource_missing`` counts as
  ended); a failure keeps it for the next run and the run fails (the ``task_failed`` alarm). The business
  never deletes itself here: purging is the Hub's (90 days).
- Idempotent, under the advisory lock ``hashtext('erplora.saas.sweep_unpaid')`` (a second run returns at
  once), one business never stops the others.

Dropped with reason: Celery beat (a ``saas-cron`` schedule of ``aws-next`` instead), the container pause and
the suspension e-mail tasks; the deletion paths of the old SaaS (operator purge, six-year cleanup, free and
suspended sweeps), which were container teardowns.
"""

import json
import time
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from billing.tests.conftest import pay
from billing.tests.stripe_double import (
    DAY,
    connection_error,
    invalid_request,
    invoice,
    listing,
    subscription,
)
from hubs.models import Hub, Subscription

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures" / "stripe_unpaid_plan"
LOCK_KEY = "hashtext('erplora.saas.sweep_unpaid')"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("invoice_payments.list", listing([]))
    return stripe_double


def recorded(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def run():
    out = StringIO()
    call_command("sweep_unpaid", stdout=out)
    return out.getvalue()


def owing(hub, *, status="past_due", sub_id="sub_1"):
    paid = pay(hub, status=status, sub_id=sub_id, unpaid_reason="payment_failed")
    Hub.objects.filter(pk=paid.pk).update(
        status=Hub.Status.PAST_DUE, ready_at=timezone.now(), pending_hub_call=""
    )
    return Hub.objects.get(pk=paid.pk)


def open_invoice(days, invoice_id="in_1", sub_id="sub_1"):
    return invoice(
        invoice_id, subscription_id=sub_id, created=int(time.time()) - days * DAY
    )


def status_of(hub):
    return Hub.objects.get(pk=hub.pk).status


class TestTheRecordedFixturesAreWhatTheCodeReads:
    def test_the_captured_event_is_a_failed_renewal_of_a_past_due_subscription(self):
        failed = recorded("payment_failed_event")
        live = recorded("live_subscription")
        listed = recorded("open_invoices")

        assert failed["type"] == "invoice.payment_failed"
        assert failed["data"]["object"]["billing_reason"] == "subscription_cycle"
        assert failed["data"]["object"]["subscription"] == live["id"]
        assert listed["data"][0]["id"] == failed["data"]["object"]["id"]
        assert live["status"] == "past_due"

    def test_the_recorded_open_invoice_suspends_once_its_grace_is_over(
        self, shop, stripe_double
    ):
        live = recorded("live_subscription")
        listed = recorded("open_invoices")
        listed["data"][0]["created"] = int(time.time()) - 8 * DAY
        business = owing(shop, sub_id=live["id"])
        stripe_double.answer("invoices.list", listed)
        stripe_double.answer("subscriptions.retrieve", live)

        run()

        assert status_of(business) == Hub.Status.SUSPENDED
        assert stripe_double.last("invoices.list").params == {
            "subscription": live["id"],
            "status": "open",
            "limit": 100,
        }


class TestStripeStopsRetryingBeforeTheGraceEnds:
    def test_the_business_is_suspended_once_the_grace_is_over_without_another_event(
        self, shop, stripe_double
    ):
        business = owing(shop)
        stripe_double.answer("invoices.list", listing([open_invoice(8)]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))

        output = run()

        assert status_of(business) == Hub.Status.SUSPENDED
        assert "suspended=1" in output

    def test_a_run_does_not_count_a_failure_stripe_did_not_have(self, shop, stripe_double):
        """The sweep replays to decide; it is not a failed payment (review of L2-B)."""
        from billing.models import PaymentFailure

        owing(shop)
        stripe_double.answer("invoices.list", listing([open_invoice(3)]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))
        run()
        first = PaymentFailure.objects.get()

        run()

        again = PaymentFailure.objects.get()
        assert (again.attempts, again.failed_at) == (first.attempts, first.failed_at)

    def test_a_second_run_reads_nothing_more(self, shop, stripe_double):
        owing(shop)
        stripe_double.answer("invoices.list", listing([open_invoice(8)]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))
        run()
        calls = len(stripe_double.calls)

        output = run()

        assert len(stripe_double.calls) == calls
        assert "suspended=0" in output

    def test_inside_the_grace_the_business_keeps_working(self, shop, stripe_double):
        business = owing(shop)
        stripe_double.answer("invoices.list", listing([open_invoice(6)]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))

        run()

        assert status_of(business) == Hub.Status.PAST_DUE

    def test_the_oldest_open_invoice_starts_the_grace(self, shop, stripe_double):
        business = owing(shop)
        stripe_double.answer(
            "invoices.list",
            listing([open_invoice(2, "in_new"), open_invoice(9, "in_old")]),
        )
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))

        run()

        assert status_of(business) == Hub.Status.SUSPENDED

    def test_stripes_unpaid_verdict_suspends_without_waiting(self, shop, stripe_double):
        business = owing(shop, status="unpaid")
        stripe_double.answer("invoices.list", listing([open_invoice(3)]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="unpaid"))

        run()

        assert status_of(business) == Hub.Status.SUSPENDED


class TestTheSweepLeavesAloneWhoPaidOrOwesNothing:
    def test_a_plan_collected_meanwhile_is_brought_back(self, shop, stripe_double):
        """Review of L2-B: the sweep applies the live subscription when it is no longer unpaid (a payment whose
        event was lost), instead of leaving «payment pending» for ever."""
        business = owing(shop)
        stripe_double.answer("invoices.list", listing([open_invoice(10)]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="active"))

        run()

        assert status_of(business) == Hub.Status.ACTIVE
        assert Subscription.objects.get(hub=business).status == "active"

    def test_no_open_invoice_means_nothing_is_owed(self, shop, stripe_double):
        business = owing(shop)
        stripe_double.answer("invoices.list", listing([]))

        run()

        assert status_of(business) == Hub.Status.PAST_DUE
        assert stripe_double.calls_to("subscriptions.retrieve") == []

    def test_only_owed_plans_of_businesses_still_running_are_read(
        self, owner, shop, stripe_double, plans, make_user
    ):
        from hubs.tests.conftest import create_business

        owing(shop, sub_id="sub_owed")
        for index, (status, hub_status) in enumerate(
            [
                ("active", Hub.Status.ACTIVE),
                ("trialing", Hub.Status.ACTIVE),
                ("past_due", Hub.Status.SUSPENDED),
            ]
        ):
            other = pay(
                create_business(
                    make_user(f"o{index}@example.com"), name=f"Bar {index}"
                ),
                status=status,
                sub_id=f"sub_{index}",
            )
            Hub.objects.filter(pk=other.pk).update(status=hub_status)
        create_business(make_user("free@example.com"), name="Free Bar")
        stripe_double.answer("invoices.list", listing([]))

        run()

        assert [
            call.params["subscription"]
            for call in stripe_double.calls_to("invoices.list")
        ] == ["sub_owed"]

    def test_an_unreachable_stripe_skips_that_business_and_goes_on(
        self, shop, owner, stripe_double, make_user
    ):
        from hubs.tests.conftest import create_business

        first = owing(shop, sub_id="sub_a")
        second = owing(
            create_business(make_user("b@example.com"), name="Bar B"), sub_id="sub_b"
        )
        stripe_double.answer(
            "invoices.list",
            lambda call: (
                connection_error()
                if call.params["subscription"] == "sub_a"
                else listing([open_invoice(9, sub_id="sub_b")])
            ),
        )
        stripe_double.answer(
            "subscriptions.retrieve", subscription("sub_b", status="past_due")
        )

        with pytest.raises(CommandError) as failed:
            run()

        assert "errors=1" in str(failed.value)
        assert (status_of(first), status_of(second)) == (
            Hub.Status.PAST_DUE,
            Hub.Status.SUSPENDED,
        )


class TestADeletedBusinessStopsPaying:
    def deleted(self, hub, **paid):
        """Deleted through ``hubs.business.delete``, which asks for its Stripe subscription to end."""
        from hubs import services as hub_services
        from hubs.models import HubMember
        from hubs.schemas import BusinessDeleteIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        business = pay(hub, **paid)
        owner = HubMember.objects.get(hub=business, role=HubMember.Role.OWNER).user
        hub_services.business_delete(hub_ctx(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name))
        return business

    def test_a_business_restored_before_the_sweep_stops_paying_too(self, shop, owner, stripe_double):
        """Review of L2-B: deleting asked for the end; recovering it (on Free) does not take that back."""
        from hubs import services as hub_services
        from hubs.schemas import ByIdIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        business = self.deleted(shop)
        hub_services.business_restore(hub_ctx(owner), ByIdIn(id=business.id))
        stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))

        run()

        assert stripe_double.last("subscriptions.cancel").args == ("sub_1",)
        local = Subscription.objects.get(hub=business)
        assert (local.stripe_subscription_id, local.cancel_requested_at) == ("", None)

    def test_its_subscription_is_cancelled_now(self, shop, stripe_double):
        business = self.deleted(shop)
        stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))

        output = run()

        assert stripe_double.last("subscriptions.cancel").args == ("sub_1",)
        local = Subscription.objects.select_related("plan").get(hub=business)
        assert (local.stripe_subscription_id, local.plan.slug) == ("", "free")
        assert status_of(business) == Hub.Status.DELETING
        assert "cancelled=1" in output

    def test_one_cancelled_at_the_period_end_is_ended_now_too(
        self, shop, stripe_double
    ):
        self.deleted(shop, cancel_at_period_end=True)
        stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))

        run()

        assert stripe_double.calls_to("subscriptions.cancel")

    def test_a_subscription_stripe_no_longer_has_counts_as_ended(
        self, shop, stripe_double
    ):
        business = self.deleted(shop)
        stripe_double.answer(
            "subscriptions.cancel", invalid_request("resource_missing")
        )

        run()

        assert Subscription.objects.get(hub=business).stripe_subscription_id == ""

    def test_a_failed_cancellation_is_kept_for_the_next_run(self, shop, stripe_double):
        business = self.deleted(shop)
        stripe_double.answer("subscriptions.cancel", connection_error())

        with pytest.raises(CommandError):
            run()

        assert Subscription.objects.get(hub=business).stripe_subscription_id == "sub_1"

    def test_only_the_deleted_businesses_are_touched(
        self, shop, owner, stripe_double, make_user
    ):
        from hubs.tests.conftest import create_business

        self.deleted(shop)
        alive = pay(
            create_business(make_user("alive@example.com"), name="Alive"),
            sub_id="sub_alive",
        )
        stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))

        run()

        assert [
            call.args for call in stripe_double.calls_to("subscriptions.cancel")
        ] == [("sub_1",)]
        assert Subscription.objects.get(hub=alive).stripe_subscription_id == "sub_alive"


class TestTheRun:
    def test_a_second_run_returns_at_once_while_one_holds_the_lock(
        self, shop, stripe_double, other_session
    ):
        owing(shop)
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
        try:
            output = run()
        finally:
            other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

        assert "already running" in output
        assert stripe_double.calls == []

    def test_the_lock_is_released_after_a_run(self, other_session):
        run()

        taken = other_session.execute(
            f"SELECT pg_try_advisory_lock({LOCK_KEY})"
        ).fetchone()[0]
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
        assert taken is True

    def test_without_stripe_work_to_do_is_an_error(self, shop, settings, stripe_double):
        owing(shop)
        settings.STRIPE_SECRET_KEY = ""

        with pytest.raises(CommandError):
            run()

        assert stripe_double.calls == []

    def test_a_mail_of_the_unpaid_episode_still_owed_is_an_error(self, monkeypatch, stripe_double):
        """BILLING-F16: the run fails while a payer is still owed their mail, so the cron alarm says it."""
        from collections import Counter

        from billing import services

        monkeypatch.setattr(
            services, "sweep_unpaid", lambda: Counter({key: 0 for key in services.SWEEP_COUNTS}) + Counter(mail_failed=1)
        )

        with pytest.raises(CommandError):
            run()

    def test_with_nothing_to_do_nothing_is_asked(self, settings, stripe_double):
        settings.STRIPE_SECRET_KEY = ""

        assert "checked=0" in run()
