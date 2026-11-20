"""Promo codes: redeeming one at checkout, and the trial days one may grant.

The counter goes up once per completed checkout and never past its cap, even under races (the cap is in
the UPDATE's WHERE). Which code is redeemable and ``billing.promo.check`` are tested with the other reads of
promo codes, in ``test_queries_promo_codes.py``.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from billing.services import promo_codes
from billing.models import PromoCode
from billing.tests.conftest import promo

pytestmark = pytest.mark.django_db


class TestRedeem:
    def test_redeeming_counts_one(self):
        made = promo()

        assert promo_codes.redeem_promo("canary_2026") is True
        made.refresh_from_db()
        assert made.redemption_count == 1

    def test_redeeming_is_case_insensitive(self):
        promo()

        assert promo_codes.redeem_promo("CANARY_2026") is True

    def test_an_unknown_code_counts_nothing(self):
        assert promo_codes.redeem_promo("nope") is False
        assert promo_codes.redeem_promo("") is False

    def test_the_cap_is_never_passed(self):
        made = promo(max_redemptions=1)

        assert promo_codes.redeem_promo("canary_2026") is True
        assert promo_codes.redeem_promo("canary_2026") is False
        made.refresh_from_db()
        assert made.redemption_count == 1

    def test_an_unlimited_code_keeps_counting(self):
        made = promo()

        for _ in range(3):
            promo_codes.redeem_promo("canary_2026")

        made.refresh_from_db()
        assert made.redemption_count == 3


class TestTrialDays:
    def test_a_year_is_allowed(self):
        PromoCode(code="year", trial_days=365).full_clean()

    @pytest.mark.parametrize("days", [0, 366])
    def test_no_days_or_more_than_a_year_is_refused(self, days):
        with pytest.raises(ValidationError):
            PromoCode(code="bad", trial_days=days).full_clean()

    @pytest.mark.parametrize("days", [0, 366])
    def test_the_database_refuses_them_too(self, days):
        with pytest.raises(IntegrityError), transaction.atomic():
            PromoCode.objects.create(code="bad", trial_days=days)
