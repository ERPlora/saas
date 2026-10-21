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
def rows(no_plans):
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


def test_staff_edit_the_monthly_messages_of_a_plan(staff_client, rows):
    """The assistant and WhatsApp messages a plan includes are edited next to its limits (2026-10-15)."""
    page = staff_client.get(f"/admin/hubs/plan/{rows['plan'].pk}/change/").content.decode()

    assert 'name="assistant_messages_per_month"' in page
    assert 'name="whatsapp_messages_per_month"' in page


def test_staff_write_every_text_of_a_plan_in_english_and_in_spanish(staff_client, rows):
    """HUBS-F05 (HUBS-G06, HUBS-G44: the old admin's translation tabs, ``PlanTranslationOptions``): the name,
    the description, the card's features and its badge, one field per language, English the source."""
    page = staff_client.get(f"/admin/hubs/plan/{rows['plan'].pk}/change/").content.decode()

    for text in ("name", "description", "features", "featured_label"):
        for language in ("en", "es"):
            assert f'name="{text}_{language}"' in page, f"{text}_{language}"


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


class TestThePlanPrices:
    """BILLING-F28: a plan is not saved with a Stripe price that would charge something else."""

    def save(self, staff_client, plan, **changes):
        from django.forms.models import model_to_dict

        import json

        def posted(value):
            # As the form sends them: JSON fields as JSON, nothing as an empty field.
            return json.dumps(value) if isinstance(value, (list, dict)) else "" if value is None else value

        data = {key: posted(value) for key, value in model_to_dict(plan).items()}
        data.update(changes)
        return staff_client.post(f"/admin/hubs/plan/{plan.pk}/change/", data, follow=True)

    def test_a_price_stripe_refuses_keeps_the_plan_as_it_was(self, staff_client, plans, settings, monkeypatch):
        from billing import services

        settings.STRIPE_SECRET_KEY = "rk_test_51abc"
        monkeypatch.setattr(
            services, "plan_price_problems", lambda **kwargs: {"stripe_price_id": "This price is not in euros."}
        )
        starter = Plan.objects.get(slug="starter")

        page = self.save(staff_client, starter, stripe_price_id="price_usd").content.decode()

        assert "This price is not in euros." in page
        assert Plan.objects.get(slug="starter").stripe_price_id == starter.stripe_price_id

    def test_without_stripe_it_is_saved_and_says_it_was_not_checked(self, staff_client, plans, monkeypatch):
        from billing import services

        def unavailable(**kwargs):
            raise services.PriceCheckUnavailable("Stripe is not configured here: the prices were not checked.")

        monkeypatch.setattr(services, "plan_price_problems", unavailable)
        starter = Plan.objects.get(slug="starter")

        page = self.save(staff_client, starter, stripe_price_id="price_new").content.decode()

        assert "Stripe is not configured here: the prices were not checked." in page
        assert Plan.objects.get(slug="starter").stripe_price_id == "price_new"

    def test_other_changes_ask_stripe_nothing(self, staff_client, plans, monkeypatch):
        from billing import services

        asked = []
        monkeypatch.setattr(services, "plan_price_problems", lambda **kwargs: asked.append(kwargs) or {})

        self.save(staff_client, Plan.objects.get(slug="starter"), name_es="Inicio")

        assert asked == []


class TestTheTestClock:
    """BILLING-F29: the staff try a real charge in PRE with a Stripe test clock, from the business's row."""

    @pytest.fixture
    def actions(self, staff_client):
        def offered():
            page = staff_client.get("/admin/hubs/hub/").content.decode()
            return {name for name in ("attach_test_clock", "advance_test_clock") if f'value="{name}"' in page}

        return offered

    def test_with_test_keys_both_actions_are_offered(self, actions, business, settings):
        settings.STRIPE_SECRET_KEY = "rk_test_51abc"

        assert actions() == {"attach_test_clock", "advance_test_clock"}

    @pytest.mark.parametrize("key", ["rk_live_51abc", ""])
    def test_without_test_keys_they_are_not_offered(self, actions, business, settings, key):
        settings.STRIPE_SECRET_KEY = key

        assert actions() == set()

    def test_attaching_says_which_clock_or_why_not(self, staff_client, business, settings, monkeypatch):
        from billing import services

        settings.STRIPE_SECRET_KEY = "rk_test_51abc"
        monkeypatch.setattr(services, "attach_test_clock", lambda hub_id: "clock_qa")

        assert "clock_qa" in _act(staff_client, "hub", "attach_test_clock", [business]).content.decode()

        def refused(hub_id):
            raise services.TestClockRefused("Its payer is a Stripe customer already.")

        monkeypatch.setattr(services, "attach_test_clock", refused)
        assert "Its payer is a Stripe customer already." in _act(
            staff_client, "hub", "attach_test_clock", [business]
        ).content.decode()


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


# --- The usage of each business, day by day (L4-A): read only, as the Hub measured it ---------------


class TestTheUsageAdmin:
    @pytest.fixture
    def day(self, business):
        from datetime import date

        from hubs.models import HubUsageDaily

        return HubUsageDaily.objects.create(
            hub=business,
            day=date(2026, 10, 13),
            s3_bytes=3 * 1024**3,
            db_bytes=250 * 1024**2,
            active_users_1d=3,
            active_users_30d=4,
        )

    def test_it_is_listed_with_its_sizes_readable_and_shown(self, staff_client, day):
        listing = staff_client.get("/admin/hubs/hubusagedaily/").content.decode()

        # Django's ``filesizeformat`` (binary units, a non-breaking space before the unit).
        assert "3.0\xa0GB" in listing and "250.0\xa0MB" in listing
        assert staff_client.get(f"/admin/hubs/hubusagedaily/{day.pk}/change/").status_code == 200

    def test_it_finds_a_business_by_its_address(self, staff_client, day, business):
        listing = staff_client.get("/admin/hubs/hubusagedaily/", {"q": business.slug}).content.decode()

        assert business.name in listing

    def test_it_is_read_only_only_the_nightly_collection_writes_it(self, staff_client, day):
        from django.contrib import admin

        model_admin = admin.site._registry[type(day)]
        request = staff_client.get("/admin/").wsgi_request

        assert staff_client.get("/admin/hubs/hubusagedaily/add/").status_code == 403
        assert not model_admin.has_change_permission(request, day)
        assert not model_admin.has_delete_permission(request, day)
