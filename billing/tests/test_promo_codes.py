"""Promo codes: extra trial days at checkout (ADR-0107), and ``billing.promo.check``.

Ported from ERPlora/saas ``hubs/subscriptions/tests/test_promo_codes.py`` (origin/develop, 23 tests): a code
grants free TIME, never a lower price (a Stripe coupon burns during the trial, and a discount turns the
renewal into a price hike). It is case-insensitive and trimmed; an unknown, inactive, expired or exhausted
code resolves to nothing and never blocks a sale; the counter goes up once per completed checkout and
never past its cap, even under races (the cap is in the UPDATE's WHERE).

Dropped with reason: ``TestHubCreationFormPromoCode`` (3, the Django form of the old sign-up; its
normalisation is the model's, pinned here). New: the panel asks whether a code is valid before paying
(``GET /api/billing/promo-check``), with a per-person budget so codes cannot be guessed by brute force.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone
from live.errors import OperationError

from billing import queries, services
from billing.models import PromoCode
from billing.schemas import PromoCheckIn
from billing.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def promo(code="canary_2026", trial_days=60, **fields):
    return PromoCode.objects.create(code=code, trial_days=trial_days, **fields)


class TestResolve:
    def test_an_exact_code_resolves(self):
        made = promo()

        assert queries.redeemable_promo("canary_2026") == made

    @pytest.mark.parametrize("typed", ["CANARY_2026", "Canary_2026", "  canary_2026  "])
    def test_case_and_surrounding_spaces_do_not_matter(self, typed):
        made = promo()

        assert queries.redeemable_promo(typed) == made

    def test_the_code_is_stored_lowercase(self):
        assert promo(code="  SUMMER_ES ").code == "summer_es"

    @pytest.mark.parametrize("typed", ["", None, "   ", "unknown"])
    def test_nothing_or_an_unknown_code_resolves_to_nothing(self, typed):
        promo()

        assert queries.redeemable_promo(typed) is None

    def test_an_inactive_code_resolves_to_nothing(self):
        promo(is_active=False)

        assert queries.redeemable_promo("canary_2026") is None

    def test_an_expired_code_resolves_to_nothing(self):
        promo(expires_at=timezone.now() - timedelta(seconds=1))

        assert queries.redeemable_promo("canary_2026") is None

    def test_a_code_before_its_expiry_resolves(self):
        made = promo(expires_at=timezone.now() + timedelta(days=1))

        assert queries.redeemable_promo("canary_2026") == made

    def test_a_code_without_expiry_never_expires(self):
        made = promo(expires_at=None)

        assert queries.redeemable_promo("canary_2026") == made

    def test_an_exhausted_code_resolves_to_nothing(self):
        promo(max_redemptions=2, redemption_count=2)

        assert queries.redeemable_promo("canary_2026") is None

    def test_a_code_with_redemptions_left_resolves(self):
        made = promo(max_redemptions=2, redemption_count=1)

        assert queries.redeemable_promo("canary_2026") == made

    def test_a_code_without_a_cap_is_unlimited(self):
        made = promo(max_redemptions=None, redemption_count=10_000)

        assert queries.redeemable_promo("canary_2026") == made


class TestRedeem:
    def test_redeeming_counts_one(self):
        made = promo()

        assert services.redeem_promo("canary_2026") is True
        made.refresh_from_db()
        assert made.redemption_count == 1

    def test_redeeming_is_case_insensitive(self):
        promo()

        assert services.redeem_promo("CANARY_2026") is True

    def test_an_unknown_code_counts_nothing(self):
        assert services.redeem_promo("nope") is False
        assert services.redeem_promo("") is False

    def test_the_cap_is_never_passed(self):
        made = promo(max_redemptions=1)

        assert services.redeem_promo("canary_2026") is True
        assert services.redeem_promo("canary_2026") is False
        made.refresh_from_db()
        assert made.redemption_count == 1

    def test_an_unlimited_code_keeps_counting(self):
        made = promo()

        for _ in range(3):
            services.redeem_promo("canary_2026")

        made.refresh_from_db()
        assert made.redemption_count == 3


class TestTrialDaysCeiling:
    def test_a_year_is_allowed(self):
        PromoCode(code="year", trial_days=365).full_clean()

    @pytest.mark.parametrize("days", [0, 366])
    def test_no_days_or_more_than_a_year_is_refused(self, days):
        with pytest.raises(ValidationError):
            PromoCode(code="bad", trial_days=days).full_clean()


class TestCheck:
    def test_a_valid_code_says_its_trial(self, buyer):
        promo(code="canary_2026", trial_days=60)

        answer = queries.promo_check(
            ctx_for(buyer), PromoCheckIn(code=" Canary_2026 ")
        ).model_dump()

        assert answer == {"code": "canary_2026", "valid": True, "trial_days": 60}

    def test_an_invalid_code_is_an_answer_not_an_error(self, buyer):
        promo(is_active=False)

        answer = queries.promo_check(
            ctx_for(buyer), PromoCheckIn(code="canary_2026")
        ).model_dump()

        assert answer == {"code": "canary_2026", "valid": False, "trial_days": 0}

    def test_a_visitor_cannot_try_codes(self):
        response = Client().get("/api/billing/promo-check", {"code": "canary_2026"}, HTTP_HOST=HOST)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    def test_guessing_codes_is_throttled(self, buyer, settings):
        settings.PROMO_CHECK_RATE = "3/m"
        for _ in range(3):
            queries.promo_check(ctx_for(buyer), PromoCheckIn(code="guess"))

        with pytest.raises(OperationError) as refused:
            queries.promo_check(ctx_for(buyer), PromoCheckIn(code="guess"))

        assert (refused.value.status, refused.value.code) == (
            429,
            "billing.promo_check_throttled",
        )

    def test_the_route_answers_the_panel(self, buyer):
        promo(code="canary_2026", trial_days=30)
        client = Client()
        client.force_login(buyer)

        response = client.get(
            "/api/billing/promo-check", {"code": "canary_2026"}, HTTP_HOST=HOST
        )

        assert response.status_code == 200
        assert response.json() == {
            "code": "canary_2026",
            "valid": True,
            "trial_days": 30,
        }
