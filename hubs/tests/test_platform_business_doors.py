"""What nobody does to ERPlora's own business, and what every pass over the businesses does with it.

It has no plan nor payments, and its name, address and country are not erplora.com's to change: each door that would is
refused with ``hubs.platform_business``, saying why in the person's language, and no sweep charges, warns, suspends or
deletes it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from live.context import Scope, system_context
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from hubs.models import BillingProfile, CustomDomain, Hub, HubMember, HubUsageDaily, Plan, Subscription
from hubs.queries import hub_usage, plan_catalog
from hubs.schemas.businesses import BusinessAddressIn, BusinessDeleteIn, BusinessUpdateIn
from hubs.schemas.common import ByIdIn
from hubs.schemas.custom_domains import CustomDomainRequestIn
from hubs.schemas.hub_usage import UsageGetIn, UsageRecordIn
from hubs.schemas.payers import BillingProfileIn
from hubs.schemas.subscriptions import SubscriptionApplyIn
from hubs.services import (
    billing_profiles,
    business_settings,
    custom_domain_requests,
    deletion,
    hub_push,
    platform_actions,
    reconciliation,
    scheduled_moves,
    subscription_sync,
    suspensions,
    usage_collection,
)
from hubs.tests.conftest import add_member, create_business, ctx_for
from hubs.tests.test_admin import _act
from hubs.tests.test_reconcile_hub_states import run

pytestmark = pytest.mark.django_db

PAYER = {"billing_name": "ERPlora", "billing_country": "ES", "billing_postal_code": "28001", "billing_email": "a@b.es"}
#: Every door that changes a business, by its name: what it is called with.
DOORS = {
    "update its name": (business_settings.business_update, lambda hub: BusinessUpdateIn(id=hub.id, name="Other")),
    "update its country": (business_settings.business_update, lambda hub: BusinessUpdateIn(id=hub.id, country="PT")),
    "update its language": (business_settings.business_update, lambda hub: BusinessUpdateIn(id=hub.id, language="en")),
    "update its time zone": (
        business_settings.business_update,
        lambda hub: BusinessUpdateIn(id=hub.id, timezone="Atlantic/Canary"),
    ),
    "change its address": (
        business_settings.business_change_address,
        lambda hub: BusinessAddressIn(id=hub.id, slug="erplora-hq"),
    ),
    "delete it": (deletion.business_delete, lambda hub: BusinessDeleteIn(id=hub.id, confirm_name=hub.name)),
    "restore it": (deletion.business_restore, lambda hub: ByIdIn(id=hub.id)),
    "say who pays for it": (
        billing_profiles.billing_profile_update,
        lambda hub: BillingProfileIn(hub_id=hub.id, **PAYER),
    ),
    "connect a domain to it": (
        custom_domain_requests.custom_domain_request,
        lambda hub: CustomDomainRequestIn(id=hub.id, domain="www.minegocio.es"),
    ),
}


def row(hub):
    return Hub.objects.filter(pk=hub.pk).values().get()


class TestTheDoors:
    @pytest.mark.parametrize("door", DOORS)
    def test_its_owner_is_refused_and_nothing_changes(self, platform_business, founder, hub_double, settings, door):
        settings.CUSTOM_DOMAINS_ENABLED = True
        operation, data = DOORS[door]
        before, calls = row(platform_business), len(hub_double.calls)

        with pytest.raises(Conflict) as caught:
            operation(ctx_for(founder), data(platform_business))

        assert caught.value.code == "hubs.platform_business"
        assert row(platform_business) == before
        assert len(hub_double.calls) == calls
        assert not BillingProfile.objects.exists()
        assert not CustomDomain.objects.exists()

    @pytest.mark.parametrize("door", DOORS)
    def test_the_refusal_comes_after_the_role(self, platform_business, make_user, settings, door):
        settings.CUSTOM_DOMAINS_ENABLED = True
        employee, stranger = make_user("ana@example.com"), make_user("stranger@example.com")
        add_member(platform_business, employee, HubMember.Role.EMPLOYEE)
        operation, data = DOORS[door]

        with pytest.raises(PermissionDenied):
            operation(ctx_for(employee), data(platform_business))
        with pytest.raises(NotFound):
            operation(ctx_for(stranger), data(platform_business))

    def test_the_refusal_speaks_the_person_s_language(self, client, platform_business, founder):
        from accounts.tests.conftest import api_post

        client.force_login(founder)
        body = {"id": str(platform_business.id), "confirm_name": "ERPlora"}
        said = {}
        for language in ("en", "es"):
            founder.language = language
            founder.save(update_fields=["language"])
            answer = api_post(client, "/api/hubs/businesses/delete", body)
            assert (answer.status_code, answer.json()["error"]["code"]) == (409, "hubs.platform_business")
            said[language] = answer.json()["error"]["message"]

        assert said["en"] and said["es"] and said["en"] != said["es"]

    @pytest.mark.parametrize("door", ["update its name", "update its language", "say who pays for it"])
    def test_any_other_business_still_changes(self, business, owner, hub_double, door):
        operation, data = DOORS[door]

        operation(ctx_for(owner), data(business))

        assert Hub.objects.get(pk=business.pk).billing_profile is not None

    def test_any_other_business_is_still_moved_and_deleted(self, business, owner, hub_double):
        moved = business_settings.business_change_address(
            ctx_for(owner), BusinessAddressIn(id=business.id, slug="casa-manolo")
        )
        gone = deletion.business_delete(ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name))

        assert (moved.slug, gone.status) == ("casa-manolo", "deleting")


class TestWithoutAPlan:
    def test_it_has_no_plan_not_even_the_free_one(self, platform_business):
        assert plan_catalog.effective_plan(platform_business.id, timezone.now()) is None

    def test_a_business_without_a_subscription_still_has_the_free_one(self, business):
        Subscription.objects.filter(hub=business).delete()

        assert plan_catalog.effective_plan(business.id, timezone.now()).slug == "free"

    def test_what_stripe_says_of_a_plan_never_reaches_it(self, platform_business, hub_double):
        before = row(platform_business)
        data = SubscriptionApplyIn(
            hub_id=platform_business.id, plan="starter", status="past_due", stripe_subscription_id="sub_1", standing="suspended"
        )

        with pytest.raises(Conflict) as caught:
            subscription_sync.subscription_apply(system_context(Scope("user", "system")), data)

        assert caught.value.code == "hubs.platform_business"
        assert row(platform_business) == before
        assert not Subscription.objects.filter(hub=platform_business).exists()

    def test_a_change_of_a_plan_s_rights_owes_it_nothing(self, platform_business, business):
        for plan in Plan.objects.all():
            subscription_sync.owe_plan_rights(plan)
        for tier in plan_catalog.LEVELS:
            subscription_sync.owe_module_rights(tier)

        assert Hub.objects.get(pk=platform_business.pk).state_version == 1


class TestItsUsage:
    def measured(self, hub):
        day = datetime.now(UTC).date() - timedelta(days=1)
        return UsageRecordIn(id=hub.id, day=day, s3_bytes=1, db_bytes=1, active_users_1d=1, active_users_30d=1)

    def test_the_night_s_measure_is_not_kept_nor_told(self, platform_business, hub_double):
        day = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        hub_double.usage[day] = [
            {"id": str(platform_business.id), "s3_bytes": 1, "db_bytes": 1, "active_users_1d": 1, "active_users_30d": 1}
        ]

        out = run("collect_hub_usage", "--day", day)

        assert "unknown=1" in out
        assert not HubUsageDaily.objects.exists()
        assert not OutboxEvent.objects.filter(name="hubs.business.usage_collected").exists()

    def test_any_other_business_s_is(self, business, hub_double):
        recorded = usage_collection.usage_record(system_context(Scope("user", "system")), self.measured(business))

        assert recorded.changed is True

    def test_its_own_read_never_promises_the_figures_of_any_other(self, platform_business, business, founder, owner):
        said = []
        for hub, user in ((platform_business, founder), (business, owner)):
            with pytest.raises(NotFound) as caught:
                hub_usage.usage_get(ctx_for(user), UsageGetIn(business_id=hub.id))
            assert caught.value.code == "hubs.usage_not_collected"
            said.append(caught.value.message)

        assert said[0] != said[1]


class TestThePasses:
    def test_the_reconciliation_settles_its_photo_and_then_leaves_it_alone(self, platform_business, hub_double):
        hub_double.calls.clear()

        first, second = reconciliation.reconcile(), reconciliation.reconcile()

        assert (first["delivered"], second["delivered"], second["owed"]) == (1, 0, 0)
        assert [(call.method, call.path) for call in hub_double.calls] == [
            ("PUT", f"/internal/hubs/{platform_business.id}/state")
        ]

    def test_a_hub_away_leaves_only_its_photo_owed(self, platform_business, hub_double):
        hub_double.answer("PUT", "/state$", 503)
        assert reconciliation.reconcile()["owed"] == 1
        hub_double._answers.clear()

        assert reconciliation.reconcile()["delivered"] == 1
        assert Hub.objects.get(pk=platform_business.pk).pending_hub_call == ""

    def test_every_night_its_photo_goes_out_again_and_nothing_else(self, platform_business, hub_double):
        hub_double.calls.clear()

        platform_actions.push_snapshots()
        platform_actions.push_snapshots()

        assert [(call.path.rsplit("/", 1)[-1], call.body["version"]) for call in hub_double.calls] == [
            ("state", 2),
            ("state", 3),
        ]
        assert all(set(call.body) == {"hub_id", "slug", "version", "members"} for call in hub_double.calls)

    def test_the_clock_of_the_suspended_never_sees_it(self, platform_business, hub_double):
        assert not any(suspensions.age_suspended().values())

    def test_its_scheduled_maintenance_is_asked_as_any_other_s(self, platform_business, hub_double):
        hub_push.sync_hub(platform_business.id)
        before = row(platform_business)

        counts = scheduled_moves.check_scheduled_moves()

        assert (counts["checked"], counts["scheduled"]) == (1, 0)
        assert row(platform_business) == before


class TestTheStaff:
    @pytest.fixture
    def staff_client(self, client):
        client.force_login(get_user_model().objects.create_superuser(email="root@example.com", password="x"))
        return client

    @pytest.mark.parametrize("action", ["allow_internal_plans", "stop_internal_plans"])
    def test_it_is_not_marked_for_the_internal_plans_and_the_admin_says_why(
        self, staff_client, platform_business, action
    ):
        page = _act(staff_client, "hub", action, [platform_business]).content.decode()

        assert Hub.objects.get(pk=platform_business.pk).can_buy_internal_plans is False
        assert "own business has no plan" in page

    def test_the_businesses_chosen_with_it_are_marked(self, staff_client, platform_business, make_user):
        other = create_business(make_user("other@example.com"), name="Otro Bar")

        page = _act(staff_client, "hub", "allow_internal_plans", [platform_business, other]).content.decode()

        assert Hub.objects.get(pk=other.pk).can_buy_internal_plans is True
        assert "1 business(es): its owner now sees the internal plans" in page

    def test_choosing_only_others_says_nothing_of_it(self, staff_client, platform_business, business):
        page = _act(staff_client, "hub", "allow_internal_plans", [business]).content.decode()

        assert Hub.objects.get(pk=business.pk).can_buy_internal_plans is True
        assert "own business has no plan" not in page

    @pytest.mark.parametrize("action", ["attach_test_clock", "advance_test_clock"])
    def test_it_takes_no_test_clock(self, staff_client, platform_business, settings, action):
        settings.STRIPE_SECRET_KEY = "rk_test_double"

        page = _act(staff_client, "hub", action, [platform_business]).content.decode()

        assert "own business has no plan" in page

    def test_sending_its_latest_state_sends_its_photo(self, staff_client, platform_business, hub_double):
        hub_double.calls.clear()

        _act(staff_client, "hub", "send_latest_state", [platform_business])

        assert [call.path.rsplit("/", 1)[-1] for call in hub_double.calls] == ["state"]

    @pytest.mark.parametrize("path", ["add/", "{pk}/change/", "{pk}/delete/"])
    def test_the_admin_neither_adds_nor_changes_nor_deletes_it(self, staff_client, platform_business, path):
        address = f"/admin/hubs/hub/{path.format(pk=platform_business.pk)}"
        before = row(platform_business)

        assert staff_client.post(address, {"name": "Other", "post": "yes"}).status_code == 403
        assert row(platform_business) == before
