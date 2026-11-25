"""What ``hubs.member.invite`` writes, whom it tells and which refusal goes first.

Who may invite whom is in ``test_members.py``; the seats, in ``test_seats.py``; releasing an account that never proved
its email, in ``test_invite_unverified_account.py``.
"""

import logging
from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from hubs import events
from hubs.models import Hub, HubMember
from hubs.tests.conftest import add_member, create_business, fill_the_free_plan, invite, member_of

pytestmark = pytest.mark.django_db

User = get_user_model()


def expire(member):
    HubMember.objects.filter(pk=member.pk).update(invitation_expires_at=timezone.now() - timedelta(days=1))


def told(name):
    return [(event.scope_key, event.payload) for event in OutboxEvent.objects.filter(name=name)]


class TestANewInvitation:
    def test_it_says_who_invited_whom_as_what_and_when(self, business, owner):
        before = timezone.now()

        invite(owner, business, "new@example.com", "hub_manager", "Bienvenida")

        member = HubMember.objects.get(user__email="new@example.com")
        assert (member.hub, member.role, member.invited_by, member.invitation_message, member.accepted_at) == (
            business,
            "hub_manager",
            owner,
            "Bienvenida",
            None,
        )
        assert before <= member.invited_at <= timezone.now()
        assert member.joined_at == member.invited_at
        assert member.invitation_expires_at - member.invited_at == HubMember.INVITATION_WINDOW

    @pytest.mark.parametrize("language", ["en", "es"])
    def test_the_new_account_speaks_the_business_s_language(self, business, owner, language):
        Hub.objects.filter(pk=business.pk).update(language=language)

        invite(owner, business, "new@example.com")

        assert User.objects.get(email="new@example.com").language == language

    def test_an_account_written_with_capitals_is_the_one_invited(self, business, owner, make_user):
        ana = make_user("ana@example.com")
        User.objects.filter(pk=ana.pk).update(email="Ana@Example.com")

        invite(owner, business, "ana@example.com")

        assert member_of(business, ana).is_pending
        assert User.objects.filter(email__iexact="ana@example.com").count() == 1

    def test_somebody_on_another_business_is_new_here(self, business, owner, make_user):
        ana = make_user("ana@example.com")
        add_member(create_business(make_user("lola@example.com"), name="Café Lola"), ana, HubMember.Role.EMPLOYEE)

        assert invite(owner, business, "ana@example.com").status == "pending"
        assert member_of(business, ana).is_pending

    def test_the_business_is_told_of_it_once(self, business, owner):
        row = invite(owner, business, "new@example.com")

        assert told(events.MEMBER_INVITED) == [
            (str(owner.pk), {"id": str(row.id), "hub_id": str(business.id)}),
        ]

    def test_the_invitee_sees_it_at_once_and_the_one_who_invited_is_not_told_twice(self, business, owner, make_user):
        ana = make_user("ana@example.com")

        invite(owner, business, "ana@example.com")

        assert [scope for scope, _ in told(events.MEMBER_CHANGED)] == [str(ana.pk)]

    def test_a_released_account_says_why_in_the_log(self, business, owner, caplog):
        squatter = User.objects.create_user(email="ana@example.com", password="Squatt3r-pass-phrase")
        EmailAddress.objects.create(user=squatter, email=squatter.email, primary=True, verified=False)

        with caplog.at_level(logging.WARNING, logger="accounts.services.mailbox_proof"):
            invite(owner, business, "ana@example.com")

        assert [record.getMessage() for record in caplog.records] == [
            f"accounts.released_unproven_account user={squatter.pk} reason=invited_while_unverified"
        ]


class TestAnExpiredInvitation:
    def test_it_takes_the_new_role_message_and_who_invites_now(self, business, team):
        before = timezone.now()
        expire(member_of(business, team["invitee"]))

        row = invite(team["admin"], business, "invitee@example.com", "hub_manager", "Te esperamos")

        member = member_of(business, team["invitee"])
        assert (member.role, member.invitation_message, member.invited_by) == (
            "hub_manager",
            "Te esperamos",
            team["admin"],
        )
        assert before <= member.invited_at <= timezone.now()
        assert member.invitation_expires_at - member.invited_at == HubMember.INVITATION_WINDOW
        assert (row.id, row.role, row.status, row.invited_by) == (member.id, "hub_manager", "pending", "Adela")

    def test_without_a_message_the_old_one_goes(self, business, team):
        member = member_of(business, team["invitee"])
        HubMember.objects.filter(pk=member.pk).update(invitation_message="Antes")
        expire(member)

        invite(team["owner"], business, "invitee@example.com")

        assert member_of(business, team["invitee"]).invitation_message == ""

    def test_an_address_written_with_capitals_is_the_same_invitation(self, business, team):
        User.objects.filter(pk=team["invitee"].pk).update(email="Invitee@Example.com")
        expire(member_of(business, team["invitee"]))

        invite(team["owner"], business, "invitee@example.com")

        assert HubMember.objects.filter(hub=business, user=team["invitee"]).count() == 1
        assert member_of(business, team["invitee"]).invitation_expires_at > timezone.now()

    def test_it_is_told_and_mailed_as_a_new_one(self, business, team, django_capture_on_commit_callbacks):
        member = member_of(business, team["invitee"])
        expire(member)

        with django_capture_on_commit_callbacks(execute=True):
            invite(team["owner"], business, "invitee@example.com")

        assert told(events.MEMBER_INVITED) == [
            (str(team["owner"].pk), {"id": str(member.id), "hub_id": str(business.id)}),
        ]
        assert {scope for scope, _ in told(events.MEMBER_CHANGED)} == {
            str(team["admin"].pk),
            str(team["invitee"].pk),
        }
        assert [message.to for message in mail.outbox] == [["invitee@example.com"]]

    def test_its_password_is_left_alone(self, business, owner):
        """Renewing releases nobody: that was done, or not needed, when the invitation was made."""
        ana = User.objects.create_user(email="ana@example.com", password="Known-pass-phrase")
        invite(owner, business, "ana@example.com")
        EmailAddress.objects.create(user=ana, email=ana.email, primary=True, verified=False)
        expire(member_of(business, ana))

        invite(owner, business, "ana@example.com")

        assert User.objects.get(pk=ana.pk).check_password("Known-pass-phrase")

    def test_a_peers_is_not_renewed(self, business, team, make_user):
        peer = make_user("peer@example.com")
        add_member(business, peer, HubMember.Role.ADMIN, invited_by=team["owner"], accepted=False)
        expire(member_of(business, peer))

        with pytest.raises(PermissionDenied) as refused:
            invite(team["admin"], business, "peer@example.com", "hub_employee")

        assert str(refused.value) == "You cannot manage a member whose role is equal to or above yours."
        assert member_of(business, peer).is_expired(timezone.now())


