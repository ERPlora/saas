"""What the live Stripe subscription says of a business (``live_state``): its plan and how often it is billed, its
modules, its period and its trial, its card and what it owes. Read by the webhook, the operations and the nightly
reading of Stripe, which write it through ``hubs.subscription.apply``."""

import logging
from datetime import datetime, timedelta, timezone as tz

import pytest
from django.utils import timezone

from billing.models import PaymentFailure
from billing.services.live_subscriptions import live_state
from billing.tests.conftest import pay
from billing.tests.stripe_double import DAY, MONTH_END, MONTH_START, item, subscription
from hubs.models import Subscription, SubscriptionItem

pytestmark = pytest.mark.django_db

PLAN = item("si_plan", "price_starter_month")
PLAN_ANNUAL = item("si_plan", "price_standard_year", interval="year")
MODULE = item("si_inventory", "price_inventory_month")
MODULE_ANNUAL = item("si_inventory", "price_inventory_year", interval="year")


def moment(timestamp):
    return datetime.fromtimestamp(timestamp, tz=tz.utc)


def rights(state):
    return {right.module_slug: (right.stripe_item_id, right.valid_until) for right in state["modules"]}


def bought(hub, slug="inventory", *, source="purchase", **fields):
    return SubscriptionItem.objects.create(
        subscription=Subscription.objects.get(hub=hub), module_slug=slug, source=source, **fields
    )


def declined(hub, *, method="pm_old", days=3):
    return PaymentFailure.objects.create(
        hub=hub,
        stripe_invoice_id="in_1",
        stripe_customer_id="cus_1",
        reason=PaymentFailure.Reason.CARD_DECLINED,
        payment_method_id=method,
        invoice_created_at=timezone.now() - timedelta(days=days),
    )


class TestItsPlan:
    def test_the_plan_says_how_often_it_is_billed_when_its_module_comes_first(self, shop, inventory):
        state = live_state(shop, subscription(items=[MODULE_ANNUAL, PLAN]))

        assert (state["plan"], state["billing_interval"]) == ("starter", "month")

    def test_the_plan_says_how_often_it_is_billed_when_its_module_comes_last(self, shop, inventory):
        state = live_state(shop, subscription(items=[PLAN_ANNUAL, MODULE]))

        assert (state["plan"], state["billing_interval"]) == ("standard", "year")

    def test_modules_alone_are_on_free_billed_as_often_as_they_are(self, shop, inventory):
        paid = pay(shop, modules=["inventory"])

        state = live_state(paid, subscription(items=[MODULE_ANNUAL]))

        assert (state["plan"], state["billing_interval"]) == ("free", "year")

    @pytest.mark.parametrize(
        "line, named",
        [(item("si_x", "price_nobody_sells"), "price_nobody_sells"), ({**PLAN, "price": None}, "")],
        ids=["unknown price", "no price"],
    )
    def test_a_line_nobody_sells_says_nothing_of_the_plan_and_is_an_error(self, shop, caplog, line, named):
        with caplog.at_level(logging.ERROR, logger="billing.services"):
            state = live_state(shop, subscription(items=[line]))

        assert {"plan", "billing_interval", "trial_start", "trial_end"}.isdisjoint(state)
        assert [record.getMessage() for record in caplog.records] == [
            f"[BILLING] Stripe bills hub {shop.id} a price nobody sells: {named}"
        ]

    def test_a_plan_is_read_next_to_a_line_nobody_sells(self, shop):
        state = live_state(shop, subscription(items=[item("si_x", "price_nobody_sells"), PLAN]))

        assert (state["plan"], state["billing_interval"]) == ("starter", "month")

    def test_a_plan_brings_its_own_trial(self, shop):
        state = live_state(shop, subscription(status="trialing", trial=(MONTH_START, MONTH_END)))

        assert (state["trial_start"], state["trial_end"]) == (moment(MONTH_START), moment(MONTH_END))


