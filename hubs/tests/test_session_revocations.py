"""``SessionRevocation``: the Hub ends an account's sessions, and a Hub that is away does not lose it
(PLAN-SAAS §2.1, the back-channel logout; plan 2026-10-13 §3 and L1-A2).

Taking access away (removing a member, changing a role, handing the ownership over) queues a revocation
in the same transaction; it is delivered after the COMMIT (``POST /internal/sessions/revoke``) and, while
the Hub is away or refuses it, ``reconcile_hub_states`` retries it with a growing wait. Delivered once.
The next snapshot no longer lists a removed member either (the Hub's second way of learning it).
"""

import re
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from hubs import services
from hubs.models import Hub, HubMember, SessionRevocation
from hubs.schemas import ByIdIn, MemberRoleIn, OwnershipTransferIn
from hubs.tests.conftest import ctx_for, member_of

pytestmark = pytest.mark.django_db

REVOKE = "/internal/sessions/revoke"


def remove(actor, hub, user):
    return services.member_remove(ctx_for(actor), ByIdIn(id=member_of(hub, user).id))


def reconcile():
    out = StringIO()
    call_command("reconcile_hub_states", stdout=out)
    return out.getvalue()


def count(output: str, key: str) -> int:
    return int(re.search(rf"\b{key}=(\d+)", output)[1])


def due_now():
    """Every queued revocation is due (as if its wait had passed)."""
    SessionRevocation.objects.update(
        next_attempt_at=timezone.now() - timedelta(seconds=1)
    )


class TestQueued:
    def test_removing_a_member_queues_its_revocation_in_the_same_transaction(
        self, business, team
    ):
        remove(team["owner"], business, team["employee"])

        (revocation,) = SessionRevocation.objects.all()
        assert (revocation.user_id, revocation.hub_id) == (
            team["employee"].pk,
            business.pk,
        )
        assert (
            revocation.delivered_at,
            revocation.attempts,
            revocation.last_error,
        ) == (None, 0, "")
        assert revocation.requested_at <= timezone.now()

    def test_changing_the_role_of_a_member_queues_it(self, business, team):
        """The role travels in the Hub's session (``/internal/auth/redeem``): it must sign in again."""
        services.member_change_role(
            ctx_for(team["owner"]),
            MemberRoleIn(
                id=member_of(business, team["manager"]).id, role="hub_employee"
            ),
        )

        assert list(SessionRevocation.objects.values_list("user_id", "hub_id")) == [
            (team["manager"].pk, business.pk)
        ]

    def test_an_invitation_has_no_session_to_end(self, business, team):
        services.member_change_role(
            ctx_for(team["owner"]),
            MemberRoleIn(
                id=member_of(business, team["invitee"]).id, role="hub_manager"
            ),
        )

        assert not SessionRevocation.objects.exists()

    def test_the_same_role_again_ends_nothing(self, business, team):
        services.member_change_role(
            ctx_for(team["owner"]),
            MemberRoleIn(
                id=member_of(business, team["manager"]).id, role="hub_manager"
            ),
        )

        assert not SessionRevocation.objects.exists()

    def test_an_ownership_hand_over_ends_the_sessions_of_both_sides(
        self, business, team
    ):
        offer = services.ownership_transfer(
            ctx_for(team["owner"]),
            OwnershipTransferIn(
                hub_id=business.id, member_id=member_of(business, team["admin"]).id
            ),
        )

        services.ownership_accept(ctx_for(team["admin"]), ByIdIn(id=offer.id))

        assert set(SessionRevocation.objects.values_list("user_id", "hub_id")) == {
            (team["owner"].pk, business.pk),
            (team["admin"].pk, business.pk),
        }

    def test_a_refused_write_queues_nothing(self, business, team):
        from live.errors import PermissionDenied

        with pytest.raises(PermissionDenied):
            remove(team["manager"], business, team["employee"])

        assert not SessionRevocation.objects.exists()


