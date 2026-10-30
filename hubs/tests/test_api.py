"""``GET /api/catalog/sectors`` and ``GET /api/catalog/business-types``: the public taxonomy.

Adapted from ERPlora/saas ``public/catalog/tests/test_categories_api.py`` (origin/develop), whose
nine tests covered the same pattern for ``Category``/``Subcategory`` (gone, round 16): public,
read-only, active rows only, ordered, nested parent, filter by parent. Here over ninja, bound to
the operations ``hubs.sector.list`` and ``hubs.business_type.list`` (PLAN §21.4), in the request's
language and without pagination (12 sectors, 70 business types).
"""

from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve

from hubs.models import BusinessType, Sector

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
SECTORS = "/api/catalog/sectors"
BUSINESS_TYPES = "/api/catalog/business-types"


@pytest.fixture
def catalog():
    hospitality = Sector.objects.create(
        code="hospitality",
        name_en="Hospitality & Food",
        name_es="Hostelería y Alimentación",
        description_en="Restaurants, bars",
        description_es="Restaurantes, bares",
        icon="restaurant-outline",
        color="#ff6b35",
        display_order=1,
    )
    retail = Sector.objects.create(code="retail", name_en="Retail & Commerce", name_es="Comercio", display_order=2)
    # Inactive: never listed.
    archived = Sector.objects.create(code="archived", name_en="Archived", display_order=0, is_active=False)

    BusinessType.objects.create(
        code="restaurant",
        name_en="Restaurant",
        name_es="Restaurante",
        description_en="Full-service restaurant",
        description_es="Restaurante con servicio de mesa",
        icon="restaurant-outline",
        color="#e74c3c",
        sector=hospitality,
        display_order=2,
        vertical="restaurant",
    )
    BusinessType.objects.create(code="bar", name_en="Bar", name_es="Bar", sector=hospitality, display_order=1)
    BusinessType.objects.create(code="grocery", name_en="Grocery", name_es="", sector=retail, display_order=1)
    BusinessType.objects.create(code="old_type", name_en="Old type", sector=archived, is_active=False)
    return {"hospitality": hospitality, "retail": retail}


def _get(client, path, **params):
    response = client.get(path, params, HTTP_HOST=HOST)
    assert response.status_code == 200, response.content
    return response.json()


def _codes(rows):
    return [row["code"] for row in rows]


def test_the_routes_are_bound_to_their_operations():
    from hubs.api import router

    routes = {
        path: (
            sorted(method for route in view.operations for method in route.methods),
            "|".join(route.operation_id for route in sorted(view.operations, key=lambda route: route.methods)),
        )
        for path, view in router.path_operations.items()
    }
    assert routes == {
        "/catalog/sectors": (["GET"], "hubs.sector.list"),
        "/catalog/business-types": (["GET"], "hubs.business_type.list"),
        "/plans": (["GET"], "hubs.plan.list"),
        "/hubs/businesses": (["GET", "POST"], "hubs.business.list|hubs.business.create"),
        "/hubs/businesses/detail": (["GET"], "hubs.business.get"),
        "/hubs/businesses/update": (["POST"], "hubs.business.update"),
        "/hubs/businesses/address": (["POST"], "hubs.business.change_address"),
        "/hubs/businesses/delete": (["POST"], "hubs.business.delete"),
        "/hubs/businesses/restore": (["POST"], "hubs.business.restore"),
        "/hubs/businesses/open": (["POST"], "hubs.business.open"),
        "/hubs/address": (["GET"], "hubs.address.propose"),
        "/hubs/members": (["GET"], "hubs.member.list"),
        "/hubs/members/invite": (["POST"], "hubs.member.invite"),
        "/hubs/members/change_role": (["POST"], "hubs.member.change_role"),
        "/hubs/members/remove": (["POST"], "hubs.member.remove"),
        "/hubs/members/resend": (["POST"], "hubs.member.resend"),
        "/hubs/members/cancel": (["POST"], "hubs.member.cancel"),
        "/hubs/invitations": (["GET"], "hubs.invitation.list_mine"),
        "/hubs/invitations/accept": (["POST"], "hubs.invitation.accept"),
        "/hubs/invitations/decline": (["POST"], "hubs.invitation.decline"),
        "/hubs/ownership/transfer": (["POST"], "hubs.ownership.transfer"),
        "/hubs/ownership/accept": (["POST"], "hubs.ownership.accept"),
        "/hubs/ownership/decline": (["POST"], "hubs.ownership.decline"),
        "/hubs/ownership/cancel": (["POST"], "hubs.ownership.cancel"),
        "/hubs/billing-profile": (["GET", "POST"], "hubs.billing_profile.get|hubs.billing_profile.update"),
        "/hubs/usage": (["GET"], "hubs.usage.get"),
        "/hubs/usage/series": (["GET"], "hubs.usage.series"),
        "/hubs/data-copies": (["GET"], "hubs.data_copy.list"),
        "/hubs/data-copies/link": (["GET"], "hubs.data_copy.link"),
    }
    assert resolve(SECTORS).url_name and resolve(BUSINESS_TYPES).url_name


