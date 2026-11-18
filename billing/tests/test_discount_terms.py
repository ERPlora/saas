"""What a discount takes off and where it applies (``billing.discount_terms``), with no database: the same answers the
panel, the checkout and the next invoice rely on.

A discount is a percentage or a fixed amount (never more than what it applies to), once, for N months or forever,
on the plans it names (none named = every plan). A discount that lasts a number of months runs on the clock, so
it is only sold with monthly billing; once and forever go with either.
"""

from datetime import UTC, datetime

import pytest

from billing.discount_terms import coupon_name, covers, intervals, off_cents, whole_months
from billing.models import Discount


def discount(**terms) -> Discount:
    return Discount(name="test", **{"duration": Discount.Duration.ONCE, **terms})


class TestWhatItTakesOff:
    @pytest.mark.parametrize(
        ("percent", "net", "off"),
        [(100, 2999, 2999), (20, 2999, 600), (10, 2999, 300), (15, 5499, 825), (1, 49, 0), (50, 1, 1)],
    )
    def test_a_percentage_rounds_to_the_nearest_cent_half_up(self, percent, net, off):
        assert off_cents(discount(percent_off=percent), net) == off

    @pytest.mark.parametrize(("amount", "net", "off"), [(1000, 2999, 1000), (5000, 2999, 2999), (2999, 2999, 2999)])
    def test_an_amount_never_takes_off_more_than_there_is(self, amount, net, off):
        assert off_cents(discount(amount_off_cents=amount), net) == off

    def test_nothing_is_taken_off_nothing(self):
        assert off_cents(discount(percent_off=20), 0) == 0


class TestWhereItApplies:
    def test_no_plan_named_is_every_plan(self):
        assert covers(set(), "plan-a")

    def test_plans_named_are_the_only_ones(self):
        assert covers({"plan-a"}, "plan-a")
        assert not covers({"plan-a"}, "plan-b")

    @pytest.mark.parametrize(
        ("duration", "months", "allowed"),
        [("once", None, ("month", "year")), ("forever", None, ("month", "year")), ("repeating", 6, ("month",))],
    )
    def test_months_go_with_monthly_billing_only(self, duration, months, allowed):
        assert intervals(discount(percent_off=10, duration=duration, duration_in_months=months)) == allowed


class TestItsNameInStripe:
    @pytest.mark.parametrize(
        ("terms", "name"),
        [
            ({"percent_off": 100, "duration": "repeating", "duration_in_months": 6}, "Free for 6 months"),
            ({"percent_off": 100, "duration": "repeating", "duration_in_months": 1}, "Free for 1 month"),
            ({"percent_off": 20, "duration": "once"}, "20% off the first payment"),
            ({"percent_off": 15, "duration": "forever"}, "15% off forever"),
            ({"amount_off_cents": 1000, "duration": "forever"}, "10.00 EUR off forever"),
            ({"amount_off_cents": 250, "duration": "repeating", "duration_in_months": 36}, "2.50 EUR off for 36 months"),
        ],
    )
    def test_it_says_what_it_takes_off_and_for_how_long(self, terms, name):
        assert coupon_name(discount(**terms)) == name

    def test_it_fits_stripes_forty_characters(self):
        longest = discount(amount_off_cents=99_999_999, duration="repeating", duration_in_months=36)

        assert len(coupon_name(longest)) <= 40


class TestTheWholeMonthsLeft:
    """What a discount for months still has when a business changes hands: whole months, rounded down."""

    @pytest.mark.parametrize(
        ("start", "end", "months"),
        [
            ("2027-03-10T12:00", "2027-07-01T09:00", 3),
            ("2027-03-10T12:00", "2027-06-10T12:00", 3),
            ("2027-03-10T12:00", "2027-06-10T11:59", 2),
            ("2027-11-20T00:00", "2028-02-21T00:00", 3),
            ("2027-03-10T12:00", "2027-04-09T12:00", 0),
            ("2027-03-10T12:00", "2027-03-01T12:00", 0),
        ],
    )
    def test_they_round_down(self, start, end, months):
        assert whole_months(moment(start), moment(end)) == months


def moment(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)
