"""The Django admin shows every model of hubs (PLAN-SAAS §6: «el Django admin, lo más completo posible»)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.tests.factories import make_app
from hubs.models import BusinessType, Plan, Sector

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client):
    client.force_login(get_user_model().objects.create_superuser(email="root@example.com", password="x"))
    return client


@pytest.fixture
def rows():
    sector = Sector.objects.create(code="hospitality", name_en="Hospitality & Food", name_es="Hostelería")
    business_type = BusinessType.objects.create(
        code="restaurant", name_en="Restaurant", name_es="Restaurante", sector=sector, vertical="restaurant"
    )
    plan = Plan.objects.create(slug="starter", name_en="Starter", price_monthly=Decimal("29.99"))
    return {"sector": sector, "businesstype": business_type, "plan": plan}


@pytest.mark.parametrize("model", ["sector", "businesstype", "plan"])
def test_changelist_add_and_change_pages_load(staff_client, rows, model):
    assert staff_client.get(f"/admin/hubs/{model}/").status_code == 200
    assert staff_client.get(f"/admin/hubs/{model}/add/").status_code == 200
    assert staff_client.get(f"/admin/hubs/{model}/{rows[model].pk}/change/").status_code == 200


def test_the_changelists_search_by_code(staff_client, rows):
    response = staff_client.get("/admin/hubs/businesstype/", {"q": "restaurant"})

    assert response.status_code == 200
    assert "Restaurant" in response.content.decode()


def test_the_admin_refuses_a_folded_spanish_name(staff_client, rows):
    """The model's guard reaches the admin form: the row is not saved and the field says why."""
    response = staff_client.post(
        "/admin/hubs/businesstype/add/",
        {"code": "barber_shop", "name_en": "Barber Shop", "name_es": "Barberia", "display_order": 0, "is_active": "on"},
    )

    assert response.status_code == 200
    assert not BusinessType.objects.filter(code="barber_shop").exists()
    assert "«Barberia» → «Barbería»" in response.content.decode()


def test_a_business_type_is_added_with_its_sector_and_vertical(staff_client, rows):
    # The vertical is one an app of the catalog builds (BusinessType.clean, spec §5.4).
    make_app("appointment", verticals=["hair_salon"])
    response = staff_client.post(
        "/admin/hubs/businesstype/add/",
        {
            "code": "barber_shop",
            "name_en": "Barber Shop",
            "name_es": "Barbería",
            "sector": rows["sector"].pk,
            "vertical": "hair_salon",
            "display_order": 1,
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    added = BusinessType.objects.get(code="barber_shop")
    assert (added.sector, added.vertical) == (rows["sector"], "hair_salon")
