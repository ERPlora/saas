"""Deleting and recovering a business, ``hubs.business.{delete,restore}``: deleting keeps the record,
recoverable for 90 days, and the owner is told the date; every change of the snapshot moves its version
forward.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone, translation
from live.errors import Conflict, InvalidPayload, PermissionDenied

from hubs import queries, services
from hubs.models import Hub, Plan, Subscription
from hubs.schemas.businesses import BusinessDeleteIn
from hubs.schemas.common import ByIdIn
from hubs.tests.conftest import ctx_for, role_on

pytestmark = pytest.mark.django_db


# --- Deleting and recovering ----------------------------------------------------------------------


class TestDelete:
    def delete(self, user, hub, name="Bar Manolo"):
        return services.deletion.business_delete(
            ctx_for(user), BusinessDeleteIn(id=hub.id, confirm_name=name)
        )

    def test_the_owner_deletes_it_and_the_record_stays(self, business, owner):
        deleted = self.delete(owner, business)
        business.refresh_from_db()

        assert (business.status, deleted.status) == ("deleting", "deleting")
        assert business.deletion_requested_at is not None
        assert deleted.purge_after == business.deletion_requested_at + timedelta(
            days=90
        )

    def test_the_hub_owes_the_deletion(self, business, owner):
        self.delete(owner, business)
        business.refresh_from_db()

        assert business.pending_hub_call == "delete"

    def test_nobody_enters_a_deleted_business(self, business, team):
        self.delete(team["owner"], business)

        assert queries.membership.hubs_with_members() == []

    def test_the_name_must_be_typed_again(self, business, owner):
        with pytest.raises(InvalidPayload) as refused:
            self.delete(owner, business, name="Bar")

        assert set(refused.value.fields) == {"confirm_name"}
        # The dialog has its own box and marks nothing: the reason itself is the notice.
        assert refused.value.message == refused.value.fields["confirm_name"]
        business.refresh_from_db()
        assert business.status == "preparing"

    def test_the_name_is_compared_without_case_nor_outer_spaces(self, business, owner):
        assert self.delete(owner, business, name="  bar manolo ").status == "deleting"

    @pytest.mark.parametrize("who", ["admin", "manager", "employee"])
    def test_only_the_owner_deletes(self, business, team, who):
        with pytest.raises(PermissionDenied):
            self.delete(team[who], business)

    def test_deleting_twice_is_a_conflict(self, business, owner):
        self.delete(owner, business)

        with pytest.raises(Conflict) as refused:
            self.delete(owner, business)

        assert refused.value.code == "hubs.business_deleted"

    def test_the_owner_is_told_until_when_it_can_be_recovered(
        self, business, owner, django_capture_on_commit_callbacks, offline_hub
    ):
        with django_capture_on_commit_callbacks(execute=True):
            self.delete(owner, business)
        business.refresh_from_db()

        (message,) = mail.outbox
        assert message.to == ["owner@example.com"]
        with translation.override("es"):
            from django.utils.formats import date_format

            purge = date_format(timezone.localtime(business.purge_after), "DATE_FORMAT")
        assert "Bar Manolo" in message.subject
        assert purge in message.body
        # The account reads Spanish.
        assert "recuperar" in message.body.lower()

    # The deletion mail asks the Hub first whether a copy will come.
    COPY_LINE = "Descarga una copia completa de sus datos"

    def test_the_mail_leads_to_the_copy_when_the_hub_will_make_one(
        self, business, owner, django_capture_on_commit_callbacks, hub_double
    ):
        hub_double.dumps[str(business.id)] = []

        with django_capture_on_commit_callbacks(execute=True):
            self.delete(owner, business)

        (message,) = mail.outbox
        assert f"{self.COPY_LINE}: " in message.body
        assert hub_double.calls_to("GET", f"/internal/hubs/{business.id}/dumps")

    def test_the_mail_promises_no_copy_of_a_business_without_its_own_database(
        self, business, owner, django_capture_on_commit_callbacks, hub_double
    ):
        hub_double.dumps[str(business.id)] = []
        hub_double.without_copies.add(str(business.id))

        with django_capture_on_commit_callbacks(execute=True):
            self.delete(owner, business)

        (message,) = mail.outbox
        assert self.COPY_LINE not in message.body
        assert "recuperar" in message.body.lower()

    @pytest.mark.parametrize("hub", ["away", "refusing"])
    def test_with_the_hub_away_the_mail_still_leads_to_the_copy(
        self, business, owner, django_capture_on_commit_callbacks, hub_double, settings, hub
    ):
        """The page promises nothing it cannot keep, so the mail keeps the way to it when the Hub cannot say."""
        if hub == "away":
            settings.HUB_INTERNAL_URL = "http://127.0.0.1:9"
        else:
            hub_double.answer("GET", r"/dumps$", 403, {"error": {"code": "forbidden"}})

        with django_capture_on_commit_callbacks(execute=True):
            self.delete(owner, business)

        (message,) = mail.outbox
        assert f"{self.COPY_LINE}: " in message.body

    def test_deleting_cancels_the_plan_at_once(self, business, owner, plans):
        """It comes back on Free."""
        Subscription.objects.filter(hub=business).update(
            plan=Plan.objects.get(slug="standard"), trial_plan=None, status="active"
        )

        self.delete(owner, business)

        subscription = Subscription.objects.get(hub=business)
        assert (
            subscription.plan.slug,
            subscription.trial_plan,
            subscription.status,
        ) == ("free", None, "active")


class TestRestore:
    def deleted(self, business, owner, days_ago=1):
        services.deletion.business_delete(
            ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name)
        )
        Hub.objects.filter(pk=business.pk).update(
            deletion_requested_at=timezone.now() - timedelta(days=days_ago),
            pending_hub_call="",
        )
        return business

    def test_within_ninety_days_the_owner_gets_it_back(self, business, owner):
        self.deleted(business, owner)
        version = Hub.objects.get(pk=business.pk).state_version

        restored = services.deletion.business_restore(ctx_for(owner), ByIdIn(id=business.id))
        business.refresh_from_db()

        assert (restored.status, business.status, business.deletion_requested_at) == (
            "preparing",
            "preparing",
            None,
        )
        assert business.pending_hub_call == "restore"
        assert business.state_version == version + 1
        assert role_on(owner, business.slug) == "hub_owner"

    def test_a_business_that_was_ready_comes_back_active(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(
            ready_at=timezone.now(), status=Hub.Status.ACTIVE
        )
        self.deleted(business, owner)

        assert (
            services.deletion.business_restore(ctx_for(owner), ByIdIn(id=business.id)).status
            == "active"
        )

    def test_after_ninety_days_it_is_gone(self, business, owner):
        self.deleted(business, owner, days_ago=90)

        with pytest.raises(Conflict) as refused:
            services.deletion.business_restore(ctx_for(owner), ByIdIn(id=business.id))

        assert refused.value.code == "hubs.business_purged"

    def test_a_business_that_is_not_deleted_is_not_restored(self, business, owner):
        with pytest.raises(Conflict) as refused:
            services.deletion.business_restore(ctx_for(owner), ByIdIn(id=business.id))

        assert refused.value.code == "hubs.business_not_deleted"

    def test_only_the_owner_restores(self, business, team):
        self.deleted(business, team["owner"])

        with pytest.raises(PermissionDenied):
            services.deletion.business_restore(ctx_for(team["admin"]), ByIdIn(id=business.id))


# --- The state version ----------------------------------------------------------------------------


def test_every_change_of_the_snapshot_moves_the_version_forward(business, team, plans):
    """The Hub ignores an older snapshot: ours must grow with every change it carries."""
    versions = [Hub.objects.get(pk=business.pk).state_version]
    services.hub_push.bump_state(business.id)
    versions.append(Hub.objects.get(pk=business.pk).state_version)
    services.deletion.business_delete(
        ctx_for(team["owner"]),
        BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo"),
    )
    services.deletion.business_restore(ctx_for(team["owner"]), ByIdIn(id=business.id))
    versions.append(Hub.objects.get(pk=business.pk).state_version)

    assert versions == sorted(set(versions))
