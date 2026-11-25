"""What the staff read about a Stripe price pasted on a plan or a module: one problem per price, in a fixed order, or
the reason nothing was checked (BILLING-F28, APPS-F04). What each wrong price is refused for, through the admin, is in
``test_services`` and ``apps/tests/test_admin.py``."""

from decimal import Decimal

import pytest

from billing import stripe_service
from billing.services import price_checks
from billing.tests.stripe_double import connection_error, invalid_request
from billing.tests.test_services import stripe_price

pytestmark = pytest.mark.django_db

MONTHLY = {"interval": "month", "interval_count": 1}
YEARLY = {"interval": "year", "interval_count": 1}
NOT_CHECKED = "Stripe is not configured here: the prices were not checked."
NO_ANSWER = "Stripe did not answer: the prices were not checked. Try again."
ARCHIVED = "This price is archived in Stripe."
NOT_EUROS = "This price is not in euros."
NOT_MONTHLY = "This price is not charged every month."
NOT_YEARLY = "This price is not charged every year."
NOT_NET = "This price includes the VAT or does not say: it must be net (tax behaviour «exclusive»)."
OTHER_PRODUCT = "This price is of another Stripe product."


def other_amount(stripe: str, expected: str) -> str:
    return f"Stripe charges {stripe} and the plan says {expected}."


#: A price wrong in each way and what is said of it, in the order the problems are looked for.
WRONG_FROM_FIRST_TO_LAST = (
    ({"active": False}, ARCHIVED),
    ({"currency": "usd"}, NOT_EUROS),
    ({"recurring": YEARLY}, NOT_MONTHLY),
    ({"unit_amount": 2900}, other_amount("29.00", "29.99")),
    ({"tax_behavior": "inclusive"}, NOT_NET),
    ({"product": "prod_other"}, OTHER_PRODUCT),
)


def yearly(price_id="price_year", **fields):
    return stripe_price(price_id, **{"unit_amount": 29990, "recurring": YEARLY, **fields})


def check(monthly="", annual="", *, product="prod_starter", **amounts):
    return price_checks.plan_price_problems(
        prices={"stripe_price_id": monthly, "stripe_price_id_annual": annual},
        amounts=amounts or {"price_monthly": Decimal("29.99"), "price_annual": Decimal("299.90")},
        product=product,
    )


def of_the_month(stripe_double, **fields):
    stripe_double.answer("prices.retrieve", stripe_price(**fields))
    return check("price_month").get("stripe_price_id")


def of_the_year(stripe_double, **fields):
    stripe_double.answer("prices.retrieve", yearly(**fields))
    return check(annual="price_year").get("stripe_price_id_annual")


class TestWhatTheStaffRead:
    @pytest.mark.parametrize(
        ("fields", "problem"), [*WRONG_FROM_FIRST_TO_LAST, ({"tax_behavior": "unspecified"}, NOT_NET)]
    )
    def test_of_a_monthly_price(self, stripe_double, fields, problem):
        assert of_the_month(stripe_double, **fields) == problem

    def test_of_an_annual_price_charged_every_month(self, stripe_double):
        assert of_the_year(stripe_double, recurring=MONTHLY) == NOT_YEARLY

    def test_of_an_annual_price_with_another_amount(self, stripe_double):
        assert of_the_year(stripe_double, unit_amount=2999) == other_amount("29.99", "299.90")

    def test_a_price_charged_every_three_months_is_not_a_monthly_one(self, stripe_double):
        assert of_the_month(stripe_double, recurring={"interval": "month", "interval_count": 3}) == NOT_MONTHLY

    def test_a_price_stripe_does_not_have_names_the_pasted_id(self, stripe_double):
        stripe_double.answer("prices.retrieve", invalid_request("No such price: 'price_test_x'"))

        assert check("price_test_x") == {"stripe_price_id": "Stripe has no price price_test_x with these keys."}

    @pytest.mark.parametrize("first", range(len(WRONG_FROM_FIRST_TO_LAST)))
    def test_only_the_first_problem_of_a_price_is_said(self, stripe_double, first):
        wrong = {}
        for fields, _problem in WRONG_FROM_FIRST_TO_LAST[first:]:
            wrong.update(fields)

        assert of_the_month(stripe_double, **wrong) == WRONG_FROM_FIRST_TO_LAST[first][1]


