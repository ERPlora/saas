"""A discount: a percentage or a fixed amount in euros, once, for N months (1 to 36) or forever, on every plan or on
some. The database and the form refuse one that is not exactly that, and a promo code gives either a discount or
trial days, never both nor neither.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from billing.models import Discount, PromoCode

pytestmark = pytest.mark.django_db


def terms(**changes) -> dict:
    return {"name": "Testers", "percent_off": 100, "duration": "repeating", "duration_in_months": 6, **changes}


class TestADiscount:
    @pytest.mark.parametrize(
        "changes",
        [
            {},
            {"percent_off": 1, "duration": "once", "duration_in_months": None},
            {"percent_off": None, "amount_off_cents": 1000, "duration": "forever", "duration_in_months": None},
            {"duration_in_months": 36},
        ],
    )
    def test_a_valid_one_is_kept(self, changes):
        Discount(**terms(**changes)).full_clean()
        Discount.objects.create(**terms(**changes))

    @pytest.mark.parametrize(
        ("changes", "says"),
        [
            ({"amount_off_cents": 1000}, "a percentage or an amount"),
            ({"percent_off": None}, "a percentage or an amount"),
            ({"duration_in_months": None}, "how many months"),
            ({"duration": "once"}, "how many months"),
        ],
    )
    def test_the_form_says_what_is_wrong(self, changes, says):
        with pytest.raises(ValidationError) as refused:
            Discount(**terms(**changes)).full_clean()

        assert says in str(refused.value)

    @pytest.mark.parametrize(
        "changes",
        [
            {"percent_off": 0},
            {"percent_off": 101},
            {"duration_in_months": 37},
            {"duration_in_months": 0},
            {"currency": "usd"},
        ],
    )
    def test_a_term_out_of_range_is_refused(self, changes):
        with pytest.raises(ValidationError):
            Discount(**terms(**changes)).full_clean()

    @pytest.mark.parametrize(
        "changes",
        [
            {"amount_off_cents": 1000},
            {"percent_off": None},
            {"percent_off": 101},
            {"duration_in_months": None},
            {"duration": "forever"},
            {"duration_in_months": 37},
            {"currency": "usd"},
            {"percent_off": None, "amount_off_cents": 0},
        ],
    )
    def test_the_database_refuses_it_too(self, changes):
        with pytest.raises(IntegrityError), transaction.atomic():
            Discount.objects.create(**terms(**changes))


class TestAPromoCode:
    def test_it_gives_a_discount(self):
        made = PromoCode.objects.create(code="testers", discount=Discount.objects.create(**terms()))

        assert made.trial_days is None

    def test_it_gives_trial_days(self):
        PromoCode(code="canary", trial_days=30).full_clean()

    @pytest.mark.parametrize("both", [True, False])
    def test_never_both_nor_neither(self, both):
        given = {"discount": Discount.objects.create(**terms()), "trial_days": 30} if both else {}

        with pytest.raises(ValidationError) as refused:
            PromoCode(code="bad", **given).full_clean()
        assert "either trial days or a discount" in str(refused.value)
        with pytest.raises(IntegrityError), transaction.atomic():
            PromoCode.objects.create(code="bad", **given)

    def test_a_discount_with_codes_is_not_deleted(self):
        given = Discount.objects.create(**terms())
        PromoCode.objects.create(code="testers", discount=given)

        with pytest.raises(IntegrityError), transaction.atomic():
            given.delete()
