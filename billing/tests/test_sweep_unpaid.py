"""``manage.py sweep_unpaid``: the safety net of unpaid plans and deleted businesses (``saas-cron``).

With recorded Stripe fixtures (``fixtures/stripe_unpaid_plan/``: a test-clock renewal that failed once):

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
import logging
import time
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from billing.models import PaymentFailure
from billing.services import unpaid_sweep
from billing.tests.conftest import pay
from billing.tests.stripe_double import (
    DAY,
    connection_error,
    invalid_request,
    invoice,
    listing,
    subscription,
)
from hubs.models import BillingProfile, Hub, Subscription

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
        """The sweep replays to decide; it is not a failed payment."""
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
        """The sweep applies the live subscription when it is no longer unpaid (a payment whose
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
        from hubs.services import deletion
        from hubs.models import HubMember
        from hubs.schemas.businesses import BusinessDeleteIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        business = pay(hub, **paid)
        owner = HubMember.objects.get(hub=business, role=HubMember.Role.OWNER).user
        deletion.business_delete(hub_ctx(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name))
        return business

    def test_a_business_restored_before_the_sweep_stops_paying_too(self, shop, owner, stripe_double):
        """Deleting asked for the end; recovering it (on Free) does not take that back."""
        from hubs.services import deletion
        from hubs.schemas.common import ByIdIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        business = self.deleted(shop)
        deletion.business_restore(hub_ctx(owner), ByIdIn(id=business.id))
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

    def test_nothing_is_invoiced_for_a_plan_cancelled_and_then_deleted(self, shop, owner, stripe_double):
        """The only thing Stripe is asked for a deleted business is to end its subscription now, with no final
        invoice; Billing then has no row of it left, so no invoice of 0 € comes at the end of its period."""
        from billing import queries
        from billing.schemas.subscriptions import SubscriptionListIn
        from billing.tests.conftest import ctx_for

        self.deleted(shop, cancel_at_period_end=True)
        stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))

        run()

        writes = [call for call in stripe_double.calls if not call.path.endswith((".list", ".retrieve"))]
        assert [(call.path, call.args, call.params) for call in writes] == [("subscriptions.cancel", ("sub_1",), {})]
        assert queries.subscription_list(ctx_for(owner), SubscriptionListIn()).rows == []

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

        monkeypatch.setattr(
            unpaid_sweep,
            "sweep_unpaid",
            lambda: Counter({key: 0 for key in unpaid_sweep.SWEEP_COUNTS}) + Counter(mail_failed=1),
        )

        with pytest.raises(CommandError):
            run()

    def test_with_nothing_to_do_nothing_is_asked(self, settings, stripe_double):
        settings.STRIPE_SECRET_KEY = ""

        assert "checked=0" in run()


def another(make_user, email="b@example.com", name="Bar B"):
    from hubs.tests.conftest import create_business

    return create_business(make_user(email), name=name)


def said(caplog):
    return [record.getMessage() for record in caplog.records if record.name == "billing.services"]


class TestWhatARunSaysOfThePlansInDunning:
    def test_every_plan_looked_at_is_counted_and_one_inside_its_grace_is_not_suspended(self, shop, stripe_double):
        owing(shop)
        stripe_double.answer("invoices.list", listing([open_invoice(6)]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))

        output = run()

        assert "checked=1 suspended=0" in output

    def test_they_are_looked_at_in_the_order_they_were_opened(self, shop, stripe_double, make_user):
        owing(shop, sub_id="sub_first")
        owing(another(make_user), sub_id="sub_second")
        stripe_double.answer("invoices.list", listing([]))

        run()

        assert [call.params["subscription"] for call in stripe_double.calls_to("invoices.list")] == [
            "sub_first",
            "sub_second",
        ]

    def test_a_plan_without_a_stripe_subscription_is_not_looked_at(self, shop, stripe_double):
        business = owing(shop)
        Subscription.objects.filter(hub=business).update(stripe_subscription_id="")

        output = run()

        assert "checked=0" in output
        assert stripe_double.calls == []

    def test_an_open_invoice_without_a_date_is_the_oldest(self, shop, stripe_double):
        owing(shop)
        undated = {**open_invoice(2, "in_undated"), "created": None}
        stripe_double.answer("invoices.list", listing([open_invoice(9, "in_old"), undated]))
        stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))

        run()

        assert PaymentFailure.objects.get().stripe_invoice_id == "in_undated"

    def test_one_that_could_not_be_read_is_an_error_and_nothing_else(self, shop, stripe_double, caplog):
        """Suspended by the webhook while Stripe did not answer the sweep: it is not the sweep's suspension."""
        business = owing(shop)

        def suspended_meanwhile(call):
            Hub.objects.filter(pk=business.pk).update(status=Hub.Status.SUSPENDED, suspended_at=timezone.now())
            return connection_error()

        stripe_double.answer("invoices.list", suspended_meanwhile)

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            counts = unpaid_sweep.sweep_unpaid()

        assert (counts["checked"], counts["suspended"], counts["errors"]) == (1, 0, 1)
        assert said(caplog) == ["[UNPAID SWEEP] sub_1 could not be swept"]
        assert caplog.records[0].exc_info

    def test_without_stripe_each_one_is_an_error_that_names_it(self, shop, settings, stripe_double, make_user, caplog):
        owing(shop, sub_id="sub_first")
        owing(another(make_user), sub_id="sub_second")
        settings.STRIPE_SECRET_KEY = ""

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            counts = unpaid_sweep.sweep_unpaid()

        assert (counts["checked"], counts["errors"]) == (2, 2)
        assert said(caplog) == [
            "[UNPAID SWEEP] Stripe is not configured: sub_first is not swept",
            "[UNPAID SWEEP] Stripe is not configured: sub_second is not swept",
        ]


