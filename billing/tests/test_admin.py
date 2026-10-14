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
