"""The Stripe coupons of the promo codes of free months (``billing.stripe_coupons``).

One coupon per number of months, with a fixed id (``free-months-<N>``): 100 % off, repeating for N months. It is
created the first time a code of N months is used and reused after that, in test and live mode alike, so nothing
is stored on our side. One that another checkout created meanwhile is the same coupon.
"""

import pytest

from billing.stripe_coupons import ensure_free_months_coupon
from billing.stripe_service import StripeRefused, StripeUnavailable
from billing.tests.stripe_double import connection_error, invalid_request


def test_the_coupon_of_n_months_is_created_on_its_first_use(stripe_double):
    assert ensure_free_months_coupon(6) == "free-months-6"

    assert stripe_double.last("coupons.retrieve").args == ("free-months-6",)
    assert stripe_double.last("coupons.create").params == {
        "id": "free-months-6",
        "percent_off": 100,
        "duration": "repeating",
        "duration_in_months": 6,
        "name": "6 months free",
    }


def test_a_coupon_that_exists_is_used_as_it_is(stripe_double):
    ensure_free_months_coupon(3)

    assert ensure_free_months_coupon(3) == "free-months-3"
    assert len(stripe_double.calls_to("coupons.create")) == 1
    assert len(stripe_double.calls_to("coupons.retrieve")) == 2


def test_each_number_of_months_has_its_own_coupon(stripe_double):
    assert [ensure_free_months_coupon(months) for months in (1, 12)] == ["free-months-1", "free-months-12"]

    assert [call.params["duration_in_months"] for call in stripe_double.calls_to("coupons.create")] == [1, 12]


def test_a_coupon_another_checkout_created_meanwhile_is_the_same(stripe_double):
    stripe_double.answer("coupons.create", invalid_request("resource_already_exists", "Coupon already exists."))

    assert ensure_free_months_coupon(6) == "free-months-6"


def test_any_other_refusal_is_not_taken_for_a_coupon(stripe_double):
    stripe_double.answer("coupons.create", invalid_request("parameter_invalid_integer", "Invalid integer"))

    with pytest.raises(StripeRefused):
        ensure_free_months_coupon(6)


def test_stripe_away_is_said_as_such(stripe_double):
    stripe_double.answer("coupons.retrieve", connection_error())

    with pytest.raises(StripeUnavailable):
        ensure_free_months_coupon(6)

    assert not stripe_double.calls_to("coupons.create")
