"""The reads of promo codes (``billing.queries.promo_codes``): which code is redeemable, and ``billing.promo.check``.

A code grants exactly one of the two: trial days, or a discount (``test_discounts.py``). It is
case-insensitive and trimmed; an unknown, inactive, expired or exhausted
code resolves to nothing and never blocks a sale. The panel asks whether a code is valid before paying
(``GET /api/billing/promo-check``), with a per-person budget so codes cannot be guessed by brute force.

Dropped with reason: ``TestHubCreationFormPromoCode`` (3, the Django form of the old sign-up; its
normalisation is the model's, pinned here).
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from live.errors import OperationError

from billing import queries
from billing.models import PromoCode
from billing.schemas.promo_codes import PromoCheckIn
from billing.tests.conftest import ctx_for, promo

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


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


class TestCheck:
    def test_a_valid_code_says_its_trial(self, buyer):
        promo(code="canary_2026", trial_days=60)

        answer = queries.promo_check(
            ctx_for(buyer), PromoCheckIn(code=" Canary_2026 ")
        ).model_dump()

        assert answer == {"code": "canary_2026", "valid": True, "trial_days": 60, "discount": None}

    def test_a_code_of_a_discount_says_its_terms_and_where_they_apply(self, buyer, plans):
        from billing.models import Discount
        from hubs.models import Plan

        given = Discount.objects.create(name="Testers", percent_off=100, duration="repeating", duration_in_months=6)
        given.plans.set(Plan.objects.filter(slug__in=["standard", "starter"]))
        PromoCode.objects.create(code="testers", discount=given)

        answer = queries.promo_check(ctx_for(buyer), PromoCheckIn(code="TESTERS")).model_dump()

        assert answer == {
            "code": "testers",
            "valid": True,
            "trial_days": 0,
            "discount": {
                "percent_off": 100,
                "amount_off_cents": None,
                "currency": "eur",
                "duration": "repeating",
                "duration_in_months": 6,
                "applies_to": {"kind": "plans", "plans": ["standard", "starter"], "intervals": ["month"]},
            },
        }

    def test_a_discount_on_every_plan_names_none(self, buyer):
        from billing.models import Discount

        given = Discount.objects.create(name="Ten", amount_off_cents=1000, duration="forever")
        PromoCode.objects.create(code="ten", discount=given)

        answer = queries.promo_check(ctx_for(buyer), PromoCheckIn(code="ten")).model_dump()

        assert answer["discount"]["applies_to"] == {"kind": "plans", "plans": [], "intervals": ["month", "year"]}
        assert (answer["discount"]["percent_off"], answer["discount"]["amount_off_cents"]) == (None, 1000)

    def test_an_inactive_discount_makes_its_codes_invalid(self, buyer):
        from billing.models import Discount

        given = Discount.objects.create(name="Off", percent_off=10, duration="once", is_active=False)
        PromoCode.objects.create(code="off", discount=given)

        assert queries.promo_check(ctx_for(buyer), PromoCheckIn(code="off")).valid is False

    def test_an_invalid_code_is_an_answer_not_an_error(self, buyer):
        promo(is_active=False)

        answer = queries.promo_check(
            ctx_for(buyer), PromoCheckIn(code="canary_2026")
        ).model_dump()

        assert answer == {"code": "canary_2026", "valid": False, "trial_days": 0, "discount": None}

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
            "discount": None,
        }