class TestItsModules:
    def test_one_billed_is_open_ended(self, shop, inventory):
        state = live_state(shop, subscription(items=[PLAN, MODULE]))

        assert rights(state) == {"inventory": ("si_inventory", None)}

    @pytest.mark.parametrize("ending", [{"cancel_at_period_end": True}, {"cancel_at": MONTH_END}])
    def test_one_of_a_subscription_that_ends_lasts_as_long_as_its_period(self, shop, inventory, ending):
        state = live_state(shop, {**subscription(items=[PLAN, MODULE]), **ending})

        assert state["cancel_at_period_end"] is True
        assert rights(state) == {"inventory": ("si_inventory", moment(MONTH_END))}

    def test_one_that_left_stripe_lasts_until_its_own_date_and_is_billed_no_more(self, shop, inventory):
        until = moment(MONTH_END - 5 * DAY)
        bought(shop, stripe_item_id="si_gone", valid_until=until)

        state = live_state(shop, subscription(items=[PLAN]))

        assert rights(state) == {"inventory": ("", until)}

    def test_one_that_left_stripe_without_a_date_lasts_as_long_as_the_period(self, shop, inventory):
        bought(shop, stripe_item_id="si_gone")

        state = live_state(shop, subscription(items=[PLAN]))

        assert rights(state) == {"inventory": ("", moment(MONTH_END))}

    def test_one_that_left_stripe_without_any_date_ends_now(self, shop, inventory):
        bought(shop, stripe_item_id="si_gone")
        now = timezone.now()

        state = live_state(shop, subscription(items=[item("si_plan", "price_starter_month", period=(None, None))]), now)

        assert rights(state) == {"inventory": ("", now)}

    def test_one_already_over_by_then_is_gone(self, shop, inventory):
        until = timezone.now() + timedelta(days=1)
        bought(shop, valid_until=until)

        assert rights(live_state(shop, subscription(items=[PLAN]), until)) == {}
        assert rights(live_state(shop, subscription(items=[PLAN]), until - timedelta(seconds=1))) == {
            "inventory": ("", until)
        }

    def test_one_the_plan_includes_was_never_bought(self, shop, inventory):
        bought(shop, source="plan")

        assert rights(live_state(shop, subscription(items=[PLAN]))) == {}

    def test_those_of_another_business_are_not_its_own(self, shop, inventory, make_user):
        from hubs.tests.conftest import create_business

        other = create_business(make_user("other@example.com"), name="Bar Otro")
        bought(shop)

        assert rights(live_state(other, subscription(items=[PLAN]))) == {}


class TestWhoPaysIt:
    @pytest.mark.parametrize(
        "customer, known", [("cus_9", "cus_9"), ({"id": "cus_9", "object": "customer"}, "cus_9"), (None, "")]
    )
    def test_the_customer_is_read_whole_or_by_its_id(self, shop, customer, known):
        assert live_state(shop, subscription(customer=customer))["stripe_customer_id"] == known

    @pytest.mark.parametrize("method", ["pm_new", {"id": "pm_new", "object": "payment_method"}])
    def test_another_card_after_a_decline_is_said_in_the_same_reading(self, shop, method):
        failure = declined(shop, method="pm_old")

        state = live_state(shop, subscription(status="past_due", default_payment_method=method))

        failure.refresh_from_db()
        assert failure.card_changed_at is not None
        assert state["unpaid_reason"] == "card_changed"

    @pytest.mark.parametrize("method", ["pm_old", {"id": "pm_old", "object": "payment_method"}, None])
    def test_the_card_the_bank_declined_is_not_another_one(self, shop, method):
        failure = declined(shop, method="pm_old")

        state = live_state(shop, subscription(status="past_due", default_payment_method=method))

        failure.refresh_from_db()
        assert failure.card_changed_at is None
        assert state["unpaid_reason"] == "card_declined"


class TestItsStatus:
    def test_one_stripe_gives_none_has_none(self, shop):
        live = subscription()
        del live["status"]

        assert live_state(shop, live)["status"] == ""

    def test_the_grace_is_counted_to_the_moment_it_is_read_for(self, shop):
        declined(shop, days=3)
        live = subscription(status="past_due")

        assert live_state(shop, live)["standing"] == "grace"
        assert live_state(shop, live, timezone.now() + timedelta(days=10))["standing"] == "suspended"

    def test_one_that_ended_takes_its_modules_with_it_at_that_moment(self, shop, inventory):
        bought(shop, stripe_item_id="si_inventory")
        at = timezone.now() - timedelta(hours=1)

        state = live_state(shop, subscription(status="canceled"), at)

        assert (state["plan"], state["stripe_subscription_id"], rights(state)) == ("free", "", {"inventory": ("", at)})
