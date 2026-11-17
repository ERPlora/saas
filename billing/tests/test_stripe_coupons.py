"""The Stripe coupons of the promo codes of free months (``billing.stripe_coupons``).

One coupon per number of months, with a fixed id (``free-months-<N>``): 100 % off, repeating for N months. Every
checkout of a code of N months asks Stripe to create it: the first one does, and Stripe answers the others that it
exists already, which is no error (no ERROR in the log). Nothing is stored on our side, in test and live mode alike.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from billing.stripe_coupons import ensure_free_months_coupon, free_months_end
from billing.stripe_service import StripeRefused, StripeUnavailable
from billing.tests.stripe_double import connection_error, invalid_request


def errors(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]


def test_the_coupon_of_n_months_is_created_on_its_first_use_without_an_error(stripe_double, caplog):
    assert ensure_free_months_coupon(6) == "free-months-6"

    assert stripe_double.last("coupons.create").params == {
        "id": "free-months-6",
        "percent_off": 100,
        "duration": "repeating",
        "duration_in_months": 6,
        "name": "6 months free",
    }
    assert not stripe_double.calls_to("coupons.retrieve")
    assert errors(caplog) == []


def test_once_it_exists_stripe_says_so_and_that_is_no_error(stripe_double, caplog):
    ensure_free_months_coupon(3)

    assert ensure_free_months_coupon(3) == "free-months-3"
    assert ensure_free_months_coupon(3) == "free-months-3"
    assert len(stripe_double.calls_to("coupons.create")) == 3
    assert stripe_double.coupons["free-months-3"]["duration_in_months"] == 3
    assert errors(caplog) == []


def test_each_number_of_months_has_its_own_coupon(stripe_double):
    assert [ensure_free_months_coupon(months) for months in (1, 12)] == ["free-months-1", "free-months-12"]

    assert [call.params["duration_in_months"] for call in stripe_double.calls_to("coupons.create")] == [1, 12]


def test_any_other_refusal_is_not_taken_for_a_coupon(stripe_double, caplog):
    stripe_double.answer("coupons.create", invalid_request("parameter_invalid_integer", "Invalid integer"))

    with pytest.raises(StripeRefused):
        ensure_free_months_coupon(6)

    assert errors(caplog)


def test_stripe_away_is_said_as_such(stripe_double):
    stripe_double.answer("coupons.create", connection_error())

    with pytest.raises(StripeUnavailable):
        ensure_free_months_coupon(6)


# --- When the free months of a subscription end --------------------------------------------------------


def captured_discount() -> dict:
    """The discount a code of six months left on a subscription of the test account, as Stripe expands it."""
    fixture = Path(__file__).parent / "fixtures" / "free_months" / "subscription.json"
    return json.loads(fixture.read_text())["discounts"][0]


def test_the_free_months_end_with_the_discount_of_their_coupon():
    discount = captured_discount()

    assert free_months_end({"discounts": [discount]}) == datetime.fromtimestamp(discount["end"], tz=UTC)


def test_the_latest_of_two_discounts_of_free_months_counts():
    first, later = captured_discount(), {**captured_discount(), "end": captured_discount()["end"] + 86_400}

    assert free_months_end({"discounts": [later, first]}).timestamp() == later["end"]


@pytest.mark.parametrize(
    "discounts",
    [
        [],
        ["di_not_expanded"],
        [{"source": {"coupon": "9KnYiLBN", "type": "coupon"}, "end": 1_900_000_000}],
        [{"source": {"coupon": "free-months-6", "type": "coupon"}, "end": None}],
    ],
)
def test_no_free_months_without_an_expanded_discount_of_ours_with_an_end(discounts):
    assert free_months_end({"discounts": discounts}) is None
    assert free_months_end({}) is None
