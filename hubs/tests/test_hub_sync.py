"""What the SaaS tells the Hub after each COMMIT, against the Hub double (PLAN-SAAS §2.2, §3.1, §3.4).

New with this lot (plan 2026-10-13 §3, the push to the Hub): ``services.sync_hub`` brings the Hub to what
the SaaS knows (the registry, the deletion or the restoration it owes, then the snapshot), records
each acknowledgement and leaves the rest pending when the Hub is away; ``reconcile_hub_states`` retries it.
Ported from ``test_entitlement_push`` (origin/develop): a push is delivered only when the Hub
acknowledged it; anything else is «not delivered», and nothing breaks.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.tests.factories import make_app
from hubs import hub_client, queries, services
from hubs.models import (
    BusinessType,
    Hub,
    HubMember,
    Plan,
    Subscription,
    SubscriptionItem,
)
from hubs.schemas import BusinessDeleteIn, BusinessListIn, BusinessUpdateIn, ByIdIn
from hubs.tests.conftest import add_member, create_business, ctx_for

pytestmark = pytest.mark.django_db


def fresh(hub):
    return Hub.objects.get(pk=hub.pk)


# --- What travels ---------------------------------------------------------------------------------


class TestTheRegistry:
    def test_it_carries_what_the_hub_needs_to_provision(self, business):
        assert queries.hub_registry(business.id) == {
            "id": str(business.id),
            "slug": "bar-manolo",
            "name": "Bar Manolo",
            "country": "ES",
            "timezone": "Europe/Madrid",
            "language": "es",
            "vertical": None,
        }

    def test_the_vertical_of_the_chosen_type_travels(self, owner, plans):
        make_app("table", verticals=["restaurant"])
        BusinessType.objects.create(
            code="restaurant", name_en="Restaurant", vertical="restaurant"
        )

        hub = create_business(owner, business_type="restaurant")

        assert queries.hub_registry(hub.id)["vertical"] == "restaurant"

    def test_a_type_without_vertical_sends_none(self, owner, plans):
        BusinessType.objects.create(code="bar", name_en="Bar", vertical="")

        hub = create_business(owner, business_type="bar")

        assert queries.hub_registry(hub.id)["vertical"] is None


class TestTheSnapshot:
    def test_it_is_the_shape_of_section_2_2(self, business, team):
        snapshot = queries.hub_snapshot(business.id)

        assert set(snapshot) == {
            "hub_id",
            "version",
            "status",
            "plan",
            "modules",
            "members",
        }
        assert (snapshot["hub_id"], snapshot["version"], snapshot["status"]) == (
            str(business.id),
            fresh(business).state_version,
            "active",
        )

    def test_the_plan_is_the_trials_while_it_lasts(self, business):
        """Free is born with 15 days of Starter: the Hub applies Starter's rights meanwhile."""
        assert queries.hub_snapshot(business.id)["plan"] == {
            "slug": "starter",
            "included_level": "basic",
            "max_devices": 0,
            "max_users": 0,
            "max_db_connections": 3,
            "statement_timeout_seconds": 15,
            # The monthly messages the Hub counts and blocks at (PLAN-SAAS §3.6, 2026-10-15): 0 = none.
            "assistant_messages_per_month": 300,
            "whatsapp_messages_per_month": 150,
        }

    def test_after_the_trial_it_is_free(self, business):
        Subscription.objects.filter(hub=business).update(
            trial_end=timezone.now() - timedelta(seconds=1)
        )

        plan = queries.hub_snapshot(business.id)["plan"]

        assert (
            plan["slug"],
            plan["max_devices"],
            plan["max_users"],
            plan["max_db_connections"],
            plan["statement_timeout_seconds"],
            plan["assistant_messages_per_month"],
            plan["whatsapp_messages_per_month"],
        ) == (
            "free",
            1,
            3,
            1,
            5,
            30,
            30,
        )

    def test_the_members_are_those_who_answered(self, business, team):
        members = queries.hub_snapshot(business.id)["members"]

        assert [(m["email"], m["role"]) for m in members] == [
            ("owner@example.com", "hub_owner"),
            ("admin@example.com", "hub_admin"),
            ("manager@example.com", "hub_manager"),
            ("employee@example.com", "hub_employee"),
        ]
        assert members[0] == {
            "user_id": str(team["owner"].pk),
            "email": "owner@example.com",
            "name": "Olga Owner",
            "role": "hub_owner",
        }

    def test_a_member_without_a_name_is_named_by_email(self, business, team):
        names = {
            m["email"]: m["name"] for m in queries.hub_snapshot(business.id)["members"]
        }

        assert names["admin@example.com"] == "Adela"
        add_member(business, team["stranger"], HubMember.Role.EMPLOYEE)
        names = {
            m["email"]: m["name"] for m in queries.hub_snapshot(business.id)["members"]
        }
        assert names["stranger@example.com"] == "stranger@example.com"

    def test_the_modules_are_the_live_items(self, business):
        subscription = Subscription.objects.get(hub=business)
        until = timezone.now() + timedelta(days=30)
        SubscriptionItem.objects.create(
            subscription=subscription,
            module_slug="inventory",
            source="purchase",
            valid_until=until,
        )
        SubscriptionItem.objects.create(
            subscription=subscription, module_slug="loyalty", source="plan"
        )
        SubscriptionItem.objects.create(
            subscription=subscription,
            module_slug="old",
            source="purchase",
            valid_until=timezone.now() - timedelta(days=1),
        )

        assert queries.hub_snapshot(business.id)["modules"] == [
            {"id": "inventory", "source": "purchase", "valid_until": until.isoformat()},
            {"id": "loyalty", "source": "plan", "valid_until": None},
        ]

    @pytest.mark.parametrize(
        "status, sent",
        [
            ("preparing", "active"),
            ("active", "active"),
            ("past_due", "past_due"),
            ("suspended", "suspended"),
        ],
    )
    def test_the_status_is_the_commercial_one(self, business, status, sent):
        Hub.objects.filter(pk=business.pk).update(status=status)

        assert queries.hub_snapshot(business.id)["status"] == sent


