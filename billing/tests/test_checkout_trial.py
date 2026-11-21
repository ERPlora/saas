"""The trial a purchase carries: the days left of the sign-up trial, a promo code that replaces it, also when the
plan comes on top of modules bought alone, and a promo code used once per business and per payer.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import OperationError

from billing.models import PromoCode
from billing.tests.checkout_calls import NOW_TS, payer, session_params, start
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import item, preview, subscription
from hubs.models import Subscription

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


# --- The trial ---------------------------------------------------------------------------------------


class TestTheTrial:
    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no seeded plan carries one)
    def test_the_days_left_of_the_sign_up_trial_are_kept(
        self, shop, owner, stripe_double
    ):
        trial_end = Subscription.objects.get(hub=shop).trial_end

        start(owner, shop, plan="starter")

        assert session_params(stripe_double)["subscription_data"]["trial_end"] == int(
            trial_end.timestamp()
        )

    def test_a_trial_about_to_end_is_not_carried(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(
            trial_end=timezone.now() + timedelta(hours=30)
        )

        start(owner, shop, plan="starter")

        assert "trial_end" not in session_params(stripe_double)["subscription_data"]

    def test_a_business_past_its_trial_pays_at_once(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(
            trial_end=timezone.now() - timedelta(days=1)
        )

        start(owner, shop, plan="starter")

        assert "trial_end" not in session_params(stripe_double)["subscription_data"]

    def test_a_promo_code_replaces_the_trial(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(
            trial_end=timezone.now() - timedelta(days=1)
        )
        PromoCode.objects.create(code="canary_2026", trial_days=60)

        start(owner, shop, plan="starter", promo_code=" CANARY_2026 ")

        params = session_params(stripe_double)
        expected = timezone.now() + timedelta(days=60)
        assert abs(params["subscription_data"]["trial_end"] - expected.timestamp()) < 60
        assert params["metadata"]["promo_code"] == "canary_2026"

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no seeded plan carries one)
    def test_the_longer_of_the_two_wins(self, shop, owner, stripe_double):
        PromoCode.objects.create(code="short", trial_days=3)
        trial_end = Subscription.objects.get(hub=shop).trial_end

        start(owner, shop, plan="starter", promo_code="short")

        assert session_params(stripe_double)["subscription_data"]["trial_end"] == int(
            trial_end.timestamp()
        )

    def test_an_invalid_promo_code_is_said_and_the_sale_goes_on_without_it(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(trial_end=None)
        PromoCode.objects.create(code="gone", trial_days=30, is_active=False)

        with pytest.raises(OperationError, match="remove it to pay without it"):
            start(owner, shop, plan="starter", promo_code="gone")

        assert start(owner, shop, plan="starter")["flow"] == "checkout"
        params = session_params(stripe_double)
        assert "promo_code" not in params["metadata"] and "trial_end" not in params["subscription_data"]


class TestAPlanOnTopOfModules:
    """A Free business that bought modules alone pays a subscription without a plan item: buying the plan
    keeps the days left of its sign-up trial and honours a promo code, as the checkout does."""

    def modules_only(self, shop, stripe_double, inventory):
        paid = pay(shop, plan="free", modules=["inventory"])
        stripe_double.answer(
            "subscriptions.retrieve", subscription(items=[item("si_inventory", "price_inventory_month")])
        )
        return paid

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no seeded plan carries one)
    def test_the_preview_and_the_change_carry_the_trial_left(self, shop, owner, inventory, stripe_double):
        from billing.services import plan_changes
        from billing.schemas.subscription_changes import PlanChangeIn

        trial_end = Subscription.objects.get(hub=shop).trial_end
        paid = self.modules_only(shop, stripe_double, inventory)
        stripe_double.answer("invoices.create_preview", preview(amount_due=0, tax=0))
        stripe_double.answer("subscriptions.update", subscription(items=[item("si_inventory", "price_inventory_month"),
                                                                         item("si_plan", "price_starter_month")]))

        start(owner, paid, plan="starter")
        plan_changes.plan_change(
            ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", proration_date=NOW_TS)
        )

        details = stripe_double.last("invoices.create_preview").params["subscription_details"]
        sent = stripe_double.last("subscriptions.update").params
        assert details["trial_end"] == sent["trial_end"] == int(trial_end.timestamp())
        assert details["proration_behavior"] == sent["proration_behavior"] == "none"

    def test_a_promo_code_is_honoured(self, shop, owner, inventory, stripe_double):
        from billing.services import plan_changes
        from billing.schemas.subscription_changes import PlanChangeIn

        Subscription.objects.filter(hub=shop).update(trial_end=timezone.now() - timedelta(days=1))
        PromoCode.objects.create(code="canary_2026", trial_days=60)
        paid = self.modules_only(shop, stripe_double, inventory)
        stripe_double.answer("subscriptions.update", subscription())

        plan_changes.plan_change(
            ctx_for(owner),
            PlanChangeIn(hub_id=paid.id, plan="starter", proration_date=NOW_TS, promo_code="Canary_2026"),
        )

        sent = stripe_double.last("subscriptions.update").params
        assert abs(sent["trial_end"] - (timezone.now() + timedelta(days=60)).timestamp()) < 60
        assert PromoCode.objects.get().redemption_count == 1


class TestAPromoCodeOncePerBusinessAndPayer:
    def redeemed(self, hub, code="canary_2026", customer="cus_1"):
        from billing.models import PromoRedemption

        promo = PromoCode.objects.get_or_create(code=code, defaults={"trial_days": 60})[0]
        PromoRedemption.objects.create(promo=promo, hub=hub, stripe_customer_id=customer, stripe_session_id="cs_old")
        return promo

    def test_the_same_business_does_not_use_it_twice(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(trial_end=None)
        self.redeemed(shop)

        with pytest.raises(OperationError, match="remove it to pay without it"):
            start(owner, shop, plan="starter", promo_code="canary_2026")

    def test_the_same_payer_does_not_use_it_for_another_business(self, shop, owner, stripe_double, plans):
        from hubs.tests.conftest import create_business

        Subscription.objects.filter(hub=shop).update(trial_end=None)
        payer(shop, stripe_customer_id="cus_1")
        other = pay(create_business(make_free_owner(), name="Otro"), sub_id="sub_x")
        self.redeemed(other, customer="cus_1")

        with pytest.raises(OperationError, match="remove it to pay without it"):
            start(owner, shop, plan="starter", promo_code="canary_2026")


def make_free_owner():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email="other-owner@example.com", password=None)