class TestWhichRefusalGoesFirst:
    def test_somebody_inside_is_named(self, business, team):
        with pytest.raises(Conflict) as refused:
            invite(team["owner"], business, "employee@example.com")

        assert str(refused.value) == "employee@example.com is already on this business."

    def test_an_invitation_waiting_is_named(self, business, team):
        with pytest.raises(Conflict) as refused:
            invite(team["owner"], business, "invitee@example.com")

        assert str(refused.value) == "invitee@example.com already has an invitation waiting. Resend it instead."

    def test_somebody_inside_goes_before_their_rank(self, business, team):
        with pytest.raises(Conflict) as refused:
            invite(team["admin"], business, "owner@example.com")

        assert refused.value.code == "hubs.already_member"

    @pytest.mark.parametrize("who", ["manager", "employee"])
    def test_below_admin_the_refusal_is_the_rank_s_also_on_a_deleted_business(self, business, team, who):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(PermissionDenied) as refused:
            invite(team[who], business, "new@example.com")

        assert str(refused.value) == "Your role in this business does not allow it."

    def test_a_deleted_business_goes_before_the_role(self, business, team):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(Conflict) as refused:
            invite(team["admin"], business, "new@example.com", "hub_admin")

        assert refused.value.code == "hubs.business_deleted"

    def test_the_role_goes_before_somebody_inside(self, business, team):
        with pytest.raises(PermissionDenied) as refused:
            invite(team["admin"], business, "employee@example.com", "hub_admin")

        assert str(refused.value) == "You cannot hand out a role equal to or above yours."

    def test_a_business_gone_for_good_does_not_exist(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

        with pytest.raises(NotFound):
            invite(owner, business, "new@example.com")

    def test_renewing_the_staff_s_goes_before_its_seat(self, business, owner, make_user):
        ana = make_user("ana@example.com")
        add_member(business, ana, HubMember.Role.EMPLOYEE, accepted=False)
        expire(member_of(business, ana))
        fill_the_free_plan(business, owner)
        User.objects.filter(pk=ana.pk).update(is_staff=True)

        with pytest.raises(Conflict) as refused:
            invite(owner, business, "ana@example.com")

        assert refused.value.code == "hubs.platform_account"

    def test_a_peers_expired_invitation_goes_before_the_staff(self, business, team, make_user):
        peer = make_user("peer@example.com", is_staff=True)
        add_member(business, peer, HubMember.Role.ADMIN, invited_by=team["owner"], accepted=False)
        expire(member_of(business, peer))

        with pytest.raises(PermissionDenied):
            invite(team["admin"], business, "peer@example.com")

    def test_a_seat_for_somebody_new_goes_before_the_staff(self, business, owner, make_user):
        make_user("root@example.com", is_staff=True)
        fill_the_free_plan(business, owner)

        with pytest.raises(Conflict) as refused:
            invite(owner, business, "root@example.com")

        assert refused.value.code == "hubs.seat_limit"

    def test_the_staff_is_refused_before_its_account_is_touched(self, business, owner, caplog):
        staff = User.objects.create_user(email="root@example.com", password="Known-pass-phrase", is_staff=True)
        EmailAddress.objects.create(user=staff, email=staff.email, primary=True, verified=False)

        with caplog.at_level(logging.WARNING, logger="accounts.services.mailbox_proof"), pytest.raises(Conflict):
            invite(owner, business, "root@example.com")

        assert caplog.records == []
        assert User.objects.get(pk=staff.pk).check_password("Known-pass-phrase")


class TestItsLocks:
    def locked(self, queries):
        return [
            table
            for query in queries
            if " FOR UPDATE" in query["sql"]
            for table in ('"hubs_hub"', '"hubs_hubmember"')
            if f"FROM {table}" in query["sql"]
        ]

    @pytest.mark.parametrize("who", ["new", "invitee"])
    def test_the_business_first_then_the_member(self, business, team, who):
        """Two managers inviting the same address at once never make two invitations of it."""
        expire(member_of(business, team["invitee"]))

        with CaptureQueriesContext(connection) as seen:
            invite(team["owner"], business, f"{who}@example.com")

        assert self.locked(seen.captured_queries) == ['"hubs_hub"', '"hubs_hubmember"']

    def test_the_renewed_member_s_business_is_not_read_again(
        self, business, team, django_capture_on_commit_callbacks
    ):
        expire(member_of(business, team["invitee"]))

        with CaptureQueriesContext(connection) as seen, django_capture_on_commit_callbacks(execute=True):
            invite(team["owner"], business, "invitee@example.com")

        assert len([query for query in seen.captured_queries if 'FROM "hubs_hub" WHERE' in query["sql"]]) == 1