class TestDelivered:
    def test_it_reaches_the_hub_after_the_commit_and_is_marked_delivered(
        self, business, team, hub_double, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            remove(team["owner"], business, team["employee"])

        (call,) = hub_double.calls_to("POST", REVOKE)
        assert call.body == {
            "user_id": str(team["employee"].pk),
            "hub_id": str(business.id),
        }
        revocation = SessionRevocation.objects.get()
        assert revocation.delivered_at is not None
        assert (revocation.attempts, revocation.last_error) == (1, "")

    def test_a_revocation_of_every_business_carries_no_hub(
        self, team, hub_double, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            services.revoke_after_commit(team["admin"].pk)

        (call,) = hub_double.calls_to("POST", REVOKE)
        assert call.body == {"user_id": str(team["admin"].pk)}
        assert SessionRevocation.objects.get().hub_id is None

    def test_with_the_hub_away_it_stays_queued_with_its_error_and_a_wait(
        self, business, team, offline_hub, django_capture_on_commit_callbacks
    ):
        before = timezone.now()
        with django_capture_on_commit_callbacks(execute=True):
            remove(team["owner"], business, team["employee"])

        revocation = SessionRevocation.objects.get()
        assert revocation.delivered_at is None
        assert revocation.attempts == 1
        assert revocation.last_error
        assert revocation.next_attempt_at >= before + services.revocation_backoff(1)

    def test_a_refusal_of_the_hub_is_recorded_and_retried_too(
        self, business, team, hub_double, django_capture_on_commit_callbacks
    ):
        hub_double.answer(
            "POST",
            f"^{REVOKE}$",
            400,
            {"error": {"code": "invalid_request", "message": "No."}},
        )

        with django_capture_on_commit_callbacks(execute=True):
            remove(team["owner"], business, team["employee"])

        revocation = SessionRevocation.objects.get()
        assert (revocation.delivered_at, revocation.attempts) == (None, 1)
        assert "invalid_request" in revocation.last_error

    def test_the_revocation_outlives_the_account_it_ends(
        self, business, team, hub_double
    ):
        """Deleting an account ends its sessions everywhere: the row keeps the account's id."""
        employee_id = team["employee"].pk
        remove(team["owner"], business, team["employee"])
        get_user_model().objects.filter(pk=employee_id).delete()
        due_now()

        reconcile()

        (call,) = hub_double.calls_to("POST", REVOKE)
        assert call.body["user_id"] == str(employee_id)
        assert SessionRevocation.objects.get().delivered_at is not None

    def test_a_purged_business_has_no_session_left_to_end(
        self, business, team, hub_double
    ):
        remove(team["owner"], business, team["employee"])
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)
        due_now()

        reconcile()

        assert hub_double.calls_to("POST", REVOKE) == []
        assert SessionRevocation.objects.get().delivered_at is not None


class TestRetried:
    def test_the_hub_down_then_up_gets_it_exactly_once(
        self, business, team, offline_hub, settings, django_capture_on_commit_callbacks
    ):
        from hubs.tests.conftest import SECRET
        from hubs.tests.hub_double import HubDouble

        with django_capture_on_commit_callbacks(execute=True):
            remove(team["owner"], business, team["employee"])
        assert SessionRevocation.objects.get().delivered_at is None

        settings.INTERNAL_SHARED_SECRET = SECRET
        double = HubDouble(SECRET).start()
        settings.HUB_INTERNAL_URL = double.url
        try:
            due_now()
            first = reconcile()
            second = reconcile()
        finally:
            double.stop()

        (call,) = double.calls_to("POST", REVOKE)
        assert call.body == {
            "user_id": str(team["employee"].pk),
            "hub_id": str(business.id),
        }
        assert (count(first, "sessions_ended"), count(second, "sessions_ended")) == (
            1,
            0,
        )
        revocation = SessionRevocation.objects.get()
        assert revocation.delivered_at is not None
        assert revocation.attempts == 2
        # The snapshot the Hub got no longer lists the removed member.
        (snapshot,) = double.calls_to("PUT", "/state")
        assert str(team["employee"].pk) not in {
            member["user_id"] for member in snapshot.body["members"]
        }

    def test_one_still_waiting_is_not_retried_yet(self, business, team, hub_double):
        remove(team["owner"], business, team["employee"])
        SessionRevocation.objects.update(
            attempts=1, next_attempt_at=timezone.now() + timedelta(minutes=10)
        )

        output = reconcile()

        assert hub_double.calls_to("POST", REVOKE) == []
        assert (count(output, "sessions_ended"), count(output, "sessions_pending")) == (
            0,
            0,
        )

    def test_a_retry_that_fails_again_waits_longer_and_fails_the_run(
        self, business, team, offline_hub
    ):
        remove(team["owner"], business, team["employee"])
        SessionRevocation.objects.update(
            attempts=1, next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        before = timezone.now()

        with pytest.raises(CommandError) as failed:
            reconcile()

        assert count(str(failed.value), "sessions_pending") == 1
        revocation = SessionRevocation.objects.get()
        assert revocation.attempts == 2
        assert revocation.next_attempt_at >= before + services.revocation_backoff(2)

    @pytest.mark.parametrize(
        ("attempts", "wait"),
        [
            (1, timedelta(minutes=15)),
            (2, timedelta(minutes=30)),
            (3, timedelta(hours=1)),
            (10, timedelta(hours=6)),
        ],
    )
    def test_the_wait_doubles_up_to_six_hours(self, attempts, wait):
        assert services.revocation_backoff(attempts) == wait
