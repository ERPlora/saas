"""Stripe test clocks for the billing QA (``billing.stripe_test_clocks``).

Ported from ERPlora/saas ``hubs/main/services/stripe_test_clocks.py`` and its
``hubs/main/tests/test_stripe_test_clocks.py`` (origin/develop, 10 tests; saas#1961): a customer attached
to a clock subscribes to a NORMAL plan with its NORMAL trial and the clock jumps past it, so Stripe issues a
real invoice (instead of the retired internal 1 € plan). Two refusals stay, because both failures are
silent: a LIVE key (clocks do not exist there) is refused before any call, and advancing returns only once
the clock is ``ready`` (reading while it is ``advancing`` gives the state from BEFORE the jump).

``TestTheCustomerCarriesTheClock`` (2) is ``billing.services.ensure_customer(hub, test_clock=…)``, tested
with the checkout (``test_checkout.py``).
"""

import pytest

from billing import stripe_test_clocks
from billing.stripe_test_clocks import (
    ClockNotReady,
    LiveModeRefused,
    advance_test_clock,
    create_test_clock,
)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(stripe_test_clocks.time, "sleep", lambda seconds: None)


@pytest.mark.parametrize("key", ["sk_live_51abc", "rk_live_51abc"])
def test_a_live_key_is_refused_before_any_call(stripe_double, settings, key):
    settings.STRIPE_SECRET_KEY = key

    with pytest.raises(LiveModeRefused):
        create_test_clock(1_700_000_000, name="billing-qa")
    with pytest.raises(LiveModeRefused):
        advance_test_clock("clock_123", 1_700_100_000)

    assert stripe_double.calls == []


def test_a_restricted_test_key_is_allowed(stripe_double, settings):
    settings.STRIPE_SECRET_KEY = "rk_test_51abc"
    stripe_double.answer(
        "test_helpers.test_clocks.create", {"id": "clock_123", "status": "ready"}
    )

    assert create_test_clock(1_700_000_000) == "clock_123"


def test_a_test_key_creates_the_clock_with_its_time_and_name(stripe_double):
    stripe_double.answer(
        "test_helpers.test_clocks.create", {"id": "clock_123", "status": "ready"}
    )

    assert create_test_clock(1_700_000_000, name="billing-qa") == "clock_123"
    assert stripe_double.last("test_helpers.test_clocks.create").params == {
        "frozen_time": 1_700_000_000,
        "name": "billing-qa",
    }


def test_advancing_polls_until_the_clock_is_ready(stripe_double):
    stripe_double.answer(
        "test_helpers.test_clocks.advance", {"id": "clock_123", "status": "advancing"}
    )
    stripe_double.answer(
        "test_helpers.test_clocks.retrieve",
        {"id": "clock_123", "status": "advancing"},
        {"id": "clock_123", "status": "advancing"},
        {"id": "clock_123", "status": "ready"},
    )

    advance_test_clock("clock_123", 1_700_100_000)

    assert stripe_double.last("test_helpers.test_clocks.advance").params == {
        "frozen_time": 1_700_100_000
    }
    assert len(stripe_double.calls_to("test_helpers.test_clocks.retrieve")) == 3


def test_a_clock_that_never_becomes_ready_raises(stripe_double):
    stripe_double.answer(
        "test_helpers.test_clocks.advance", {"id": "clock_123", "status": "advancing"}
    )
    stripe_double.answer(
        "test_helpers.test_clocks.retrieve", {"id": "clock_123", "status": "advancing"}
    )

    with pytest.raises(ClockNotReady):
        advance_test_clock("clock_123", 1_700_100_000, max_polls=3)

    assert len(stripe_double.calls_to("test_helpers.test_clocks.retrieve")) == 3


def test_an_internal_failure_of_the_clock_raises_at_once(stripe_double):
    stripe_double.answer(
        "test_helpers.test_clocks.advance", {"id": "clock_123", "status": "advancing"}
    )
    stripe_double.answer(
        "test_helpers.test_clocks.retrieve",
        {"id": "clock_123", "status": "internal_failure"},
    )

    with pytest.raises(ClockNotReady):
        advance_test_clock("clock_123", 1_700_100_000, max_polls=10)

    assert len(stripe_double.calls_to("test_helpers.test_clocks.retrieve")) == 1