# --- Pushing after the COMMIT ---------------------------------------------------------------------


class TestTheSignUp:
    def test_after_the_commit_the_hub_gets_the_registry_then_the_snapshot(
        self, owner, plans, hub_double, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            hub = create_business(owner)

        assert [(c.method, c.path) for c in hub_double.calls] == [
            ("PUT", f"/internal/hubs/{hub.id}"),
            ("PUT", f"/internal/hubs/{hub.id}/state"),
        ]
        hub = fresh(hub)
        assert (hub.pending_hub_call, hub.pushed_state_version) == (
            "",
            hub.state_version,
        )
        assert hub_double.calls[0].body == queries.hub_registry(hub.id)

    def test_nothing_leaves_before_the_commit(
        self, owner, plans, hub_double, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            create_business(owner)

        assert callbacks and hub_double.calls == []

    def test_with_the_hub_away_the_sign_up_is_kept_and_stays_owed(
        self, owner, plans, offline_hub, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            hub = create_business(owner)

        hub = fresh(hub)
        assert (hub.status, hub.pending_hub_call, hub.pushed_state_version) == (
            "preparing",
            "put",
            0,
        )

    def test_a_hub_that_refuses_the_registry_leaves_it_owed_and_sends_no_snapshot(
        self, owner, plans, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer(
            "PUT",
            r"/internal/hubs/[^/]+$",
            422,
            {"error": {"code": "unknown_vertical"}},
        )

        with django_capture_on_commit_callbacks(execute=True):
            hub = create_business(owner)

        assert fresh(hub).pending_hub_call == "put"
        assert hub_double.calls_to("PUT", "/state") == []


class TestChanges:
    def test_a_new_member_reaches_the_hub_with_a_newer_version(
        self, business, owner, hub_double, make_user
    ):
        services.sync_hub(business.id)
        first = hub_double.calls_to("PUT", "/state")[-1].body["version"]

        add_member(business, make_user("new@example.com"), HubMember.Role.EMPLOYEE)
        services.bump_state(business.id)  # what the member operations do in their transaction
        services.sync_hub(business.id)

        last = hub_double.calls_to("PUT", "/state")[-1].body
        assert last["version"] > first
        assert "new@example.com" in [m["email"] for m in last["members"]]
        assert fresh(business).pushed_state_version == last["version"]

    def test_an_up_to_date_hub_gets_no_snapshot(self, business, hub_double):
        services.sync_hub(business.id)
        sent = len(hub_double.calls)

        services.sync_hub(business.id)

        assert len(hub_double.calls) == sent

    def test_an_acknowledgement_never_moves_the_pushed_version_back(
        self, business, hub_double
    ):
        services.sync_hub(business.id)
        Hub.objects.filter(pk=business.pk).update(
            state_version=9, pushed_state_version=9
        )

        services.record_state_pushed(business.id, 3)

        assert fresh(business).pushed_state_version == 9

    def test_a_registry_owed_during_the_push_is_not_forgotten(
        self, business, hub_double
    ):
        """Cleared only if still the call that was made: a newer one stays owed."""
        services.record_call_answered(business.id, "delete")

        assert fresh(business).pending_hub_call == "put"


class TestDeleteAndRestore:
    def test_the_hub_gets_the_deletion_and_no_snapshot(
        self, business, owner, hub_double, django_capture_on_commit_callbacks
    ):
        services.sync_hub(business.id)
        hub_double.calls.clear()

        with django_capture_on_commit_callbacks(execute=True):
            services.business_delete(
                ctx_for(owner),
                BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo"),
            )

        assert [(c.method, c.path, c.body) for c in hub_double.calls] == [
            ("DELETE", f"/internal/hubs/{business.id}", {"id": str(business.id)})
        ]
        assert fresh(business).pending_hub_call == ""

    def test_the_hub_gets_the_restoration_then_the_free_snapshot(
        self, business, owner, hub_double, django_capture_on_commit_callbacks
    ):
        services.business_delete(
            ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo")
        )
        services.sync_hub(business.id)
        hub_double.calls.clear()

        with django_capture_on_commit_callbacks(execute=True):
            services.business_restore(ctx_for(owner), ByIdIn(id=business.id))

        assert [(c.method, c.path) for c in hub_double.calls] == [
            ("POST", f"/internal/hubs/{business.id}/restore"),
            ("PUT", f"/internal/hubs/{business.id}/state"),
        ]
        assert hub_double.calls[1].body["plan"]["slug"] == "free"
        assert fresh(business).pending_hub_call == ""

    def test_a_business_the_hub_already_purged_is_marked_so(
        self, business, owner, hub_double
    ):
        services.business_delete(
            ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo")
        )
        services.sync_hub(business.id)
        services.business_restore(ctx_for(owner), ByIdIn(id=business.id))
        hub_double.answer(
            "POST",
            "/restore$",
            409,
            {"error": {"code": "hub_purged", "message": "Gone."}},
        )

        services.sync_hub(business.id)

        hub = fresh(business)
        assert (hub.status, hub.pending_hub_call) == ("deleted", "")

    def test_a_deleted_business_gets_no_snapshot(self, business, owner, hub_double):
        Hub.objects.filter(pk=business.pk).update(
            status=Hub.Status.DELETING, pending_hub_call="", state_version=5
        )

        services.sync_hub(business.id)

        assert hub_double.calls == []


def test_revocation_reaches_the_hub_after_the_commit(
    business, team, hub_double, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        services.revoke_after_commit(team["admin"].pk, business.id)

    (call,) = hub_double.calls_to("POST", "/internal/sessions/revoke")
    assert call.body == {"user_id": str(team["admin"].pk), "hub_id": str(business.id)}


def test_a_lost_revocation_breaks_nothing(
    business, team, offline_hub, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        services.revoke_after_commit(team["admin"].pk, business.id)


def test_a_sync_of_an_unknown_business_does_nothing(hub_double):
    import uuid

    assert services.sync_hub(uuid.uuid7()) is False
    assert hub_double.calls == []


def test_a_plan_change_is_a_new_version(business):
    version = fresh(business).state_version
    Subscription.objects.filter(hub=business).update(
        plan=Plan.objects.get(slug="standard")
    )

    services.bump_state(business.id)

    assert fresh(business).state_version == version + 1


# --- Review of L1-A, finding 4: permanent refusals are visible, transient ones stay owed ----------


class TestRefusals:
    def test_a_deletion_the_hub_never_had_is_confirmed(self, business, owner, hub_double):
        services.business_delete(ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo"))
        hub_double.answer("DELETE", r"/internal/hubs/[^/]+$", 404, {"error": {"code": "not_found"}})

        assert services.sync_hub(business.id) is True
        assert fresh(business).pending_hub_call == ""

    def test_restoring_before_the_hub_got_the_deletion_registers_it_again(self, business, owner, hub_double):
        """The Hub never stopped serving it: there is nothing to restore, only the registry to be sure of."""
        services.business_delete(ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo"))

        services.business_restore(ctx_for(owner), ByIdIn(id=business.id))
        assert fresh(business).pending_hub_call == "put"
        services.sync_hub(business.id)

        assert [(c.method, c.path.rsplit("/", 1)[-1]) for c in hub_double.calls] == [
            ("PUT", str(business.id)),
            ("PUT", "state"),
        ]

    def test_a_refused_registry_is_visible_on_the_business(self, business, owner, hub_double):
        hub_double.answer("PUT", r"/internal/hubs/[^/]+$", 422, {"error": {"code": "unknown_vertical", "message": "No."}})

        assert services.sync_hub(business.id) is False

        hub = fresh(business)
        assert (hub.last_hub_error, hub.hub_error_at is not None, hub.pending_hub_call) == ("unknown_vertical", True, "put")
        row = queries.business_list(ctx_for(owner), BusinessListIn()).rows[0]
        assert (row.hub_error, row.open_blocked_reason) == ("unknown_vertical", "error")
        assert queries.business_get(ctx_for(owner), ByIdIn(id=business.id)).hub_error == "unknown_vertical"

    def test_a_later_acknowledgement_clears_the_error(self, business, hub_double):
        Hub.objects.filter(pk=business.pk).update(last_hub_error="unknown_vertical", hub_error_at=timezone.now())

        services.sync_hub(business.id)

        assert (fresh(business).last_hub_error, fresh(business).hub_error_at) == ("", None)

    def test_a_refusal_re_runs_the_owners_lists_at_once(
        self, business, owner, hub_double, monkeypatch, django_capture_on_commit_callbacks
    ):
        """The panel left «Preparing» only at the 300 s safety re-run: the write had no event. Now the
        refusal is recorded by a command, on the owner's channel (as the Hub's ``ready``), and its event
        re-runs the list and the page of the business."""
        from live import operations
        from live.live_registry import live_registry
        from live.models import OutboxEvent

        notified = []
        monkeypatch.setattr(operations, "notify_hook", lambda scope, names: notified.append((scope.key, names)))
        hub_double.answer("PUT", r"/internal/hubs/[^/]+$", 422, {"error": {"code": "unknown_vertical"}})

        with django_capture_on_commit_callbacks(execute=True):
            services.sync_hub(business.id)

        event = OutboxEvent.objects.get(name="hubs.business.hub_error_changed")
        assert (event.scope_kind, event.scope_key, event.actor) == ("user", str(owner.pk), "system")
        assert event.payload == {"id": str(business.id), "hub_error": "unknown_vertical"}
        assert notified == [(str(owner.pk), ["hubs.business.hub_error_changed"])]
        assert {"hubs.business.list", "hubs.business.get"} <= live_registry.affected(notified[0][1])

    def test_clearing_the_refusal_re_runs_them_too(self, business, owner, hub_double):
        from live.models import OutboxEvent

        Hub.objects.filter(pk=business.pk).update(last_hub_error="unknown_vertical", hub_error_at=timezone.now())

        services.sync_hub(business.id)

        (event,) = OutboxEvent.objects.filter(name="hubs.business.hub_error_changed")
        assert (event.scope_key, event.payload) == (str(owner.pk), {"id": str(business.id), "hub_error": None})

    def test_the_same_refusal_again_is_no_news(self, business, hub_double):
        """``reconcile_hub_states`` retries every 15 minutes: an unchanged refusal records nothing more."""
        from live.models import OutboxEvent

        hub_double.answer("PUT", r"/internal/hubs/[^/]+$", 422, {"error": {"code": "unknown_vertical"}})

        services.sync_hub(business.id)
        services.sync_hub(business.id)

        assert OutboxEvent.objects.filter(name="hubs.business.hub_error_changed").count() == 1

    def test_a_push_without_a_refusal_records_nothing(self, business, hub_double):
        from live.models import OutboxEvent

        services.sync_hub(business.id)

        assert not OutboxEvent.objects.filter(name="hubs.business.hub_error_changed").exists()

    def test_only_the_platform_records_the_hubs_answer(self, business, owner):
        from live.errors import PermissionDenied

        from hubs.schemas import HubErrorIn

        with pytest.raises(PermissionDenied):
            services.business_record_hub_error(ctx_for(owner), HubErrorIn(id=business.id, hub_error="nope"))

        assert fresh(business).last_hub_error == ""

    def test_a_hub_that_is_away_is_no_error_of_the_business(self, business, offline_hub):
        services.sync_hub(business.id)

        assert fresh(business).last_hub_error == ""

    def test_a_newer_registry_is_not_dropped_by_an_older_acknowledgement(self, business, owner, hub_double, monkeypatch):
        """The owner renames the business while the Hub answers the previous registry."""
        real = hub_client.put_hub

        def renamed_meanwhile(registry):
            answer = real(registry)
            services.business_update(ctx_for(owner), BusinessUpdateIn(id=business.id, name="Bar Manolo 2"))
            return answer

        monkeypatch.setattr(hub_client, "put_hub", renamed_meanwhile)

        services.sync_hub(business.id)

        assert fresh(business).pending_hub_call == "put"
        monkeypatch.setattr(hub_client, "put_hub", real)
        services.sync_hub(business.id)
        assert hub_double.calls_to("PUT", str(business.id))[-1].body["name"] == "Bar Manolo 2"
        assert fresh(business).pending_hub_call == ""


def test_falling_to_free_the_modules_of_the_paid_plan_leave_the_snapshot(business, owner):
    """Review of L1-A: deleting drops the plan at once; what came with it goes, what was bought stays."""
    subscription = Subscription.objects.get(hub=business)
    SubscriptionItem.objects.create(subscription=subscription, module_slug="loyalty", source="plan")
    SubscriptionItem.objects.create(subscription=subscription, module_slug="inventory", source="purchase")

    services.business_delete(ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo"))

    assert list(SubscriptionItem.objects.values_list("module_slug", flat=True)) == ["inventory"]
    assert [module["id"] for module in queries.hub_snapshot(business.id)["modules"]] == ["inventory"]
