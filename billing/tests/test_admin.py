"""The Django admin shows every model of billing (PLAN-SAAS §6: «el Django admin, lo más completo posible»).

The two singletons (``FiscalPolicy``, ``CompanyConfig``) open straight on their one row and can be
neither added twice nor deleted; the VIES log is read-only but for the manual override.
"""

import pytest
from django.contrib.auth import get_user_model

from billing.models import CompanyConfig, FiscalPolicy, TaxCategory, TaxRule, VatCheck

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client):
    client.force_login(
        get_user_model().objects.create_superuser(
            email="root@example.com", password="x"
        )
    )
    return client


@pytest.mark.parametrize("model", [TaxCategory, TaxRule, VatCheck])
def test_changelist_and_add_pages_load(staff_client, model):
    name = model._meta.model_name

    assert staff_client.get(f"/admin/billing/{name}/").status_code == 200
    assert staff_client.get(f"/admin/billing/{name}/add/").status_code == 200


@pytest.mark.parametrize("model", [TaxCategory, TaxRule])
def test_a_rate_row_opens_for_editing(staff_client, model):
    row = model.objects.first()

    assert (
        staff_client.get(
            f"/admin/billing/{model._meta.model_name}/{row.pk}/change/"
        ).status_code
        == 200
    )


def test_a_vies_row_opens_read_only(staff_client):
    row = VatCheck.objects.create(
        vat_number="DE812871812",
        status=VatCheck.VERIFIED,
        consultation_number="WAPIAAAAX1",
    )

    response = staff_client.get(f"/admin/billing/vatcheck/{row.pk}/change/")

    assert response.status_code == 200
    assert "WAPIAAAAX1" in response.content.decode()
    assert 'name="_save"' not in response.content.decode()


@pytest.mark.parametrize("model", [FiscalPolicy, CompanyConfig])
def test_a_singleton_opens_on_its_one_row(staff_client, model):
    row = model.objects.get()
    name = model._meta.model_name

    listing = staff_client.get(f"/admin/billing/{name}/")
    adding = staff_client.get(f"/admin/billing/{name}/add/")

    assert listing.status_code == adding.status_code == 302
    assert listing.url == adding.url == f"/admin/billing/{name}/{row.pk}/change/"
    assert staff_client.get(listing.url).status_code == 200


@pytest.mark.parametrize("model", [FiscalPolicy, CompanyConfig])
def test_a_singleton_without_its_row_is_added_once(staff_client, model):
    model.objects.all().delete()
    name = model._meta.model_name

    response = staff_client.get(f"/admin/billing/{name}/")

    assert (response.status_code, response.url) == (302, f"/admin/billing/{name}/add/")
    assert staff_client.get(response.url).status_code == 200


def test_erploras_identity_is_edited_in_the_admin(staff_client):
    company = CompanyConfig.objects.get()

    response = staff_client.post(
        f"/admin/billing/companyconfig/{company.pk}/change/",
        {
            "legal_name": "ERPLORA CLOUD SL",
            "trade_name": "ERPlora",
            "tax_id": "B27593136",
            "street": "Avda. de Lisboa, 17, 2º C",
            "city": "Coslada",
            "postal_code": "28822",
            "province": "Madrid",
            "country": "ES",
            "vat_regime": "general",
            "email": "billing@erplora.com",
            "phone": "+34 600 000 000",
            "website": "https://erplora.com",
            "currency": "EUR",
        },
    )

    assert response.status_code == 302, response.content.decode()[:2000]
    assert CompanyConfig.objects.get().phone == "+34 600 000 000"


# --- Stripe (lot L2-B) -------------------------------------------------------------------------------


def test_promo_codes_are_written_in_the_admin(staff_client):
    from billing.models import PromoCode

    assert staff_client.get("/admin/billing/promocode/").status_code == 200
    response = staff_client.post(
        "/admin/billing/promocode/add/",
        {"code": " Feria_2026 ", "trial_days": "30", "is_active": "on", "redemption_count": "0", "note": "Feria"},
    )

    assert response.status_code == 302, response.content
    assert PromoCode.objects.get().code == "feria_2026"


def test_a_promo_code_with_more_than_a_year_is_refused_in_the_form(staff_client):
    response = staff_client.post(
        "/admin/billing/promocode/add/", {"code": "long", "trial_days": "366", "redemption_count": "0"}
    )

    assert response.status_code == 200
    assert b"trial_days" in response.content


@pytest.mark.parametrize("model_name", ["checkoutattempt", "webhookevent", "paymentfailure"])
def test_what_stripe_did_is_read_only(staff_client, model_name):
    assert staff_client.get(f"/admin/billing/{model_name}/").status_code == 200
    assert staff_client.get(f"/admin/billing/{model_name}/add/").status_code == 403