class TestWhatStripeLeavesOut:
    def without(self, *names):
        return {name: value for name, value in stripe_price().items() if name not in names}

    @pytest.mark.parametrize(
        ("name", "problem"),
        [
            ("active", ARCHIVED),
            ("currency", NOT_EUROS),
            ("recurring", NOT_MONTHLY),
            ("unit_amount", other_amount("0.00", "29.99")),
            ("tax_behavior", NOT_NET),
            ("product", OTHER_PRODUCT),
        ],
    )
    def test_a_price_that_does_not_say_it_is_refused_for_it(self, stripe_double, name, problem):
        stripe_double.answer("prices.retrieve", self.without(name))

        assert check("price_month") == {"stripe_price_id": problem}

    @pytest.mark.parametrize(("name", "problem"), [("currency", NOT_EUROS), ("unit_amount", other_amount("0.00", "29.99"))])
    def test_nor_one_whose_answer_is_null(self, stripe_double, name, problem):
        assert of_the_month(stripe_double, **{name: None}) == problem

    def test_every_month_is_the_interval_without_a_count(self, stripe_double):
        assert of_the_month(stripe_double, recurring={"interval": "month"}) is None

    def test_the_currency_counts_in_capitals_too(self, stripe_double):
        assert of_the_month(stripe_double, currency="EUR") is None

    def test_a_plan_that_names_no_product_takes_the_price_of_any(self, stripe_double):
        stripe_double.answer("prices.retrieve", stripe_price(product="prod_other"))

        assert check("price_month", product="") == {}

    def test_an_amount_nobody_gave_is_zero(self, stripe_double):
        stripe_double.answer("prices.retrieve", stripe_price())

        assert check("price_month", price_annual=Decimal("299.90")) == {
            "stripe_price_id": other_amount("29.99", "0.00")
        }


class TestBothPrices:
    def test_each_is_read_and_answered_under_its_own_field(self, stripe_double):
        stripe_double.answer("prices.retrieve", stripe_price(active=False), yearly(currency="usd"))

        assert check("price_month", "price_year") == {
            "stripe_price_id": ARCHIVED,
            "stripe_price_id_annual": NOT_EUROS,
        }
        assert [call.args for call in stripe_double.calls_to("prices.retrieve")] == [("price_month",), ("price_year",)]

    def test_only_the_wrong_one_has_a_problem(self, stripe_double):
        stripe_double.answer("prices.retrieve", stripe_price(), yearly(product="prod_other"))

        assert check("price_month", "price_year") == {"stripe_price_id_annual": OTHER_PRODUCT}

    def test_one_stripe_does_not_have_does_not_stop_the_other(self, stripe_double):
        stripe_double.answer(
            "prices.retrieve", invalid_request("No such price: 'price_month'"), yearly(tax_behavior="inclusive")
        )

        assert check("price_month", "price_year") == {
            "stripe_price_id": "Stripe has no price price_month with these keys.",
            "stripe_price_id_annual": NOT_NET,
        }

    def test_stripe_away_at_the_second_answers_nothing_about_the_first(self, stripe_double):
        stripe_double.answer("prices.retrieve", stripe_price(active=False), connection_error())

        with pytest.raises(price_checks.PriceCheckFailed, match=f"^{NO_ANSWER}$"):
            check("price_month", "price_year")


class TestNothingChecked:
    def test_stripe_away_says_to_try_again_and_keeps_what_failed(self, stripe_double):
        stripe_double.answer("prices.retrieve", connection_error())

        with pytest.raises(price_checks.PriceCheckFailed, match=f"^{NO_ANSWER}$") as raised:
            check("price_month")
        assert isinstance(raised.value.__cause__, stripe_service.StripeUnavailable)

    def test_without_stripe_it_says_so(self, stripe_double, settings):
        settings.STRIPE_SECRET_KEY = ""

        with pytest.raises(price_checks.PriceCheckSkipped, match=f"^{NOT_CHECKED}$"):
            check("price_month")

    @pytest.mark.parametrize("prices", [{}, {"stripe_price_id": "", "stripe_price_id_annual": None}])
    def test_with_nothing_pasted_it_does_not_matter_that_stripe_is_not_configured(self, stripe_double, settings, prices):
        settings.STRIPE_SECRET_KEY = ""

        assert price_checks.plan_price_problems(prices=prices, amounts={}, product="prod_starter") == {}
        assert stripe_double.calls == []
