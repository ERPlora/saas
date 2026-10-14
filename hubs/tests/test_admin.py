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


# --- The account plane of a business (L1-A2): read-mostly, with the actions of the platform -------

from django.contrib.auth.models import Group  # noqa: E402

from hubs import services  # noqa: E402
from hubs.models import (  # noqa: E402
    BillingProfile,
    Hub,
    HubMember,
    HubOwnershipTransfer,
    SessionRevocation,
    Subscription,
    SubscriptionItem,
)
from hubs.tests.conftest import add_member, member_of  # noqa: E402

ACCOUNT_PLANE = ("hub", "hubmember", "hubownershiptransfer", "billingprofile", "subscription", "subscriptionitem", "sessionrevocation")


@pytest.fixture
def plane(business, owner, make_user):
    """One row of every model of a business's account plane."""
    from datetime import timedelta

    from django.utils import timezone

    ana = make_user("ana@example.com")
    add_member(business, ana, HubMember.Role.ADMIN)
    transfer = HubOwnershipTransfer.objects.create(
        hub=business,
        from_user=owner,
        to_user=ana,
        from_email=owner.email,
        to_email=ana.email,
        expires_at=timezone.now() + timedelta(days=7),
    )
    item = SubscriptionItem.objects.create(subscription=business.subscription, module_slug="appointment")
    revocation = SessionRevocation.objects.create(user=ana, hub=business)
    return {
        "hub": business,
        "hubmember": member_of(business, ana),
        "hubownershiptransfer": transfer,
        "billingprofile": business.billing_profile,
        "subscription": business.subscription,
        "subscriptionitem": item,
        "sessionrevocation": revocation,
    }


@pytest.mark.parametrize("model", ACCOUNT_PLANE)
def test_the_account_plane_is_listed_and_shown(staff_client, plane, model):
    assert staff_client.get(f"/admin/hubs/{model}/").status_code == 200
    page = staff_client.get(f"/admin/hubs/{model}/{plane[model].pk}/change/")
    assert page.status_code == 200


@pytest.mark.parametrize("model", ACCOUNT_PLANE)
def test_the_account_plane_is_read_only_its_writes_are_the_operations(staff_client, plane, model):
    """A business is created, changed and deleted by its operations (state version, mirror, push to the
    Hub): the admin adds, changes and deletes nothing, even for a superuser."""
    from django.contrib import admin

    model_admin = admin.site._registry[type(plane[model])]
    request = staff_client.get("/admin/").wsgi_request

    assert staff_client.get(f"/admin/hubs/{model}/add/").status_code == 403
    assert not model_admin.has_change_permission(request, plane[model])
    assert not model_admin.has_delete_permission(request, plane[model])


def test_the_business_page_shows_its_members(staff_client, plane):
    page = staff_client.get(f"/admin/hubs/hub/{plane['hub'].pk}/change/").content.decode()

    assert "ana@example.com" in page
    assert "owner@example.com" in page


def test_the_changelist_finds_a_business_by_its_address(staff_client, plane):
    page = staff_client.get("/admin/hubs/hub/", {"q": plane["hub"].slug}).content.decode()

    assert plane["hub"].name in page


def _act(client, model, action, rows):
    return client.post(
        f"/admin/hubs/{model}/",
        {"action": action, "_selected_action": [str(row.pk) for row in rows]},
        follow=True,
    )


class TestTheActions:
    def test_send_the_latest_state_pushes_a_newer_snapshot(self, staff_client, business, hub_double):
        Hub.objects.filter(pk=business.pk).update(pending_hub_call="", status=Hub.Status.ACTIVE)
        before = Hub.objects.get(pk=business.pk).state_version

        response = _act(staff_client, "hub", "send_latest_state", [business])

        hub = Hub.objects.get(pk=business.pk)
        assert hub.state_version == before + 1 == hub.pushed_state_version
        (call,) = hub_double.calls_to("PUT", "/state")
        assert call.body["version"] == before + 1
        assert "1 business(es) up to date in the Hub" in response.content.decode()

    def test_retry_what_the_hub_owes_sends_the_registry_still_owed(self, staff_client, business, hub_double):
        response = _act(staff_client, "hub", "retry_owed", [business])

        assert [c.path for c in hub_double.calls_to("PUT")] == [
            f"/internal/hubs/{business.id}",
            f"/internal/hubs/{business.id}/state",
        ]
        assert Hub.objects.get(pk=business.pk).pending_hub_call == ""
        assert "1 business(es) up to date in the Hub" in response.content.decode()

    def test_with_the_hub_away_the_action_says_what_stays_owed(self, staff_client, business, offline_hub):
        response = _act(staff_client, "hub", "retry_owed", [business])

        assert "1 business(es) still owed" in response.content.decode()
        assert Hub.objects.get(pk=business.pk).pending_hub_call == "put"

    def test_end_the_sessions_now_delivers_a_pending_revocation(self, staff_client, plane, hub_double):
        revocation = plane["sessionrevocation"]

        response = _act(staff_client, "sessionrevocation", "deliver_now", [revocation])

        (call,) = hub_double.calls_to("POST", "/internal/sessions/revoke")
        assert call.body["hub_id"] == str(revocation.hub_id)
        assert SessionRevocation.objects.get(pk=revocation.pk).delivered_at is not None
        assert "1 session end(s) delivered" in response.content.decode()


class TestSupport:
    """``support`` (staff, view only, PLAN-SAAS §2.1 round 11) sees the account plane and acts on nothing."""

    @pytest.fixture
    def support_client(self, client, make_user):
        helper = make_user("help@erplora.com", is_staff=True)
        helper.groups.add(Group.objects.get(name="support"))
        client.force_login(helper)
        return client

    @pytest.mark.parametrize("model", ACCOUNT_PLANE)
    def test_sees_every_model(self, support_client, plane, model):
        assert support_client.get(f"/admin/hubs/{model}/").status_code == 200

    def test_runs_no_action(self, support_client, business, hub_double):
        _act(support_client, "hub", "send_latest_state", [business])

        assert hub_double.calls == []
