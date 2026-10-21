"""Every live subscription is read again from Stripe and what drifted is put right (BILLING-F38; registry
BILLING-G45, G46).

Ported from ERPlora/saas ``apps/dashboard/hubs/subscriptions/management/commands/sync_subscriptions.py``
(fi:saas/support/hubs#command-sync_subscriptions, origin/develop): each local subscription with a Stripe id is read
from Stripe and its status, cancellation, period and trial written as Stripe says; ``--dry-run`` only reports; a
subscription Stripe does not know is an error and is left alone.

Adapted: the same reading as the webhook (``live_state``, BILLING-F21), so the plan, the period, the bought modules
and the dunning move as a lost ``customer.subscription.updated`` would have moved them, under the business's lock;
the pass is a ``manage.py`` command run by saas-cron that ends with an error when it left something to look at
(the ``task_failed`` alarm). An ended subscription (no Stripe id any more) is not read.
"""

import logging

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from billing import services
from billing.tests.conftest import pay
from billing.tests.stripe_double import connection_error, invalid_request, item, subscription
from hubs.models import Subscription

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


STARTER = [item("si_plan", "price_starter_month")]


def in_step(hub, stripe_double, *, sub_id="sub_1", customer="cus_1"):
    """The business paying Starter exactly as Stripe has it (what the last webhook left)."""
    paid = pay(hub, sub_id=sub_id, customer=customer)
    services.apply_live(paid.id, subscription(sub_id, customer=customer, items=STARTER))
    return Subscription.objects.select_related("hub", "plan").get(hub=paid)


def stripe_has(stripe_double, **live):
    stripe_double.answer("subscriptions.retrieve", subscription(items=live.pop("items", STARTER), **live))


def local(hub_id) -> Subscription:
    return Subscription.objects.select_related("plan").get(hub_id=hub_id)


class TestOneSubscription:
    def test_one_in_step_with_stripe_is_left_alone(self, shop, stripe_double):
        mine = in_step(shop, stripe_double)
        stripe_has(stripe_double)

        assert services.sync_subscription(mine) == "in_sync"
        assert local(shop.id).updated_at == mine.updated_at

    def test_a_cancellation_whose_event_never_arrived_is_applied(self, shop, stripe_double, caplog):
        mine = in_step(shop, stripe_double)
        stripe_has(stripe_double, cancel_at_period_end=True)

        with caplog.at_level(logging.WARNING, logger="billing.services"):
            assert services.sync_subscription(mine) == "fixed"

        assert local(shop.id).cancel_at_period_end is True
        drift = [r for r in caplog.records if getattr(r, "event", "") == "billing.subscription_drift"]
        assert [(r.hub_id, r.fields) for r in drift] == [(str(shop.id), ["cancel_at_period_end"])]

    def test_a_plan_changed_in_stripe_is_applied(self, shop, stripe_double):
        mine = in_step(shop, stripe_double)
        stripe_has(stripe_double, items=[item("si_plan", "price_standard_year", interval="year")])

        assert services.sync_subscription(mine) == "fixed"

        now = local(shop.id)
        assert (now.plan.slug, now.billing_interval) == ("standard", "year")

    def test_a_module_added_in_stripe_is_applied(self, shop, stripe_double, inventory):
        mine = in_step(shop, stripe_double)
        stripe_has(stripe_double, items=[*STARTER, item("si_inventory", "price_inventory_month")])

        assert services.sync_subscription(mine) == "fixed"

        assert list(local(shop.id).items.filter(source="purchase").values_list("module_slug", flat=True)) == [
            "inventory"
        ]

    def test_one_that_ended_in_stripe_puts_the_business_back_on_free(self, shop, stripe_double):
        mine = in_step(shop, stripe_double)
        stripe_has(stripe_double, status="canceled")

        assert services.sync_subscription(mine) == "fixed"

        now = local(shop.id)
        assert (now.plan.slug, now.stripe_subscription_id) == ("free", "")

    def test_a_dry_run_reports_the_drift_and_writes_nothing(self, shop, stripe_double):
        mine = in_step(shop, stripe_double)
        stripe_has(stripe_double, cancel_at_period_end=True)

        assert services.sync_subscription(mine, apply=False) == "drifted"

        now = local(shop.id)
        assert now.cancel_at_period_end is False
        assert now.updated_at == mine.updated_at

    def test_one_stripe_does_not_know_is_left_alone(self, shop, stripe_double):
        mine = in_step(shop, stripe_double)
        stripe_double.answer("subscriptions.retrieve", invalid_request())

        assert services.sync_subscription(mine) == "missing"

        now = local(shop.id)
        assert (now.plan.slug, now.stripe_subscription_id, now.updated_at) == ("starter", "sub_1", mine.updated_at)

    def test_one_still_being_paid_for_the_first_time_waits(self, shop, stripe_double):
        mine = in_step(shop, stripe_double)
        stripe_has(stripe_double, status="incomplete")

        assert services.sync_subscription(mine) == "pending"
        assert local(shop.id).status == "active"


class TestThePass:
    def test_every_live_subscription_is_read_and_one_failure_never_stops_the_others(
        self, shop, owner, stripe_double
    ):
        from hubs.tests.conftest import create_business

        first = in_step(shop, stripe_double)
        second = in_step(create_business(owner, name="Bar Olga"), stripe_double, sub_id="sub_2", customer="cus_2")
        answers = {
            "sub_1": connection_error(),
            "sub_2": subscription("sub_2", customer="cus_2", items=STARTER, cancel_at_period_end=True),
        }
        stripe_double.answer("subscriptions.retrieve", lambda call: answers[call.args[0]])

        counts = services.sync_subscriptions()

        assert counts == {"checked": 2, "in_sync": 0, "fixed": 1, "drifted": 0, "pending": 0, "missing": 0, "errors": 1}
        assert local(second.hub_id).cancel_at_period_end is True
        assert local(first.hub_id).updated_at == first.updated_at

    def test_a_business_on_free_is_not_read(self, shop, stripe_double):
        counts = services.sync_subscriptions()

        assert counts["checked"] == 0
        assert stripe_double.calls_to("subscriptions.retrieve") == []


class TestTheCommand:
    def test_it_puts_the_drift_right_and_says_what_it_did(self, shop, stripe_double, capsys):
        in_step(shop, stripe_double)
        stripe_has(stripe_double, cancel_at_period_end=True)

        call_command("sync_subscriptions")

        assert capsys.readouterr().out.strip() == (
            "sync_subscriptions: checked=1 in_sync=0 fixed=1 drifted=0 pending=0 missing=0 errors=0"
        )
        assert local(shop.id).cancel_at_period_end is True

    def test_dry_run_only_reports(self, shop, stripe_double, capsys):
        in_step(shop, stripe_double)
        stripe_has(stripe_double, cancel_at_period_end=True)

        call_command("sync_subscriptions", "--dry-run")

        assert "drifted=1" in capsys.readouterr().out
        assert local(shop.id).cancel_at_period_end is False

    def test_what_it_could_not_read_ends_the_run_with_an_error(self, shop, stripe_double):
        in_step(shop, stripe_double)
        stripe_double.answer("subscriptions.retrieve", invalid_request())

        with pytest.raises(CommandError, match="missing=1"):
            call_command("sync_subscriptions")
