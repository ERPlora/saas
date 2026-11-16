"""Promo codes of free months: N months of a monthly plan at no charge, then its regular price.

A business that does not pay yet buys its plan in the Embedded Checkout with the code: the session carries the
100 % coupon of N months (``billing.stripe_coupons``) and asks for the card, never with a trial, because the coupon
runs on the clock and Stripe invoices every month (0 € while it lasts). Only a new monthly subscription takes such a
code; while its months last, the plan, the billing and the modules stay as they are (the coupon would make any change
free too), and cancelling still works. The checkout that completes counts the code and keeps when its months end,
read from the discount of the live subscription.

The discount's shape is Stripe's own, captured from the test account (``fixtures/free_months/``).
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.utils import timezone
from live.errors import OperationError

from billing import services
from billing.models import CheckoutAttempt, PromoCode, PromoRedemption
from billing.schemas import CheckoutConfirmIn, CheckoutStartIn, HubIn, PlanChangeIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import checkout_session, connection_error, item, preview, subscription

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures" / "free_months"
NOW_TS = int(timezone.now().timestamp())
IN_FOUR_MONTHS = NOW_TS + 120 * 86_400


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


@pytest.fixture
def testers(db):
    return PromoCode.objects.create(code="testers", free_months=6, note="Testers")


def captured(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def free_months_discount(end: int) -> dict:
    """The discount a code of six months leaves on the subscription, as Stripe expands it, ending at ``end``."""
    return {**captured("subscription.json")["discounts"][0], "end": end}


def start(user, hub, **selection):
    return services.checkout_start(ctx_for(user), CheckoutStartIn(hub_id=hub.id, **selection)).model_dump()


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()
    return error.value


# --- The checkout --------------------------------------------------------------------------------------


class TestTheCheckout:
    @pytest.mark.usefixtures("signup_trial")  # even the days left of the sign-up trial give way to the coupon
    def test_it_carries_the_coupon_and_asks_for_the_card_never_with_a_trial(self, shop, owner, testers, stripe_double):
        start(owner, shop, plan="starter", promo_code=" Testers ")

        params = stripe_double.last("checkout.sessions.create").params
        assert params["discounts"] == [{"coupon": "free-months-6"}]
        assert params["payment_method_collection"] == "always"
        assert "trial_end" not in params["subscription_data"]
        assert params["metadata"]["promo_code"] == "testers"
        assert stripe_double.last("coupons.create").params["duration_in_months"] == 6
        assert CheckoutAttempt.objects.get().promo_code == "testers"

    def test_a_code_of_trial_days_still_gives_its_trial_and_no_coupon(self, shop, owner, stripe_double):
        PromoCode.objects.create(code="canary", trial_days=60)

        start(owner, shop, plan="starter", promo_code="canary")

        params = stripe_double.last("checkout.sessions.create").params
        assert "discounts" not in params and "payment_method_collection" not in params
        assert abs(params["subscription_data"]["trial_end"] - (timezone.now() + timedelta(days=60)).timestamp()) < 60
        assert not stripe_double.calls_to("coupons.retrieve")

    def test_the_yearly_billing_is_refused_before_stripe_is_asked(self, shop, owner, testers, stripe_double):
        error = refused("billing.promo_monthly_only", lambda: start(owner, shop, plan="starter", interval="year",
                                                                    promo_code="testers"))

        assert error.status == 409
        assert not stripe_double.calls_to("checkout.sessions.create")
        assert not stripe_double.calls_to("coupons.retrieve")

    def test_a_module_does_not_take_the_code(self, shop, owner, testers, inventory, stripe_double):
        start(owner, shop, module="inventory", promo_code="testers")

        params = stripe_double.last("checkout.sessions.create").params
        assert "discounts" not in params
        assert "promo_code" not in params["metadata"]

    def test_stripe_away_while_finding_the_coupon_charges_nothing(self, shop, owner, testers, stripe_double):
        stripe_double.answer("coupons.retrieve", connection_error())

        error = refused("billing.stripe_unavailable", lambda: start(owner, shop, plan="starter", promo_code="testers"))

        assert error.status == 503
        assert not stripe_double.calls_to("checkout.sessions.create")

    def test_the_same_selection_reuses_its_open_session(self, shop, owner, testers, stripe_double):
        first = start(owner, shop, plan="starter", promo_code="testers")

        assert start(owner, shop, plan="starter", promo_code="testers")["session_id"] == first["session_id"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == 1


class TestAPlanChange:
    """A business that pays modules alone buys its plan with a plan change: free months are for a new subscription."""

    def modules_only(self, shop, stripe_double):
        paid = pay(shop, plan="free", modules=["inventory"])
        stripe_double.answer("subscriptions.retrieve", subscription(items=[item("si_inventory", "price_inventory_month")]))
        return paid

    def test_the_preview_refuses_a_code_of_free_months(self, shop, owner, testers, inventory, stripe_double):
        paid = self.modules_only(shop, stripe_double)

        error = refused("billing.promo_new_subscription_only",
                        lambda: start(owner, paid, plan="starter", promo_code="testers"))

        assert error.status == 409
        assert not stripe_double.calls_to("invoices.create_preview")

    def test_the_change_refuses_it_and_charges_nothing(self, shop, owner, testers, inventory, stripe_double):
        paid = self.modules_only(shop, stripe_double)

        refused("billing.promo_new_subscription_only", lambda: services.plan_change(
            ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", proration_date=NOW_TS, promo_code="testers")
        ))

        assert not stripe_double.calls_to("subscriptions.update")
        assert not PromoRedemption.objects.exists()


# --- The checkout completed ----------------------------------------------------------------------------


class TestTheCompletedCheckout:
    def complete(self, shop, stripe_double, discounts):
        CheckoutAttempt.objects.create(hub=shop, kind="plan", plan_slug="starter", selection="plan:starter",
                                       stripe_session_id="cs_test_1", promo_code="testers")
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription("sub_new", customer="cus_new", items=[item("si_plan", "price_starter_month")],
                         discounts=discounts),
        )
        metadata = {"kind": "hub_plan", "hub_id": str(shop.id), "plan": "starter", "billing_interval": "month",
                    "promo_code": "testers"}
        return services.checkout_completed(checkout_session(subscription_id="sub_new", metadata=metadata))

    def test_the_code_is_counted_with_the_day_its_free_months_end(self, shop, testers, stripe_double):
        end = captured("subscription.json")["discounts"][0]["end"]

        assert self.complete(shop, stripe_double, [free_months_discount(end)]) == "completed"

        used = PromoRedemption.objects.get()
        assert (used.promo, used.hub_id, used.stripe_customer_id) == (testers, shop.id, "cus_new")
        assert used.free_until == datetime.fromtimestamp(end, tz=UTC)
        assert stripe_double.last("subscriptions.retrieve").params == {"expand": ["discounts"]}
        testers.refresh_from_db()
        assert testers.redemption_count == 1

    def test_a_discount_that_is_not_ours_gives_no_free_months(self, shop, testers, stripe_double):
        theirs = {**free_months_discount(IN_FOUR_MONTHS), "source": {"coupon": "9KnYiLBN", "type": "coupon"}}

        self.complete(shop, stripe_double, [theirs])

        assert PromoRedemption.objects.get().free_until is None


# --- While the free months last ------------------------------------------------------------------------


class TestWhileTheFreeMonthsLast:
    def on_free_months(self, shop, stripe_double, end=IN_FOUR_MONTHS):
        paid = pay(shop, plan="starter")
        stripe_double.answer("subscriptions.retrieve", subscription(discounts=[free_months_discount(end)]))
        return paid

    def test_the_plan_does_not_change(self, shop, owner, stripe_double):
        paid = self.on_free_months(shop, stripe_double)

        error = refused("billing.free_months_active", lambda: start(owner, paid, plan="standard"))
        refused("billing.free_months_active", lambda: services.plan_change(
            ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="standard", proration_date=NOW_TS)
        ))

        assert error.status == 409
        assert timezone.localdate(datetime.fromtimestamp(IN_FOUR_MONTHS, tz=UTC)).strftime("%Y") in error.message
        assert not stripe_double.calls_to("subscriptions.update")
        assert not stripe_double.calls_to("invoices.create_preview")

    def test_the_billing_does_not_become_yearly(self, shop, owner, stripe_double):
        paid = self.on_free_months(shop, stripe_double)

        refused("billing.free_months_active", lambda: services.plan_change(
            ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", interval="year", proration_date=NOW_TS)
        ))

        assert not stripe_double.calls_to("subscriptions.update")

    def test_no_module_is_bought(self, shop, owner, inventory, stripe_double):
        paid = self.on_free_months(shop, stripe_double)

        refused("billing.free_months_active", lambda: start(owner, paid, module="inventory"))
        refused("billing.free_months_active", lambda: services.checkout_confirm(
            ctx_for(owner), CheckoutConfirmIn(hub_id=paid.id, module="inventory", proration_date=NOW_TS)
        ))

        assert not stripe_double.calls_to("subscription_items.create")

    def test_the_plan_can_still_be_cancelled(self, shop, owner, stripe_double):
        paid = self.on_free_months(shop, stripe_double)
        stripe_double.answer("subscriptions.update", subscription(cancel_at_period_end=True,
                                                                  discounts=[free_months_discount(IN_FOUR_MONTHS)]))

        services.plan_cancel(ctx_for(owner), HubIn(hub_id=paid.id))

        assert stripe_double.last("subscriptions.update").params["cancel_at_period_end"] is True

    def test_once_they_ended_the_plan_changes_again(self, shop, owner, stripe_double):
        paid = self.on_free_months(shop, stripe_double, end=NOW_TS - 86_400)
        stripe_double.answer("invoices.create_preview", preview(amount_due=2600, tax=546))

        assert start(owner, paid, plan="standard")["flow"] == "confirm"