# --- BILLING-F29: the staff's door in PRE (the Django admin; test keys only) ----------------------------


@pytest.mark.django_db
class TestTheStaffDoor:
    """A QA business whose payer is born on a clock, then the clock a month ahead: Stripe renews and charges
    in test mode and the chain runs as in production (BILLING-F20), with no internal 1 € plan."""

    def test_a_new_payer_is_born_on_a_clock(self, shop, stripe_double):
        from billing import services

        stripe_double.answer("test_helpers.test_clocks.create", {"id": "clock_qa", "status": "ready"})
        stripe_double.answer("customers.search", {"data": []})

        assert services.attach_test_clock(shop.id) == "clock_qa"

        assert stripe_double.last("test_helpers.test_clocks.create").params["name"] == f"QA {shop.slug}"
        assert stripe_double.last("customers.create").params["test_clock"] == "clock_qa"

    def test_a_payer_already_in_stripe_takes_no_clock(self, shop, stripe_double):
        from billing import services

        shop.billing_profile.stripe_customer_id = "cus_old"
        shop.billing_profile.save()

        with pytest.raises(services.TestClockRefused):
            services.attach_test_clock(shop.id)
        assert stripe_double.calls_to("test_helpers.test_clocks.create") == []

    @pytest.mark.parametrize("key", ["rk_live_51abc", ""])
    def test_without_a_test_key_there_is_no_clock(self, shop, stripe_double, settings, key):
        from billing import services

        settings.STRIPE_SECRET_KEY = key

        with pytest.raises(services.TestClockRefused):
            services.attach_test_clock(shop.id)
        with pytest.raises(services.TestClockRefused):
            services.advance_test_clock_of(shop.id)
        assert stripe_double.calls == []

    def test_advancing_moves_its_clock_a_month_from_its_own_time_without_waiting(self, shop, stripe_double):
        from billing import services

        shop.billing_profile.stripe_customer_id = "cus_qa"
        shop.billing_profile.save()
        stripe_double.answer("customers.retrieve", {"id": "cus_qa", "test_clock": "clock_qa"})
        stripe_double.answer(
            "test_helpers.test_clocks.retrieve", {"id": "clock_qa", "status": "ready", "frozen_time": 1_700_000_000}
        )
        stripe_double.answer("test_helpers.test_clocks.advance", {"id": "clock_qa", "status": "advancing"})

        reached = services.advance_test_clock_of(shop.id)

        assert stripe_double.last("test_helpers.test_clocks.advance").params == {
            "frozen_time": 1_700_000_000 + 31 * 86_400
        }
        assert int(reached.timestamp()) == 1_700_000_000 + 31 * 86_400
        assert len(stripe_double.calls_to("test_helpers.test_clocks.retrieve")) == 1

    def test_a_clock_still_advancing_is_not_pushed_again(self, shop, stripe_double):
        from billing import services

        shop.billing_profile.stripe_customer_id = "cus_qa"
        shop.billing_profile.save()
        stripe_double.answer("customers.retrieve", {"id": "cus_qa", "test_clock": "clock_qa"})
        stripe_double.answer(
            "test_helpers.test_clocks.retrieve", {"id": "clock_qa", "status": "advancing", "frozen_time": 1}
        )

        with pytest.raises(services.TestClockRefused):
            services.advance_test_clock_of(shop.id)
        assert stripe_double.calls_to("test_helpers.test_clocks.advance") == []

    def test_a_payer_without_a_clock_has_nothing_to_advance(self, shop, stripe_double):
        from billing import services

        shop.billing_profile.stripe_customer_id = "cus_real"
        shop.billing_profile.save()
        stripe_double.answer("customers.retrieve", {"id": "cus_real", "test_clock": None})

        with pytest.raises(services.TestClockRefused):
            services.advance_test_clock_of(shop.id)