class TestTheRowsOnlyTheCodeWrites:
    """BILLING-F27 (PLAN-SAAS §1.1, «Modelos sin ModelAdmin»): a promo code used, a series' counter and a downgrade
    waiting for the end of the period are seen in the admin and never written there: the checkout, the invoice's
    numbering and the plan change are their only writers."""

    @pytest.fixture
    def rows(self, db):
        from datetime import timedelta

        from django.utils import timezone

        from billing.models import InvoiceCounter, PlanChangeSchedule, PromoCode, PromoRedemption
        from hubs.models import Hub

        hub = Hub.objects.create(slug="bakery", name="Bakery")
        promo = PromoCode.objects.create(code="launch", trial_days=30)
        return {
            "promoredemption": PromoRedemption.objects.create(promo=promo, hub=hub, stripe_customer_id="cus_1"),
            "invoicecounter": InvoiceCounter.objects.create(series="ERP", year=2026, last_number=7),
            "planchangeschedule": PlanChangeSchedule.objects.create(
                hub=hub, stripe_schedule_id="sub_sched_1", plan_slug="starter", interval="month",
                starts_at=timezone.now() + timedelta(days=10),
            ),
        }

    @pytest.mark.parametrize("model_name", ["promoredemption", "invoicecounter", "planchangeschedule"])
    def test_it_is_listed_and_opens_but_is_never_added_changed_or_deleted(self, staff_client, rows, model_name):
        row = rows[model_name]
        base = f"/admin/billing/{model_name}/"

        assert staff_client.get(base).status_code == 200
        page = staff_client.get(f"{base}{row.pk}/change/")
        assert page.status_code == 200
        assert b'name="_save"' not in page.content
        assert staff_client.get(f"{base}add/").status_code == 403
        assert staff_client.post(f"{base}{row.pk}/delete/", {"post": "yes"}).status_code == 403
        assert type(row).objects.filter(pk=row.pk).exists()


def test_a_stripe_event_opens_read_only(staff_client):
    from billing.models import WebhookEvent

    row = WebhookEvent.objects.create(event_id="evt_1", event_type="invoice.paid", success=True, outcome="processed")

    page = staff_client.get(f"/admin/billing/webhookevent/{row.pk}/change/")

    assert page.status_code == 200
    assert b"evt_1" in page.content
    assert staff_client.post(f"/admin/billing/webhookevent/{row.pk}/delete/", {"post": "yes"}).status_code == 403


class TestAModuleSomeBusinessHas:
    """BILLING-G66, saas#2568: deleting the row of a paid module some business still has would make Stripe bill a
    price nobody sells (the business loses the module and keeps paying it). Like a protected relation, the
    admin refuses and names the businesses; taking it off sale («active» off) is how it stops being sold."""

    def delete(self, staff_client, module):
        return staff_client.post(f"/admin/apps/module/{module.pk}/delete/", {"post": "yes"})

    def test_its_row_is_not_deleted_and_the_page_says_who_has_it(self, staff_client, shop, inventory):
        from apps.models import Module
        from billing.tests.conftest import pay

        pay(shop, modules=["inventory"])

        response = self.delete(staff_client, inventory)

        assert Module.objects.filter(pk=inventory.pk).exists()
        assert "Panadería López" in response.content.decode()

    def test_nor_with_the_bulk_action(self, staff_client, shop, inventory):
        from apps.models import Module
        from billing.tests.conftest import pay

        pay(shop, modules=["inventory"])

        staff_client.post(
            "/admin/apps/module/",
            {"action": "delete_selected", "_selected_action": [str(inventory.pk)], "post": "yes"},
        )

        assert Module.objects.filter(pk=inventory.pk).exists()

    def test_one_cancelled_but_still_working_counts(self, staff_client, shop, inventory):
        from datetime import timedelta

        from django.utils import timezone

        from apps.models import Module
        from billing.tests.conftest import pay
        from hubs.models import SubscriptionItem

        pay(shop, modules=["inventory"])
        SubscriptionItem.objects.filter(module_slug="inventory").update(valid_until=timezone.now() + timedelta(days=3))

        self.delete(staff_client, inventory)

        assert Module.objects.filter(pk=inventory.pk).exists()

    def test_a_module_nobody_has_any_more_is_deleted(self, staff_client, shop, inventory):
        from datetime import timedelta

        from django.utils import timezone

        from apps.models import Module
        from billing.tests.conftest import pay
        from hubs.models import SubscriptionItem

        pay(shop, modules=["inventory"])
        SubscriptionItem.objects.filter(module_slug="inventory").update(valid_until=timezone.now() - timedelta(days=1))

        self.delete(staff_client, inventory)

        assert not Module.objects.filter(pk=inventory.pk).exists()
