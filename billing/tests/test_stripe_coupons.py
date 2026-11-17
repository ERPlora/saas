"""The Stripe coupon of a discount (``billing.stripe_coupons``): its mirror, never stored on our side.

Its id is derived from the discount and from what it applies to (``erp-discount-<discount>-<terms and products>``):
the same discount on the same products is always the same coupon, in test and live mode alike, and a discount
whose plans change gets a new one. Every checkout asks Stripe to create it: the first one does, and Stripe answers
the others that it exists already, which is no error (no ERROR in the log). Its terms are the discount's, limited
to the products of its plans, so it never takes anything off a module.

On a live subscription, ``live_discounts`` keeps only ours (by the id's prefix) and ``discount_end`` says when the
one that lasts months ends; the shapes are Stripe's own (``fixtures/discounts/``).
"""

import logging
import uuid
from datetime import UTC, datetime

import pytest

from billing.models import Discount
from billing.stripe_coupons import coupon_id, discount_end, ensure_coupon, live_discounts
from billing.stripe_service import StripeRefused, StripeUnavailable
from billing.tests.stripe_captured import captured
from billing.tests.stripe_double import connection_error, invalid_request

PRODUCTS = ["prod_starter", "prod_standard"]


def discount(**terms) -> Discount:
    given = {"percent_off": 100, "duration": "repeating", "duration_in_months": 6, **terms}
    return Discount(id=uuid.UUID("0193a1b2-c3d4-7000-8000-000000000001"), name="Testers", **given)


def errors(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]


class TestItsId:
    def test_it_is_the_discount_and_a_print_of_its_terms_and_products(self):
        made = coupon_id(discount(), PRODUCTS)

        assert made.startswith("erp-discount-0193a1b2c3d4-")
        assert len(made.rsplit("-", 1)[1]) == 8
        assert made == coupon_id(discount(), list(reversed(PRODUCTS)))

    @pytest.mark.parametrize(
        "changes",
        [{"percent_off": 50}, {"duration_in_months": 3}, {"duration": "forever", "duration_in_months": None}],
    )
    def test_other_terms_are_another_coupon(self, changes):
        assert coupon_id(discount(**changes), PRODUCTS) != coupon_id(discount(), PRODUCTS)

    def test_other_products_are_another_coupon(self):
        assert coupon_id(discount(), ["prod_starter"]) != coupon_id(discount(), PRODUCTS)


class TestItsCreation:
    def test_a_percentage_for_months_on_the_plans_products(self, stripe_double, caplog):
        made = ensure_coupon(discount(), PRODUCTS)

        assert made == coupon_id(discount(), PRODUCTS)
        assert stripe_double.last("coupons.create").params == {
            "id": made,
            "percent_off": 100,
            "duration": "repeating",
            "duration_in_months": 6,
            "applies_to": {"products": PRODUCTS},
            "name": "Free for 6 months",
        }
        assert errors(caplog) == []

    def test_an_amount_forever_carries_its_currency(self, stripe_double):
        ensure_coupon(discount(percent_off=None, amount_off_cents=1000, duration="forever", duration_in_months=None),
                      PRODUCTS)

        sent = stripe_double.last("coupons.create").params
        assert (sent["amount_off"], sent["currency"], sent["duration"]) == (1000, "eur", "forever")
        assert "percent_off" not in sent and "duration_in_months" not in sent

    def test_once_it_exists_stripe_says_so_and_that_is_no_error(self, stripe_double, caplog):
        first = ensure_coupon(discount(), PRODUCTS)

        assert ensure_coupon(discount(), PRODUCTS) == first
        assert len(stripe_double.calls_to("coupons.create")) == 2
        assert errors(caplog) == []

    def test_any_other_refusal_is_not_taken_for_a_coupon(self, stripe_double, caplog):
        stripe_double.answer("coupons.create", invalid_request("parameter_invalid_integer", "Invalid integer"))

        with pytest.raises(StripeRefused):
            ensure_coupon(discount(), PRODUCTS)
        assert errors(caplog)

    def test_stripe_away_is_said_as_such(self, stripe_double):
        stripe_double.answer("coupons.create", connection_error())

        with pytest.raises(StripeUnavailable):
            ensure_coupon(discount(), PRODUCTS)


class TestOnALiveSubscription:
    def test_a_discount_for_months_ends_when_stripe_says(self):
        live = captured("repeating_100/subscription.json")

        [ours] = live_discounts(live)
        assert discount_end(live) == datetime.fromtimestamp(ours["end"], tz=UTC)

    def test_one_forever_has_no_end(self):
        live = captured("forever_amount/partial/subscription_after.json")

        assert len(live_discounts(live)) == 1
        assert discount_end(live) is None

    def test_one_once_is_gone_after_its_payment(self):
        assert live_discounts(captured("once_percent/subscription_after.json")) == []

    @pytest.mark.parametrize(
        "discounts",
        [[], ["di_not_expanded"], [{"source": {"coupon": "9KnYiLBN", "type": "coupon"}, "end": 1_900_000_000}]],
    )
    def test_nothing_that_is_not_ours_and_expanded_counts(self, discounts):
        assert live_discounts({"discounts": discounts}) == []
        assert discount_end({"discounts": discounts}) is None
        assert discount_end({}) is None