class TestSectorList:
    def test_lists_the_active_sectors(self, client, catalog):
        assert _codes(_get(client, SECTORS)["sectors"]) == ["hospitality", "retail"]

    def test_is_public_no_auth_required(self, client, catalog):
        """An anonymous visitor (sign-up, industry pages) and an account read the same list."""
        anonymous = _get(client, SECTORS)
        client.force_login(get_user_model().objects.create_user(email="ana@example.com", password="x"))

        assert _get(client, SECTORS) == anonymous

    def test_response_shape(self, client, catalog):
        hospitality = _get(client, SECTORS)["sectors"][0]

        # When the row last changed, for the public sitemap's lastmod.
        sent = datetime.fromisoformat(hospitality.pop("updated_at"))
        assert abs(sent - catalog["hospitality"].updated_at) < timedelta(milliseconds=1)  # JSON keeps milliseconds
        assert hospitality == {
            "code": "hospitality",
            "name": "Hospitality & Food",
            "description": "Restaurants, bars",
            "icon": "restaurant-outline",
            "color": "#ff6b35",
        }

    def test_ordering_by_display_order_then_code(self, client, catalog):
        Sector.objects.create(code="automotive", name_en="Automotive", display_order=2)

        assert _codes(_get(client, SECTORS)["sectors"]) == ["hospitality", "automotive", "retail"]


class TestBusinessTypeList:
    def test_lists_the_active_business_types_by_their_order_then_code_across_sectors(self, client, catalog):
        """Like the origin ``catalog`` (``BusinessType.Meta.ordering = ["order", "code"]``): one order for
        every type, not grouped by sector, so ``/industries/`` interleaves them as the seed orders them.
        Here grocery (retail, 1) sits between bar (hospitality, 1) and restaurant (hospitality, 2)."""
        assert _codes(_get(client, BUSINESS_TYPES)["business_types"]) == ["bar", "grocery", "restaurant"]

    def test_response_shape_includes_the_nested_sector_and_the_vertical(self, client, catalog):
        rows = {row["code"]: row for row in _get(client, BUSINESS_TYPES)["business_types"]}

        assert rows["restaurant"].pop("updated_at")
        assert rows["restaurant"] == {
            "code": "restaurant",
            "name": "Restaurant",
            "description": "Full-service restaurant",
            "icon": "restaurant-outline",
            "color": "#e74c3c",
            "sector": {"code": "hospitality", "name": "Hospitality & Food"},
            "vertical": "restaurant",
        }
        assert rows["bar"]["vertical"] == ""

    def test_a_business_type_without_a_sector_takes_its_place_by_its_order(self, client, catalog):
        BusinessType.objects.create(code="saas", name_en="SaaS", display_order=1)

        rows = _get(client, BUSINESS_TYPES)["business_types"]

        assert _codes(rows) == ["bar", "grocery", "saas", "restaurant"]
        assert rows[2]["sector"] is None

    def test_filter_by_sector_code(self, client, catalog):
        assert _codes(_get(client, BUSINESS_TYPES, sector="hospitality")["business_types"]) == ["bar", "restaurant"]

    def test_filter_by_unknown_sector_returns_empty(self, client, catalog):
        assert _get(client, BUSINESS_TYPES, sector="does-not-exist") == {"business_types": []}

    def test_is_public_no_auth_required(self, client, catalog):
        assert _codes(_get(client, BUSINESS_TYPES)["business_types"])


class TestLanguage:
    def test_served_in_the_language_of_the_request(self, client, catalog):
        response = client.get(BUSINESS_TYPES, {"sector": "hospitality"}, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")
        restaurant = response.json()["business_types"][1]

        assert (restaurant["name"], restaurant["description"]) == ("Restaurante", "Restaurante con servicio de mesa")
        assert restaurant["sector"] == {"code": "hospitality", "name": "Hostelería y Alimentación"}

    def test_a_blank_translation_is_served_in_english(self, client, catalog):
        response = client.get(BUSINESS_TYPES, {"sector": "retail"}, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

        assert response.json()["business_types"][0]["name"] == "Grocery"
