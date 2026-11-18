"""Promo codes of a discount, from the checkout to the changes of the subscription that carries it.

A business that does not pay yet buys its plan in the Embedded Checkout with the code: the session carries the
coupon of the code's discount (``billing.stripe_coupons``) and asks for the card, never with a trial. A discount for a
number of months goes with monthly billing only, and a plan the discount does not name is refused before Stripe is
asked. The checkout that completes counts the code with the subscription it paid and when its discount ends.

The discount then lives on the subscription: a change to a bigger plan keeps it (Stripe prorates at the discounted
price), a module is bought at its full price, a downgrade waiting for the end of the period keeps it in both phases
of Stripe's schedule (reusing the same discount keeps its end, ``fixtures/discounts/downgrade_schedule``), and
moving to yearly billing waits for a discount for months to end. Cancelling works as always.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from live.errors import OperationError

from billing import queries, services
from billing.models import CheckoutAttempt, PlanChangeSchedule, PromoCode, PromoRedemption
from billing.schemas import CheckoutConfirmIn, CheckoutStartIn, HubIn, PlanChangeIn, SubscriptionListIn
from billing.services import checkouts, plan_changes
from billing.tests.conftest import code_of, ctx_for, pay
from billing.tests.stripe_captured import captured
from billing.tests.stripe_double import checkout_session, connection_error, item, preview, subscription
from hubs.models import Plan

pytestmark = pytest.mark.django_db

NOW_TS = int(timezone.now().timestamp())
IN_FOUR_MONTHS = NOW_TS + 120 * 86_400


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity, sold_plans):
    return stripe_double


def our_discount(end: int | None) -> dict:
    """A discount of ours on the subscription, as Stripe expands it, ending at ``end`` (``None``: forever)."""
    return {**captured("repeating_100/subscription.json")["discounts"][0], "end": end}


def start(user, hub, **selection):
    return checkouts.checkout_start(ctx_for(user), CheckoutStartIn(hub_id=hub.id, **selection)).model_dump()


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()
    return error.value


# --- The checkout --------------------------------------------------------------------------------------


class TestTheCheckout:
    @pytest.mark.usefixtures("signup_trial")  # even the days left of the sign-up trial give way to the discount
    def test_it_carries_the_coupon_and_asks_for_the_card_never_with_a_trial(self, shop, owner, stripe_double):
        promo = code_of(plans=["starter", "standard"])

        start(owner, shop, plan="starter", promo_code=" Testers ")

        params = stripe_double.last("checkout.sessions.create").params
        coupon = stripe_double.last("coupons.create").params
        assert params["discounts"] == [{"coupon": coupon["id"]}]
        assert params["payment_method_collection"] == "always"
        assert "trial_end" not in params["subscription_data"]
        assert params["metadata"]["promo_code"] == "testers"
        assert coupon["applies_to"] == {"products": ["prod_standard", "prod_starter"]}
        assert coupon["id"].startswith(f"erp-discount-{promo.discount.id.hex[:12]}-")
        assert CheckoutAttempt.objects.get().promo_code == "testers"

    def test_a_discount_on_every_plan_covers_the_products_of_every_paid_plan(self, shop, owner, stripe_double):
        code_of(percent_off=None, amount_off_cents=1000, duration="forever", duration_in_months=None)

        start(owner, shop, plan="starter", interval="year", promo_code="testers")

        assert stripe_double.last("coupons.create").params["applies_to"] == {
            "products": ["prod_max", "prod_pro", "prod_standard", "prod_starter"]
        }

    def test_a_code_of_trial_days_still_gives_its_trial_and_no_coupon(self, shop, owner, stripe_double):
        PromoCode.objects.create(code="canary", trial_days=60)

        start(owner, shop, plan="starter", promo_code="canary")

        params = stripe_double.last("checkout.sessions.create").params
        assert "discounts" not in params and "payment_method_collection" not in params
        assert abs(params["subscription_data"]["trial_end"] - (timezone.now() + timedelta(days=60)).timestamp()) < 60
        assert not stripe_double.calls_to("coupons.create")

    def test_a_discount_for_months_refuses_the_yearly_billing_before_stripe_is_asked(self, shop, owner, stripe_double):
        code_of()

        error = refused("billing.discount_monthly_only",
                        lambda: start(owner, shop, plan="starter", interval="year", promo_code="testers"))

        assert error.status == 409
        assert not stripe_double.calls_to("checkout.sessions.create")
        assert not stripe_double.calls_to("coupons.create")

    def test_a_plan_the_discount_does_not_name_is_refused(self, shop, owner, stripe_double):
        code_of(plans=["standard"])

        refused("billing.discount_plan_not_covered", lambda: start(owner, shop, plan="starter", promo_code="testers"))

        assert not stripe_double.calls_to("coupons.create")

    def test_a_plan_without_its_stripe_product_cannot_be_discounted(self, shop, owner, stripe_double):
        code_of()
        Plan.objects.filter(slug="starter").update(stripe_product_id="")

        error = refused("billing.payments_unavailable", lambda: start(owner, shop, plan="starter", promo_code="testers"))

        assert error.status == 503
        assert not stripe_double.calls_to("checkout.sessions.create")

    def test_a_module_does_not_take_the_code(self, shop, owner, inventory, stripe_double):
        code_of()

        start(owner, shop, module="inventory", promo_code="testers")

        params = stripe_double.last("checkout.sessions.create").params
        assert "discounts" not in params
        assert "promo_code" not in params["metadata"]

    def test_stripe_away_while_making_the_coupon_charges_nothing(self, shop, owner, stripe_double):
        code_of()
        stripe_double.answer("coupons.create", connection_error())

        error = refused("billing.stripe_unavailable", lambda: start(owner, shop, plan="starter", promo_code="testers"))

        assert error.status == 503
        assert not stripe_double.calls_to("checkout.sessions.create")

    def test_the_same_selection_reuses_its_open_session(self, shop, owner, stripe_double):
        code_of()
        first = start(owner, shop, plan="starter", promo_code="testers")

        assert start(owner, shop, plan="starter", promo_code="testers")["session_id"] == first["session_id"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == 1


class TestAPlanOnTopOfModules:
    """A business that pays modules alone buys its plan with a plan change: a discount is for a new subscription."""

    def test_the_preview_and_the_change_refuse_a_code_of_a_discount(self, shop, owner, inventory, stripe_double):
        code_of()
        paid = pay(shop, plan="free", modules=["inventory"])
        stripe_double.answer("subscriptions.retrieve", subscription(items=[item("si_inventory", "price_inventory_month")]))

        error = refused("billing.promo_discount_new_subscription_only",
                        lambda: start(owner, paid, plan="starter", promo_code="testers"))
        refused("billing.promo_discount_new_subscription_only", lambda: plan_changes.plan_change(
            ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", proration_date=NOW_TS, promo_code="testers")
        ))

        assert error.status == 409
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

    def test_the_code_is_counted_with_its_subscription_and_when_its_discount_ends(self, shop, stripe_double):
        promo = code_of()
        end = captured("repeating_100/subscription.json")["discounts"][0]["end"]

        assert self.complete(shop, stripe_double, [our_discount(end)]) == "completed"

        used = PromoRedemption.objects.get()
        assert (used.promo, used.hub_id, used.stripe_customer_id) == (promo, shop.id, "cus_new")
        assert (used.discount_ends_at, used.stripe_subscription_id) == (datetime.fromtimestamp(end, tz=UTC), "sub_new")
        assert stripe_double.last("subscriptions.retrieve").params == {"expand": ["discounts"]}
        promo.refresh_from_db()
        assert promo.redemption_count == 1

    def test_a_discount_forever_has_no_end(self, shop, stripe_double):
        code_of(duration="forever", duration_in_months=None)

        self.complete(shop, stripe_double, [our_discount(None)])

        assert PromoRedemption.objects.get().discount_ends_at is None


# --- While the discount lives on the subscription ------------------------------------------------------


class TestWhileItLasts:
    def on_discount(self, shop, stripe_double, end=IN_FOUR_MONTHS, **paying):
        paid = pay(shop, plan="starter", **paying)
        stripe_double.answer("subscriptions.retrieve", subscription(discounts=[our_discount(end)]))
        return paid

    def test_a_bigger_plan_keeps_it_without_sending_it_again(self, shop, owner, stripe_double):
        paid = self.on_discount(shop, stripe_double)
        stripe_double.answer("invoices.create_preview", preview(amount_due=0, tax=0))
        stripe_double.answer("subscriptions.update", subscription(discounts=[our_discount(IN_FOUR_MONTHS)]))

        assert start(owner, paid, plan="standard")["flow"] == "confirm"
        plan_changes.plan_change(ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="standard", proration_date=NOW_TS))

        assert "discounts" not in stripe_double.last("subscriptions.update").params

    def test_a_plan_outside_the_discount_is_allowed_and_stripe_stops_discounting_it(self, shop, owner, stripe_double):
        paid = self.on_discount(shop, stripe_double)
        PromoRedemption.objects.create(promo=code_of(plans=["starter"]), hub=paid, stripe_subscription_id="sub_1",
                                       discount_ends_at=timezone.now() + timedelta(days=120))
        stripe_double.answer("invoices.create_preview", preview(amount_due=2600, tax=546))

        answer = start(owner, paid, plan="standard")

        assert answer["preview"]["amount_due_cents"] == 2600
        assert "discounts" not in stripe_double.last("invoices.create_preview").params["subscription_details"]

    def test_a_module_is_bought_at_its_full_price(self, shop, owner, inventory, stripe_double):
        paid = self.on_discount(shop, stripe_double)
        stripe_double.answer("invoices.create_preview", preview(amount_due=1210, tax=210))
        stripe_double.answer("subscription_items.create", {"id": "si_inventory", "object": "subscription_item"})

        assert start(owner, paid, module="inventory")["preview"]["amount_due_cents"] == 1210
        plan_changes.checkout_confirm(ctx_for(owner), CheckoutConfirmIn(hub_id=paid.id, module="inventory",
                                                                  proration_date=NOW_TS))

        assert stripe_double.calls_to("subscription_items.create")

    def test_a_downgrade_keeps_it_in_both_phases_of_the_schedule(self, shop, owner, stripe_double):
        paid = pay(shop, plan="standard")
        live = subscription(items=[item("si_plan", "price_standard_month")], discounts=[our_discount(IN_FOUR_MONTHS)])
        stripe_double.answer("subscriptions.retrieve", live)
        stripe_double.answer("subscription_schedules.create", captured("downgrade_schedule/schedule_from_subscription.json"))
        stripe_double.answer("subscription_schedules.update", captured("downgrade_schedule/schedule_updated.json"))

        plan_changes.plan_change(ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", proration_date=NOW_TS))

        phases = stripe_double.last("subscription_schedules.update").params["phases"]
        held = [{"discount": our_discount(IN_FOUR_MONTHS)["id"]}]
        assert [phase["discounts"] for phase in phases] == [held, held]
        assert PlanChangeSchedule.objects.get(hub=paid).plan_slug == "starter"

    def test_yearly_billing_waits_for_a_discount_for_months_to_end(self, shop, owner, stripe_double):
        paid = self.on_discount(shop, stripe_double)

        error = refused("billing.discount_blocks_annual", lambda: plan_changes.plan_change(
            ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", interval="year", proration_date=NOW_TS)
        ))
        refused("billing.discount_blocks_annual", lambda: start(owner, paid, plan="starter", interval="year"))

        assert error.status == 409
        assert timezone.localdate(datetime.fromtimestamp(IN_FOUR_MONTHS, tz=UTC)).strftime("%Y") in error.message
        assert not stripe_double.calls_to("subscriptions.update")

    def test_yearly_billing_keeps_a_discount_forever(self, shop, owner, stripe_double):
        paid = self.on_discount(shop, stripe_double, end=None)
        stripe_double.answer("invoices.create_preview", preview(amount_due=29_990, tax=0))

        assert start(owner, paid, plan="starter", interval="year")["flow"] == "confirm"

    def test_the_plan_can_still_be_cancelled(self, shop, owner, stripe_double):
        paid = self.on_discount(shop, stripe_double)
        stripe_double.answer("subscriptions.update", subscription(cancel_at_period_end=True,
                                                                  discounts=[our_discount(IN_FOUR_MONTHS)]))

        plan_changes.plan_cancel(ctx_for(owner), HubIn(hub_id=paid.id))

        assert stripe_double.last("subscriptions.update").params["cancel_at_period_end"] is True


# --- The subscriptions list --------------------------------------------------------------------------------


class TestTheSubscriptionsList:
    def row(self, owner, shop):
        [row] = queries.subscription_list(ctx_for(owner), SubscriptionListIn(hub_id=shop.id)).model_dump()["rows"]
        return row

    def redeemed(self, shop, promo, ends_at, subscription_id="sub_1", products=("prod_starter", "prod_standard")):
        PromoRedemption.objects.create(promo=promo, hub=shop, stripe_customer_id="cus_1",
                                       stripe_subscription_id=subscription_id, discount_ends_at=ends_at,
                                       stripe_products=list(products))

    def test_a_discount_for_months_says_until_when_and_the_next_invoice_takes_it_off(self, shop, owner):
        paid = pay(shop)
        ends = timezone.now() + timedelta(days=120)
        self.redeemed(paid, code_of(), ends)

        row = self.row(owner, paid)

        assert (row["discount"]["code"], row["discount"]["ends_at"]) == ("testers", ends)
        assert (row["discount"]["terms"]["percent_off"], row["discount"]["terms"]["duration"]) == (100, "repeating")
        assert row["next_invoice"]["total_cents"] == 0

    def test_a_partial_discount_forever_takes_its_part_off_the_plan_before_vat(self, shop, owner):
        paid = pay(shop)
        self.redeemed(paid, code_of(percent_off=None, amount_off_cents=1000, duration="forever",
                                    duration_in_months=None), None)

        row = self.row(owner, paid)

        assert row["discount"]["ends_at"] is None
        assert row["next_invoice"]["total_cents"] == 2419  # (29.99 - 10.00) + 21 % VAT, as Stripe charged it

    def test_the_renewal_after_its_end_is_charged_whole(self, shop, owner):
        paid = pay(shop)  # renews in 30 days
        self.redeemed(paid, code_of(), timezone.now() + timedelta(days=10))

        row = self.row(owner, paid)

        assert row["discount"] is not None
        assert row["next_invoice"]["total_cents"] == 3629

    def test_a_discount_that_ended_or_was_once_is_not_shown(self, shop, owner):
        paid = pay(shop)
        self.redeemed(paid, code_of(), timezone.now() - timedelta(days=1))
        self.redeemed(paid, code_of("first", duration="once", duration_in_months=None), None)

        assert self.row(owner, paid)["discount"] is None

    def test_the_discount_of_an_earlier_subscription_does_not_count(self, shop, owner):
        paid = pay(shop, sub_id="sub_2")
        self.redeemed(paid, code_of(), timezone.now() + timedelta(days=120), subscription_id="sub_1")

        row = self.row(owner, paid)

        assert row["discount"] is None
        assert row["next_invoice"]["total_cents"] == 3629

    def test_a_plan_outside_the_discount_is_charged_whole(self, shop, owner):
        paid = pay(shop)
        ends = timezone.now() + timedelta(days=120)
        self.redeemed(paid, code_of(plans=["standard"]), ends, products=["prod_standard"])

        row = self.row(owner, paid)

        assert row["discount"] is None
        assert row["next_invoice"]["total_cents"] == 3629

    def test_a_plan_made_after_the_coupon_is_not_discounted_even_by_a_discount_on_every_plan(self, shop, owner):
        """Stripe discounts the products the coupon was made with: the panel never promises less than it charges."""
        newer = Plan.objects.get(slug="standard")
        newer.pk, newer.slug, newer.stripe_product_id, newer.stripe_price_id = None, "growth", "prod_growth", "price_gr"
        newer.save()
        paid = pay(shop, plan="growth")
        self.redeemed(paid, code_of(), timezone.now() + timedelta(days=120))

        row = self.row(owner, paid)

        assert row["discount"] is None
        assert row["next_invoice"]["total_cents"] == 6654  # its price (Standard's, 54.99) + 21 % VAT, whole