class TestWhatARunSaysOfTheDeletedBusinesses:
    def asked_to_end(self, hub, sub_id="sub_1"):
        business = pay(hub, sub_id=sub_id)
        Subscription.objects.filter(hub=business).update(cancel_requested_at=timezone.now())
        return business

    def test_they_are_ended_in_the_order_they_were_opened(self, shop, stripe_double, make_user):
        self.asked_to_end(shop, "sub_first")
        self.asked_to_end(another(make_user), "sub_second")
        stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))

        output = run()

        assert [call.args for call in stripe_double.calls_to("subscriptions.cancel")] == [
            ("sub_first",),
            ("sub_second",),
        ]
        assert "cancelled=2" in output

    def test_one_suspended_too_long_is_deleted_and_ended_in_the_same_pass(self, shop, stripe_double):
        business = pay(shop, status="past_due")
        long_ago = timezone.now() - timedelta(days=181)
        Hub.objects.filter(pk=business.pk).update(
            status=Hub.Status.SUSPENDED,
            suspended_at=long_ago,
            suspension_final_notice_at=timezone.now() - timedelta(days=31),
        )
        stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))

        output = run()

        assert "cancelled=1" in output and "expired=1" in output
        assert status_of(business) == Hub.Status.DELETING
        assert Subscription.objects.get(hub=business).stripe_subscription_id == ""

    def test_one_with_nothing_left_in_stripe_is_not_ended_again(self, shop, stripe_double):
        business = self.asked_to_end(shop)
        Subscription.objects.filter(hub=business).update(stripe_subscription_id="")

        output = run()

        assert "cancelled=0" in output
        assert stripe_double.calls == []

    def test_one_that_could_not_be_ended_is_an_error_and_the_next_one_is_ended(
        self, shop, stripe_double, make_user, caplog
    ):
        kept = self.asked_to_end(shop, "sub_first")
        ended = self.asked_to_end(another(make_user), "sub_second")
        stripe_double.answer(
            "subscriptions.cancel",
            lambda call: connection_error() if call.args == ("sub_first",) else subscription(status="canceled"),
        )

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            counts = unpaid_sweep.sweep_unpaid()

        assert (counts["cancelled"], counts["errors"]) == (1, 1)
        assert said(caplog) == [f"[UNPAID SWEEP] The billing of deleted hub {kept.pk} could not be ended"]
        assert caplog.records[0].exc_info
        assert Subscription.objects.get(hub=ended).stripe_subscription_id == ""

    def test_without_stripe_each_one_is_an_error_that_names_it_and_is_kept(
        self, shop, settings, stripe_double, caplog
    ):
        business = self.asked_to_end(shop)
        settings.STRIPE_SECRET_KEY = ""

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            counts = unpaid_sweep.sweep_unpaid()

        assert (counts["cancelled"], counts["errors"]) == (0, 1)
        assert said(caplog) == [f"[UNPAID SWEEP] Stripe is not configured: deleted hub {business.pk} still pays"]
        assert stripe_double.calls == []
        assert Subscription.objects.get(hub=business).stripe_subscription_id == "sub_1"


