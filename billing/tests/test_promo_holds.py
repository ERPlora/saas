"""A promo code's use is held by the checkout that offers it.

The coupon of a code's discount goes into the Checkout Session as it opens, so the use is taken then, not when the
payment arrives: within the code's cap (in the ``UPDATE``'s ``WHERE``), once per business and once per payer, all
at the same point. A checkout that is paid makes its hold a use; one that closes unpaid (Stripe expires it, another
selection replaces it, or the business changes hands) gives it back, and a hold whose session can no longer be paid
is given back by itself, so none is held forever. The hold also keeps what the coupon really covers.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from live.errors import Conflict, OperationError

from billing import services
from billing.services import checkouts, promo_holds
from billing.models import CheckoutAttempt, PromoCode, PromoRedemption
from billing.schemas import CheckoutStartIn
from billing.tests.conftest import code_of, ctx_for
from billing.tests.stripe_double import checkout_session, event, item, subscription

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("issuer_identity", "sold_plans")]


def start(user, hub, **selection):
    return checkouts.checkout_start(ctx_for(user), CheckoutStartIn(hub_id=hub.id, **selection)).model_dump()


def refused(call) -> OperationError:
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == "billing.promo_not_available", error.value.envelope()
    return error.value


@pytest.fixture
def bar(buyer, plans):
    """Another business, of another owner and payer."""
    from hubs.models import Hub
    from hubs.tests.conftest import create_business

    hub = create_business(buyer, name="Bar La Plaza")
    profile = hub.billing_profile
    profile.billing_name, profile.billing_address = "Bar La Plaza SL", "Calle Real 2"
    profile.billing_city, profile.billing_postal_code = "Madrid", "28002"
    profile.save()
    return Hub.objects.select_related("billing_profile").get(pk=hub.pk)


def counted(promo: PromoCode) -> int:
    promo.refresh_from_db()
    return promo.redemption_count


def paid(stripe_double, hub, attempt: CheckoutAttempt) -> str:
    stripe_double.answer(
        "subscriptions.retrieve",
        subscription("sub_new", customer="cus_1", items=[item("si_plan", "price_starter_month")]),
    )
    metadata = {"kind": "hub_plan", "hub_id": str(hub.id), "plan": "starter", "billing_interval": "month",
                "promo_code": attempt.promo_code}
    return services.checkout_completed(
        checkout_session(attempt.stripe_session_id, subscription_id="sub_new", metadata=metadata)
    )


class TestTheHold:
    def test_opening_the_checkout_takes_one_use_and_keeps_what_the_coupon_covers(self, shop, owner, stripe_double):
        promo = code_of(plans=["starter", "standard"])

        start(owner, shop, plan="starter", promo_code="testers")

        held = PromoRedemption.objects.get()
        attempt = CheckoutAttempt.objects.get()
        assert (held.hub_id, held.attempt, held.stripe_subscription_id) == (shop.id, attempt, "")
        assert held.held_until > timezone.now() + timedelta(hours=23)
        assert held.stripe_coupon_id == stripe_double.last("coupons.create").params["id"]
        assert held.stripe_products == ["prod_standard", "prod_starter"]
        assert counted(promo) == 1

    def test_a_code_of_trial_days_is_held_too(self, shop, owner, stripe_double):
        promo = PromoCode.objects.create(code="canary", trial_days=30)

        start(owner, shop, plan="starter", promo_code="canary")

        held = PromoRedemption.objects.get()
        assert (held.held_until is not None, held.stripe_coupon_id, held.stripe_products) == (True, "", [])
        assert counted(promo) == 1

    def test_the_last_use_goes_to_one_checkout(self, shop, owner, bar, buyer, stripe_double):
        promo = code_of(max_redemptions=1)
        start(owner, shop, plan="starter", promo_code="testers")
        sessions = len(stripe_double.calls_to("checkout.sessions.create"))

        error = refused(lambda: start(buyer, bar, plan="starter", promo_code="testers"))

        assert "remove it to pay without it" in error.envelope()["error"]["message"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == sessions
        assert counted(promo) == 1
        assert not CheckoutAttempt.objects.filter(hub=bar).exists()

    def test_one_payer_holds_it_for_one_business(self, shop, owner, bar, buyer, stripe_double):
        from hubs.models import BillingProfile

        promo = code_of()
        start(owner, shop, plan="starter", promo_code="testers")
        # The same Stripe customer pays for the other business.
        customer = PromoRedemption.objects.get().stripe_customer_id
        BillingProfile.objects.filter(pk=bar.billing_profile_id).update(stripe_customer_id=customer)
        bar.billing_profile.refresh_from_db()

        refused(lambda: start(buyer, bar, plan="starter", promo_code="testers"))

        assert counted(promo) == 1

    def test_the_same_business_choosing_again_moves_its_hold(self, shop, owner, stripe_double):
        promo = code_of(max_redemptions=1)
        start(owner, shop, plan="starter", promo_code="testers")

        start(owner, shop, plan="standard", promo_code="testers")

        held = PromoRedemption.objects.get()
        assert held.attempt == CheckoutAttempt.objects.get(status=CheckoutAttempt.Status.OPEN)
        assert held.attempt.plan_slug == "standard"
        assert counted(promo) == 1


    def test_the_same_choice_after_its_session_is_too_old_to_reuse_keeps_the_hold(self, shop, owner, stripe_double):
        promo = code_of(max_redemptions=1)
        start(owner, shop, plan="starter", promo_code="testers")
        CheckoutAttempt.objects.update(created_at=timezone.now() - CheckoutAttempt.REUSE_FOR - timedelta(minutes=5))

        start(owner, shop, plan="starter", promo_code="testers")

        newest = CheckoutAttempt.objects.order_by("-created_at").first()
        assert PromoRedemption.objects.get().attempt == newest
        assert counted(promo) == 1


class TestItsUse:
    def test_the_paid_checkout_makes_the_hold_a_use(self, shop, owner, stripe_double):
        promo = code_of()
        start(owner, shop, plan="starter", promo_code="testers")

        assert paid(stripe_double, shop, CheckoutAttempt.objects.get()) == "completed"

        used = PromoRedemption.objects.get()
        assert (used.held_until, used.stripe_subscription_id) == (None, "sub_new")
        assert used.stripe_products == ["prod_max", "prod_pro", "prod_standard", "prod_starter"]
        assert counted(promo) == 1

    def test_a_payment_after_its_hold_was_given_back_is_still_a_use(self, shop, owner, stripe_double):
        promo = code_of(max_redemptions=1)
        start(owner, shop, plan="starter", promo_code="testers")
        attempt = CheckoutAttempt.objects.get()
        PromoRedemption.objects.update(held_until=timezone.now() - timedelta(minutes=1))
        call_command("sweep_unpaid")
        assert counted(promo) == 0

        paid(stripe_double, shop, attempt)

        used = PromoRedemption.objects.get()
        assert (used.held_until, used.stripe_subscription_id) == (None, "sub_new")
        assert counted(promo) == 1


class TestItIsGivenBack:
    def test_when_stripe_expires_the_session(self, shop, owner, stripe_double):
        promo = code_of(max_redemptions=1)
        start(owner, shop, plan="starter", promo_code="testers")
        attempt = CheckoutAttempt.objects.get()

        services.process_stripe_event(
            event("checkout.session.expired", checkout_session(
                attempt.stripe_session_id, subscription_id=None, status="expired", payment_status="unpaid",
                metadata={"kind": "hub_plan", "hub_id": str(shop.id)},
            ))
        )

        assert not PromoRedemption.objects.exists()
        assert counted(promo) == 0

    def test_when_the_business_opens_another_checkout_without_the_code(self, shop, owner, stripe_double):
        promo = code_of()
        start(owner, shop, plan="starter", promo_code="testers")

        start(owner, shop, plan="standard")

        assert not PromoRedemption.objects.exists()
        assert counted(promo) == 0

    def test_when_the_business_changes_hands(self, shop, owner, stripe_double):
        promo = code_of()
        start(owner, shop, plan="starter", promo_code="testers")

        services.expire_open_checkouts(shop.id)

        assert not PromoRedemption.objects.exists()
        assert counted(promo) == 0

    def test_a_hold_whose_session_can_no_longer_be_paid_never_stays(self, shop, owner, stripe_double):
        promo = code_of()
        start(owner, shop, plan="starter", promo_code="testers")
        PromoRedemption.objects.update(held_until=timezone.now() - timedelta(minutes=1))

        call_command("sweep_unpaid")

        assert not PromoRedemption.objects.exists()
        assert counted(promo) == 0

    def test_the_next_checkout_takes_a_use_left_held_by_an_unpayable_session(self, shop, owner, bar, buyer,
                                                                            stripe_double):
        promo = code_of(max_redemptions=1)
        start(owner, shop, plan="starter", promo_code="testers")
        PromoRedemption.objects.update(held_until=timezone.now() - timedelta(minutes=1))

        start(buyer, bar, plan="starter", promo_code="testers")

        assert PromoRedemption.objects.get().hub_id == bar.id
        assert counted(promo) == 1


class TestACodeNoLongerUsable:
    def test_a_code_used_up_since_it_was_checked_is_said_and_never_dropped_in_silence(self, shop, owner,
                                                                                       stripe_double):
        code_of(max_redemptions=1, redemption_count=1)

        refused(lambda: start(owner, shop, plan="starter", promo_code="testers"))

        assert not stripe_double.calls_to("checkout.sessions.create")


class TestBehindTheLock:
    """What two checkouts opening at once meet: the cap in the ``UPDATE`` and the business and payer checked after
    it, while the code's row is held, whatever the read before them said."""

    def attempt(self, hub, selection):
        return CheckoutAttempt.objects.create(hub=hub, kind="plan", plan_slug="starter", selection=selection)

    def test_the_cap_lets_one_hold_through(self, shop, bar):
        promo = code_of(max_redemptions=1)
        promo_holds.hold(promo, self.attempt(shop, "a"), customer="cus_shop", coupon=None)

        with pytest.raises(Conflict):
            promo_holds.hold(promo, self.attempt(bar, "b"), customer="cus_bar", coupon=None)

        assert counted(promo) == 1
        assert PromoRedemption.objects.get().hub_id == shop.id

    def test_one_payer_holds_it_once_for_two_businesses(self, shop, bar):
        promo = code_of()
        promo_holds.hold(promo, self.attempt(shop, "a"), customer="cus_same", coupon=None)

        with pytest.raises(Conflict):
            promo_holds.hold(promo, self.attempt(bar, "b"), customer="cus_same", coupon=None)

        assert counted(promo) == 1
