"""The admin of discounts and promo codes: a discount is made with its codes on one page, and what a customer already
used stays as it was (its terms, and its Stripe coupon, cannot change; a used code keeps its code and what it gives).
"""

import pytest

from billing.models import Discount, PromoCode, PromoRedemption

pytestmark = pytest.mark.django_db

INLINE = {"codes-TOTAL_FORMS": "1", "codes-INITIAL_FORMS": "0", "codes-MIN_NUM_FORMS": "0", "codes-MAX_NUM_FORMS": "1000"}
TERMS = {"name": "Testers", "percent_off": "100", "currency": "eur", "duration": "repeating",
         "duration_in_months": "6", "applies_to": "plans", "is_active": "on"}


def used(discount, shop) -> PromoCode:
    promo = PromoCode.objects.create(code="testers", discount=discount)
    PromoRedemption.objects.create(promo=promo, hub=shop)
    return promo


def test_a_discount_is_made_with_its_codes(staff_client):
    response = staff_client.post(
        "/admin/billing/discount/add/",
        {**TERMS, **INLINE, "codes-0-code": " Testers ", "codes-0-is_active": "on", "codes-0-redemption_count": "0"},
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    made = Discount.objects.get()
    assert (made.percent_off, made.duration, made.duration_in_months) == (100, "repeating", 6)
    assert list(made.codes.values_list("code", "trial_days")) == [("testers", None)]


def test_terms_that_are_not_one_discount_are_refused_in_the_form(staff_client):
    response = staff_client.post(
        "/admin/billing/discount/add/", {**TERMS, **INLINE, "amount_off_cents": "1000", "codes-TOTAL_FORMS": "0"}
    )

    assert response.status_code == 200
    assert "a percentage or an amount" in response.content.decode()
    assert not Discount.objects.exists()


def test_once_used_its_terms_are_read_only_and_it_is_not_deleted(staff_client, shop):
    discount = Discount.objects.create(name="Testers", percent_off=100, duration="repeating", duration_in_months=6)
    used(discount, shop)

    page = staff_client.get(f"/admin/billing/discount/{discount.pk}/change/").content.decode()

    assert 'name="percent_off"' not in page and 'name="duration_in_months"' not in page
    assert 'name="name"' in page and 'name="is_active"' in page
    assert staff_client.get(f"/admin/billing/discount/{discount.pk}/delete/").status_code == 403


def test_before_any_use_its_terms_can_be_changed(staff_client):
    discount = Discount.objects.create(name="Testers", percent_off=100, duration="repeating", duration_in_months=6)

    page = staff_client.get(f"/admin/billing/discount/{discount.pk}/change/").content.decode()

    assert 'name="percent_off"' in page


def test_a_used_code_keeps_its_code_and_what_it_gives(staff_client, shop):
    discount = Discount.objects.create(name="Testers", percent_off=100, duration="repeating", duration_in_months=6)
    promo = used(discount, shop)

    page = staff_client.get(f"/admin/billing/promocode/{promo.pk}/change/").content.decode()

    assert 'name="code"' not in page and 'name="discount"' not in page and 'name="trial_days"' not in page
    assert 'name="max_redemptions"' in page and 'name="expires_at_0"' in page


def test_the_list_of_codes_says_what_each_gives(staff_client):
    discount = Discount.objects.create(name="Testers", percent_off=100, duration="repeating", duration_in_months=6)
    PromoCode.objects.create(code="testers", discount=discount)

    page = staff_client.get("/admin/billing/promocode/").content.decode()

    assert "column-discount" in page and "Testers" in page


class TestAUsedCodeIsTurnedOffNotDeleted:
    """Deleting a used code would take its uses with it: the same business and payer could use it again, its discount's
    terms would open up again and the subscriptions that carry it would stop showing it."""

    def test_the_code_page_offers_no_deletion(self, staff_client, shop):
        discount = Discount.objects.create(name="Testers", percent_off=100, duration="repeating", duration_in_months=6)
        promo = used(discount, shop)

        assert staff_client.get(f"/admin/billing/promocode/{promo.pk}/delete/").status_code == 403
        assert PromoCode.objects.filter(pk=promo.pk).exists()

    def test_an_unused_code_can_still_be_deleted(self, staff_client):
        promo = PromoCode.objects.create(code="spare", trial_days=30)

        response = staff_client.post(f"/admin/billing/promocode/{promo.pk}/delete/", {"post": "yes"})

        assert response.status_code == 302
        assert not PromoCode.objects.filter(pk=promo.pk).exists()

    def test_the_discount_page_does_not_delete_a_used_code_among_its_codes(self, staff_client, shop):
        discount = Discount.objects.create(name="Testers", percent_off=100, duration="repeating", duration_in_months=6)
        promo = used(discount, shop)
        spare = PromoCode.objects.create(code="spare", discount=discount)
        rows = {
            "codes-TOTAL_FORMS": "2", "codes-INITIAL_FORMS": "2", "codes-MIN_NUM_FORMS": "0",
            "codes-MAX_NUM_FORMS": "1000",
        }
        for index, code in enumerate((promo, spare)):
            rows |= {f"codes-{index}-id": str(code.pk), f"codes-{index}-discount": str(discount.pk),
                     f"codes-{index}-is_active": "on", f"codes-{index}-DELETE": "on"}
        rows["codes-1-code"] = "spare"

        response = staff_client.post(
            f"/admin/billing/discount/{discount.pk}/change/", {"name": "Testers", "is_active": "on", **rows}
        )

        assert response.status_code == 200, response.status_code
        assert "would require deleting the following protected related objects" in response.content.decode()
        assert set(PromoCode.objects.values_list("code", flat=True)) == {"testers", "spare"}

    def test_its_uses_cannot_go_with_it_from_the_code(self, shop):
        from django.db.models import ProtectedError

        promo = used(Discount.objects.create(name="Testers", percent_off=100, duration="once"), shop)

        with pytest.raises(ProtectedError):
            promo.delete()
        assert PromoRedemption.objects.filter(promo=promo).exists()


def test_the_list_of_uses_says_which_are_only_held_by_an_open_checkout(staff_client, shop):
    from datetime import timedelta

    from django.utils import timezone

    promo = PromoCode.objects.create(code="canary", trial_days=30)
    PromoRedemption.objects.create(promo=promo, hub=shop, held_until=timezone.now() + timedelta(hours=25))

    page = staff_client.get("/admin/billing/promoredemption/").content.decode()

    assert "column-held_until" in page