class TestWhatARunSaysOfThePayersOfDeletedAccounts:
    def departed(self, hub, *, customer=""):
        BillingProfile.objects.filter(pk=hub.billing_profile_id).update(
            forget_after=timezone.now() + timedelta(days=1), stripe_customer_id=customer
        )
        return hub.billing_profile_id

    def test_one_held_by_a_live_subscription_is_not_counted(self, shop, stripe_double):
        profile_id = self.departed(shop)
        pay(shop)

        output = run()

        assert "payers_forgotten=0" in output
        assert BillingProfile.objects.filter(pk=profile_id).exists()

    def test_one_that_could_not_be_forgotten_is_an_error_and_the_next_one_goes(
        self, shop, stripe_double, make_user, caplog
    ):
        kept = self.departed(shop, customer="cus_first")
        gone = self.departed(another(make_user), customer="cus_second")
        stripe_double.answer(
            "customers.delete",
            lambda call: connection_error() if call.args == ("cus_first",) else {"id": "cus_second", "deleted": True},
        )

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            counts = unpaid_sweep.sweep_unpaid()

        assert (counts["payers_forgotten"], counts["errors"]) == (1, 1)
        assert said(caplog) == [f"[UNPAID SWEEP] The payer {kept} of a deleted account could not be forgotten"]
        assert caplog.records[0].exc_info
        assert list(BillingProfile.objects.filter(pk__in=[kept, gone]).values_list("pk", flat=True)) == [kept]


class TestWhatARunSaysOfTheMailsStillOwed:
    """The mails of an unpaid episode that could not leave, in the order the businesses were opened."""

    def untold(self, hub, invoice_id="in_1", status=Hub.Status.PAST_DUE):
        Hub.objects.filter(pk=hub.pk).update(
            status=status, suspended_at=timezone.now() if status == Hub.Status.SUSPENDED else None
        )
        return PaymentFailure.objects.create(
            hub=hub,
            stripe_invoice_id=invoice_id,
            reason=PaymentFailure.Reason.PAYMENT_FAILED,
            invoice_created_at=timezone.now() - timedelta(days=3),
        )

    def test_a_suspension_nobody_was_told_of_is_told(self, shop, mailoutbox):
        self.untold(shop, status=Hub.Status.SUSPENDED)

        counts = unpaid_sweep.sweep_unpaid()

        assert [message.extra_headers["X-ERPlora-Notice"] for message in mailoutbox] == ["billing.business_suspended"]
        assert (counts["notified"], counts["mail_failed"]) == (1, 0)

    def test_they_are_told_in_the_order_they_were_opened(self, shop, make_user, mailoutbox):
        second = another(make_user, "second@example.com")
        self.untold(second, "in_2")
        self.untold(shop, "in_1")

        counts = unpaid_sweep.sweep_unpaid()

        assert [message.to for message in mailoutbox] == [["owner@example.com"], ["second@example.com"]]
        assert counts["notified"] == 2

    def test_one_that_crashes_still_owes_its_mail_and_the_next_one_is_told(
        self, shop, make_user, mailoutbox, monkeypatch, caplog
    ):
        from billing import emails

        self.untold(shop, "in_1")
        self.untold(another(make_user, "second@example.com"), "in_2")
        send = emails.send_payment_failed

        def crash(hub, *args, **kwargs):
            if hub.pk == shop.pk:
                raise RuntimeError("template")
            return send(hub, *args, **kwargs)

        monkeypatch.setattr(emails, "send_payment_failed", crash)

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            counts = unpaid_sweep.sweep_unpaid()

        assert (counts["notified"], counts["mail_failed"], counts["errors"]) == (1, 1, 0)
        assert [message.to for message in mailoutbox] == [["second@example.com"]]
        assert said(caplog) == [f"[UNPAID SWEEP] The payer of hub {shop.pk} could not be told"]
        assert caplog.records[0].exc_info

    def test_one_paid_meanwhile_is_neither_told_nor_owed(self, shop, make_user, mailoutbox, monkeypatch):
        from billing import emails

        self.untold(shop, "in_1")
        paid = self.untold(another(make_user, "second@example.com"), "in_2")
        send = emails.send_payment_failed

        def paid_meanwhile(*args, **kwargs):
            PaymentFailure.objects.filter(pk=paid.pk).update(resolved_at=timezone.now())
            return send(*args, **kwargs)

        monkeypatch.setattr(emails, "send_payment_failed", paid_meanwhile)

        counts = unpaid_sweep.sweep_unpaid()

        assert (counts["notified"], counts["mail_failed"]) == (1, 0)
        assert [message.to for message in mailoutbox] == [["owner@example.com"]]
