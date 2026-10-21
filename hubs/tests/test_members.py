"""Members and invitations of a business: ``hubs.member.{list,invite,change_role,remove,resend,cancel}``
and ``hubs.invitation.{list_mine,accept,decline}`` (plan 2026-10-13, L1-A and L1-B; round 17 §2.7–2.8).

Cases ported from ERPlora/saas (origin/develop), from services, views and DRF to operations, on the four
``hub_*`` roles of round 11 instead of owner/admin/member: ``hubs/main/tests/`` ``test_member_service``
(per-hub writes, the hierarchy: nobody acts on a peer or a superior, nor on themselves, nor grants
their own rank), ``test_hub_member_access``, ``test_members_invite_permission`` and
``test_members_role_escalation`` (a role below admin manages nobody; a re-invite is no free pass; an
owner elsewhere is a stranger here), ``test_invitation_accept`` (only the caller's own pending row is
stamped; nothing is ever granted by a poked id, a replay, a cancelled or a stale invitation; accepting
never changes the role), ``test_account_roles``; ``dashboard/users/tests/`` ``test_account_role_choices``
(least privilege by default, owner is never grantable), ``test_members_per_hub``,
``test_pending_invitation_status`` and ``test_remove_user``. Their HTTP halves and the row actions
(``test_users_row_actions``, ``test_users_list_shows_self``) are in ``test_members_api.py``; the seats
(``test_hub_seat_limit``), in ``test_seats.py``. New: the invitation expires after 7 days, «Resend»
renews it and «Decline» deletes the row. Dropped with their reason: the machine credential and the
hub's mirror door (no runtime pushes members up any more), retired role keys (the four roles are new),
htmx fragments and pages (SPA), and ``test_invite_unverified_account`` (releasing an unproven account
belongs to ``accounts``, L1-A2).
"""

from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied

from accounts.models import HubMembership
from hubs import queries, services
from hubs.models import Hub, HubMember
from hubs.schemas import (
    ByIdIn,
    InvitationListIn,
    MemberInviteIn,
    MemberListIn,
    MemberRoleIn,
)
from hubs.tests.conftest import add_member, create_business, ctx_for, member_of

pytestmark = pytest.mark.django_db

User = get_user_model()


def invite(actor, hub, email, role="hub_employee", message=""):
    return services.member_invite(
        ctx_for(actor),
        MemberInviteIn(hub_id=hub.id, email=email, role=role, message=message),
    )


def members(actor, hub, **params):
    return queries.member_list(
        ctx_for(actor), MemberListIn(hub_id=hub.id, **params)
    ).model_dump(mode="json")


def version(hub):
    return Hub.objects.get(pk=hub.pk).state_version


# --- Inviting -------------------------------------------------------------------------------------


class TestInvite:
    def test_an_invitation_is_a_member_without_an_answer(
        self, business, owner, make_user
    ):
        ana = make_user("ana@example.com")

        row = invite(owner, business, "ana@example.com", "hub_manager")

        member = member_of(business, ana)
        assert (member.role, member.invited_by, member.accepted_at) == (
            "hub_manager",
            owner,
            None,
        )
        assert member.invitation_expires_at - member.invited_at == timedelta(days=7)
        assert (row.status, row.email, row.role) == (
            "pending",
            "ana@example.com",
            "hub_manager",
        )

    def test_the_least_privilege_by_default(self, business, owner):
        assert (
            services.member_invite(
                ctx_for(owner),
                MemberInviteIn(hub_id=business.id, email="x@example.com"),
            ).role
            == "hub_employee"
        )

    def test_the_owner_is_never_handed_out_by_an_invitation(self, business):
        with pytest.raises(Exception) as refused:
            MemberInviteIn(hub_id=business.id, email="x@example.com", role="hub_owner")

        assert "role" in str(refused.value)

    def test_an_address_without_an_account_gets_one_to_claim(self, business, owner):
        invite(owner, business, "  New.Person@Example.com ")

        user = User.objects.get(email="new.person@example.com")
        assert (user.is_active, user.has_usable_password(), user.is_staff) == (
            True,
            False,
            False,
        )
        assert member_of(business, user).is_pending

    def test_the_mail_leaves_after_the_commit(
        self, business, owner, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            invite(owner, business, "ana@example.com", message="Bienvenida")
        assert mail.outbox == []

        for callback in callbacks:
            callback()

        (message,) = mail.outbox
        assert message.to == ["ana@example.com"]
        assert "Bienvenida" in message.body
        assert "/password/reset" in message.body  # a new account: how to get in

    def test_an_invitation_reaches_the_hub_only_once_answered(self, business, owner):
        before = version(business)

        invite(owner, business, "ana@example.com")

        assert version(business) == before
        assert not HubMembership.objects.filter(user__email="ana@example.com").exists()

    def test_somebody_already_on_the_business_is_a_conflict(self, business, team):
        with pytest.raises(Conflict) as refused:
            invite(team["owner"], business, "employee@example.com", "hub_manager")

        assert refused.value.code == "hubs.already_member"

    def test_a_pending_invitation_is_resent_not_duplicated(self, business, team):
        with pytest.raises(Conflict) as refused:
            invite(team["owner"], business, "invitee@example.com")

        assert refused.value.code == "hubs.already_invited"

    def test_an_expired_invitation_is_renewed_by_inviting_again(self, business, team):
        HubMember.objects.filter(user=team["invitee"]).update(
            invitation_expires_at=timezone.now() - timedelta(days=1)
        )

        row = invite(team["owner"], business, "invitee@example.com", "hub_manager")

        member = member_of(business, team["invitee"])
        assert (row.status, member.role) == ("pending", "hub_manager")
        assert member.invitation_expires_at > timezone.now() + timedelta(days=6)
        assert HubMember.objects.filter(hub=business, user=team["invitee"]).count() == 1

    def test_an_admin_invites_managers_and_employees(self, business, team):
        assert (
            invite(team["admin"], business, "m@example.com", "hub_manager").role
            == "hub_manager"
        )
        assert (
            invite(team["admin"], business, "e@example.com", "hub_employee").role
            == "hub_employee"
        )

    def test_an_admin_cannot_hand_out_admin(self, business, team):
        with pytest.raises(PermissionDenied):
            invite(team["admin"], business, "a@example.com", "hub_admin")

    def test_the_owner_hands_out_admin(self, business, owner):
        assert invite(owner, business, "a@example.com", "hub_admin").role == "hub_admin"

    @pytest.mark.parametrize("who", ["manager", "employee"])
    def test_a_manager_or_an_employee_invites_nobody(self, business, team, who):
        with pytest.raises(PermissionDenied):
            invite(team[who], business, "x@example.com")

        assert not User.objects.filter(email="x@example.com").exists()

    @pytest.mark.parametrize("who", ["stranger", "invitee"])
    def test_without_access_the_business_does_not_exist(self, business, team, who):
        with pytest.raises(NotFound):
            invite(team[who], business, "x@example.com")

    def test_a_deleted_business_takes_nobody(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(Conflict) as refused:
            invite(owner, business, "x@example.com")

        assert refused.value.code == "hubs.business_deleted"

    @pytest.mark.parametrize("target", ["admin", "owner"])
    def test_re_inviting_somebody_inside_changes_nothing(self, business, team, target):
        """test_members_role_escalation (same-role re-provisioning is no free pass) and test_member_service
        (a re-invite with another role used to move the role in place): an invitation never touches
        somebody who answered, a peer, a superior or oneself; a role moves only by «Change role»."""
        with pytest.raises(Conflict) as refused:
            invite(team["admin"], business, f"{target}@example.com", "hub_employee")

        assert refused.value.code == "hubs.already_member"
        assert member_of(business, team[target]).role == f"hub_{target}"

    def test_the_owner_of_another_business_is_a_stranger_here(self, business, team, make_user):
        """test_members_role_escalation: authority stops at one's own business (ADR-0201)."""
        lola = make_user("lola@example.com")
        create_business(lola, name="Café Lola")

        with pytest.raises(NotFound):
            invite(lola, business, "x@example.com")

        assert not User.objects.filter(email="x@example.com").exists()

    @pytest.mark.parametrize(
        "written",
        ["Ana.Lopez@EXAMPLE.com", "ana.lopez@ｅｘａｍｐｌｅ.com", "ａｎａ.lopez@example.com"],
        ids=["other-capitals", "fullwidth-after-the-at", "fullwidth-before-the-at"],
    )
    def test_an_accounts_address_in_another_form_invites_that_account_and_it_accepts(
        self, business, owner, make_user, written
    ):
        """saas#2562 (ACCOUNTS-F01): an address is the account's in its plain form, folded as
        ``accounts.adapters.plain_email`` folds it (NFKC, trimmed, lower case), so another case or look-alike
        full-width letters never make a second account that looks the same and never gets the access."""
        ana = make_user("ana.lopez@example.com")
        EmailAddress.objects.create(user=ana, email=ana.email, verified=True, primary=True)

        invite(owner, business, written)
        services.invitation_accept(ctx_for(ana), ByIdIn(id=member_of(business, ana).id))

        assert list(User.objects.exclude(pk=owner.pk).values_list("email", flat=True)) == ["ana.lopez@example.com"]
        assert member_of(business, ana).accepted_at is not None
        assert HubMembership.objects.filter(user=ana, hub_slug=business.slug).exists()


# --- Changing a role ------------------------------------------------------------------------------


class TestChangeRole:
    def change(self, actor, member, role):
        return services.member_change_role(
            ctx_for(actor), MemberRoleIn(id=member.id, role=role)
        )

    def test_the_owner_promotes_an_employee_and_the_hub_learns_it(self, business, team):
        before = version(business)
        employee = member_of(business, team["employee"])

        assert self.change(team["owner"], employee, "hub_admin").role == "hub_admin"
        assert member_of(business, team["employee"]).role == "hub_admin"
        assert version(business) == before + 1
        assert (
            HubMembership.objects.get(
                user=team["employee"], hub_slug=business.slug
            ).role
            == "hub_admin"
        )

    def test_an_admin_moves_an_employee_to_manager(self, business, team):
        assert (
            self.change(
                team["admin"], member_of(business, team["employee"]), "hub_manager"
            ).role
            == "hub_manager"
        )

    def test_an_admin_cannot_grant_admin(self, business, team):
        with pytest.raises(PermissionDenied):
            self.change(
                team["admin"], member_of(business, team["employee"]), "hub_admin"
            )

    @pytest.mark.parametrize("target", ["owner", "admin"])
    def test_an_admin_touches_no_peer_nor_superior(
        self, business, team, make_user, target
    ):
        if target == "admin":
            add_member(business, make_user("admin2@example.com"), HubMember.Role.ADMIN)
            row = HubMember.objects.get(user__email="admin2@example.com")
        else:
            row = member_of(business, team["owner"])
        with pytest.raises(PermissionDenied):
            self.change(team["admin"], row, "hub_employee")

    def test_nobody_changes_their_own_role(self, business, team):
        with pytest.raises(PermissionDenied):
            self.change(
                team["admin"], member_of(business, team["admin"]), "hub_manager"
            )

    @pytest.mark.parametrize("who", ["manager", "employee"])
    def test_a_manager_or_an_employee_changes_nobody(self, business, team, who):
        with pytest.raises(PermissionDenied):
            self.change(
                team[who],
                member_of(
                    business, team["employee" if who == "manager" else "manager"]
                ),
                "hub_employee",
            )

    def test_the_owner_role_is_not_on_offer(self, business, team):
        with pytest.raises(Exception) as refused:
            MemberRoleIn(id=member_of(business, team["admin"]).id, role="hub_owner")

        assert "role" in str(refused.value)

    def test_a_member_of_a_business_one_does_not_manage_is_out_of_reach(
        self, business, team, make_user
    ):
        other = create_business(make_user("other@example.com"), name="Café Lola")
        row = other.members.get()

        with pytest.raises(NotFound):
            self.change(team["owner"], row, "hub_employee")

    def test_an_unknown_member_is_not_found(self, business, team):
        import uuid

        with pytest.raises(NotFound):
            services.member_change_role(
                ctx_for(team["owner"]),
                MemberRoleIn(id=uuid.uuid7(), role="hub_employee"),
            )

    def test_the_role_of_an_invitation_changes_without_the_hub(self, business, team):
        before = version(business)

        self.change(team["owner"], member_of(business, team["invitee"]), "hub_manager")

        assert member_of(business, team["invitee"]).role == "hub_manager"
        assert version(business) == before


# --- Removing -------------------------------------------------------------------------------------


class TestRemove:
    def remove(self, actor, member):
        return services.member_remove(ctx_for(actor), ByIdIn(id=member.id))

    def test_removing_revokes_exactly_that_business(
        self, business, team, make_user, hub_double, django_capture_on_commit_callbacks
    ):
        other = create_business(make_user("other@example.com"), name="Café Lola")
        add_member(other, team["employee"], HubMember.Role.EMPLOYEE)
        before = version(business)

        with django_capture_on_commit_callbacks(execute=True):
            removed = self.remove(team["owner"], member_of(business, team["employee"]))

        assert removed.id
        assert not HubMember.objects.filter(
            hub=business, user=team["employee"]
        ).exists()
        assert HubMember.objects.filter(hub=other, user=team["employee"]).exists()
        assert not HubMembership.objects.filter(
            user=team["employee"], hub_slug=business.slug
        ).exists()
        assert version(business) == before + 1
        revoke = hub_double.calls_to("POST", "/internal/sessions/revoke")
        assert [call.body for call in revoke] == [
            {"user_id": str(team["employee"].pk), "hub_id": str(business.id)}
        ]

    def test_an_admin_removes_a_manager(self, business, team):
        self.remove(team["admin"], member_of(business, team["manager"]))

        assert not HubMember.objects.filter(hub=business, user=team["manager"]).exists()

    @pytest.mark.parametrize("target", ["owner", "admin"])
    def test_nobody_removes_a_peer_nor_a_superior(self, business, team, target):
        actor = team["admin"]
        row = member_of(business, team[target])
        with pytest.raises(PermissionDenied):
            self.remove(actor, row)

    def test_nobody_removes_themselves(self, business, team):
        with pytest.raises(PermissionDenied):
            self.remove(team["owner"], member_of(business, team["owner"]))

    def test_a_manager_removes_nobody(self, business, team):
        with pytest.raises(PermissionDenied):
            self.remove(team["manager"], member_of(business, team["employee"]))

    def test_an_invitation_is_cancelled_not_removed(self, business, team):
        with pytest.raises(Conflict) as refused:
            self.remove(team["owner"], member_of(business, team["invitee"]))

        assert refused.value.code == "hubs.member_pending"


# --- Resending and cancelling an invitation -------------------------------------------------------


class TestResendAndCancel:
    def test_resend_renews_the_window_and_mails_again(
        self, business, team, django_capture_on_commit_callbacks
    ):
        HubMember.objects.filter(user=team["invitee"]).update(
            invited_at=timezone.now() - timedelta(days=8),
            invitation_expires_at=timezone.now() - timedelta(days=1),
        )

        with django_capture_on_commit_callbacks(execute=True):
            row = services.member_resend(
                ctx_for(team["owner"]),
                ByIdIn(id=member_of(business, team["invitee"]).id),
            )

        member = member_of(business, team["invitee"])
        assert row.status == "pending"
        assert member.invitation_expires_at > timezone.now() + timedelta(days=6)
        assert [message.to for message in mail.outbox] == [["invitee@example.com"]]

    def test_an_answered_member_has_nothing_to_resend(self, business, team):
        with pytest.raises(Conflict) as refused:
            services.member_resend(
                ctx_for(team["owner"]),
                ByIdIn(id=member_of(business, team["employee"]).id),
            )

        assert refused.value.code == "hubs.member_not_pending"

    def test_cancel_deletes_the_invitation(self, business, team):
        services.member_cancel(
            ctx_for(team["admin"]), ByIdIn(id=member_of(business, team["invitee"]).id)
        )

        assert not HubMember.objects.filter(hub=business, user=team["invitee"]).exists()

    def test_an_answered_member_is_removed_not_cancelled(self, business, team):
        with pytest.raises(Conflict) as refused:
            services.member_cancel(
                ctx_for(team["owner"]),
                ByIdIn(id=member_of(business, team["employee"]).id),
            )

        assert refused.value.code == "hubs.member_not_pending"

    def test_a_manager_cancels_nothing(self, business, team):
        with pytest.raises(PermissionDenied):
            services.member_cancel(
                ctx_for(team["manager"]),
                ByIdIn(id=member_of(business, team["invitee"]).id),
            )

    def test_an_admin_cannot_cancel_an_admins_invitation(
        self, business, team, make_user
    ):
        add_member(
            business,
            make_user("future-admin@example.com"),
            HubMember.Role.ADMIN,
            accepted=False,
        )

        with pytest.raises(PermissionDenied):
            services.member_cancel(
                ctx_for(team["admin"]),
                ByIdIn(
                    id=HubMember.objects.get(user__email="future-admin@example.com").id
                ),
            )


# --- Answering an invitation ----------------------------------------------------------------------


class TestAccept:
    def accept(self, user, member_id):
        return services.invitation_accept(ctx_for(user), ByIdIn(id=member_id))

    def test_accepting_lets_the_invitee_in_with_the_role_it_says(self, business, team):
        before = version(business)

        row = self.accept(team["invitee"], member_of(business, team["invitee"]).id)

        member = member_of(business, team["invitee"])
        assert member.accepted_at is not None
        assert (row.slug, row.role, member.role) == (
            "bar-manolo",
            "hub_employee",
            "hub_employee",
        )
        assert HubMembership.objects.filter(
            user=team["invitee"], hub_slug=business.slug
        ).exists()
        assert version(business) == before + 1

    def test_somebody_elses_invitation_is_not_found(self, business, team):
        with pytest.raises(NotFound):
            self.accept(team["stranger"], member_of(business, team["invitee"]).id)

        assert member_of(business, team["invitee"]).is_pending

    def test_a_membership_already_answered_is_no_invitation(self, business, team):
        with pytest.raises(NotFound):
            self.accept(team["employee"], member_of(business, team["employee"]).id)

    def test_replaying_an_acceptance_grants_nothing_more(self, business, team):
        member_id = member_of(business, team["invitee"]).id
        self.accept(team["invitee"], member_id)
        first = member_of(business, team["invitee"]).accepted_at

        with pytest.raises(NotFound):
            self.accept(team["invitee"], member_id)

        assert member_of(business, team["invitee"]).accepted_at == first

    def test_an_expired_invitation_cannot_be_accepted(self, business, team):
        HubMember.objects.filter(user=team["invitee"]).update(
            invitation_expires_at=timezone.now() - timedelta(seconds=1)
        )

        with pytest.raises(Conflict) as refused:
            self.accept(team["invitee"], member_of(business, team["invitee"]).id)

        assert refused.value.code == "hubs.invitation_expired"

    def test_a_deleted_business_grants_nothing(self, business, team):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(NotFound):
            self.accept(team["invitee"], member_of(business, team["invitee"]).id)

    def test_accepting_never_touches_another_business_of_mine(
        self, business, team, make_user
    ):
        other = create_business(make_user("other@example.com"), name="Café Lola")
        add_member(other, team["invitee"], HubMember.Role.MANAGER, accepted=False)

        self.accept(team["invitee"], member_of(business, team["invitee"]).id)

        assert member_of(other, team["invitee"]).is_pending

    def test_declining_deletes_the_invitation(self, business, team):
        services.invitation_decline(
            ctx_for(team["invitee"]), ByIdIn(id=member_of(business, team["invitee"]).id)
        )

        assert not HubMember.objects.filter(hub=business, user=team["invitee"]).exists()

    def test_declining_somebody_elses_is_not_found(self, business, team):
        with pytest.raises(NotFound):
            services.invitation_decline(
                ctx_for(team["stranger"]),
                ByIdIn(id=member_of(business, team["invitee"]).id),
            )

    def test_a_cancelled_invitation_is_not_resurrected(self, business, team):
        """test_invitation_accept: the inviter changed their mind before the answer."""
        member_id = member_of(business, team["invitee"]).id
        services.member_cancel(ctx_for(team["owner"]), ByIdIn(id=member_id))

        with pytest.raises(NotFound):
            self.accept(team["invitee"], member_id)

        assert not HubMember.objects.filter(hub=business, user=team["invitee"]).exists()

    def test_an_id_that_is_no_invitation_of_mine_grants_nothing(self, business, team):
        """test_invitation_accept: a business I was never invited to (or any id at all)."""
        import uuid

        for poked in (business.id, uuid.uuid7()):
            with pytest.raises(NotFound):
                self.accept(team["stranger"], poked)

        assert not HubMember.objects.filter(user=team["stranger"]).exists()

    @pytest.mark.parametrize("status", [Hub.Status.PREPARING, Hub.Status.SUSPENDED, Hub.Status.PAST_DUE])
    def test_a_business_that_cannot_open_now_can_still_be_answered(self, business, team, status):
        """test_invitation_accept (a sleeping business still works): answering is not entering; «Open»
        says why it does not open yet."""
        Hub.objects.filter(pk=business.pk).update(status=status)

        self.accept(team["invitee"], member_of(business, team["invitee"]).id)

        assert not member_of(business, team["invitee"]).is_pending


class TestMyInvitations:
    def mine(self, user):
        return queries.invitation_list_mine(
            ctx_for(user), InvitationListIn()
        ).model_dump(mode="json")["invitations"]

    def test_what_waits_for_my_answer(self, business, team):
        (invitation,) = self.mine(team["invitee"])

        assert invitation["hub"]["name"] == "Bar Manolo"
        assert (invitation["role"], invitation["invited_by"]) == (
            "hub_employee",
            "Olga Owner",
        )

    def test_an_expired_invitation_is_no_longer_news(self, business, team):
        HubMember.objects.filter(user=team["invitee"]).update(
            invitation_expires_at=timezone.now()
        )

        assert self.mine(team["invitee"]) == []

    def test_owning_or_belonging_is_not_being_invited(self, business, team):
        assert self.mine(team["owner"]) == [] and self.mine(team["employee"]) == []

    def test_a_deleted_business_invites_nobody(self, business, team):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        assert self.mine(team["invitee"]) == []


# --- The members page -----------------------------------------------------------------------------


class TestMemberList:
    def test_the_owner_sees_everybody_with_their_state(self, business, team):
        page = members(team["owner"], business)

        assert [(row["email"], row["role"], row["status"]) for row in page["rows"]] == [
            ("owner@example.com", "hub_owner", "active"),
            ("admin@example.com", "hub_admin", "active"),
            ("manager@example.com", "hub_manager", "active"),
            ("employee@example.com", "hub_employee", "active"),
            ("invitee@example.com", "hub_employee", "pending"),
        ]
        assert page["total"] == 5
        assert page["seats"] == {"used": 5, "limit": None}

    def test_an_expired_invitation_says_so(self, business, team):
        HubMember.objects.filter(user=team["invitee"]).update(
            invitation_expires_at=timezone.now()
        )

        rows = {row["email"]: row for row in members(team["owner"], business)["rows"]}

        assert rows["invitee@example.com"]["status"] == "expired"

    def test_my_own_row_is_marked_and_offers_nothing(self, business, team):
        rows = {row["email"]: row for row in members(team["owner"], business)["rows"]}

        assert rows["owner@example.com"]["is_me"] is True
        assert rows["owner@example.com"]["actions"] == []
        assert [email for email, row in rows.items() if row["is_me"]] == ["owner@example.com"]

    def test_a_member_without_a_name_is_shown_by_email(self, business, team):
        rows = {row["email"]: row for row in members(team["owner"], business)["rows"]}

        assert rows["invitee@example.com"]["name"] == "invitee@example.com"
        assert rows["admin@example.com"]["name"] == "Adela"

    def test_the_actions_the_owner_has(self, business, team):
        rows = {row["email"]: row for row in members(team["owner"], business)["rows"]}

        assert rows["admin@example.com"]["actions"] == ["change_role", "remove", "transfer"]
        assert rows["invitee@example.com"]["actions"] == ["change_role", "resend", "cancel"]
        assert rows["admin@example.com"]["assignable_roles"] == [
            "hub_admin",
            "hub_manager",
            "hub_employee",
        ]

    def test_an_admin_cannot_reach_the_owners_row_nor_transfer(self, business, team):
        rows = {row["email"]: row for row in members(team["admin"], business)["rows"]}

        assert rows["owner@example.com"]["actions"] == []
        assert rows["employee@example.com"]["actions"] == ["change_role", "remove"]
        assert rows["employee@example.com"]["assignable_roles"] == [
            "hub_manager",
            "hub_employee",
        ]
        assert members(team["admin"], business)["invitable_roles"] == [
            "hub_manager",
            "hub_employee",
        ]

    @pytest.mark.parametrize("who", ["manager", "employee"])
    def test_a_manager_or_an_employee_sees_no_members(self, business, team, who):
        with pytest.raises(PermissionDenied):
            members(team[who], business)

    def test_a_stranger_does_not_learn_the_business_exists(self, business, team):
        with pytest.raises(NotFound):
            members(team["stranger"], business)

    def test_it_is_paginated(self, business, team):
        page = members(team["owner"], business, limit=2, offset=2)

        assert [row["email"] for row in page["rows"]] == [
            "manager@example.com",
            "employee@example.com",
        ]
        assert (page["total"], page["limit"], page["offset"]) == (5, 2, 2)

    def test_the_role_reads_in_the_callers_language(self, business, team):
        page = queries.member_list(
            ctx_for(team["owner"], language="es"), MemberListIn(hub_id=business.id)
        ).model_dump()

        assert [row["role_label"] for row in page["rows"][:4]] == [
            "Propietario",
            "Administrador",
            "Encargado",
            "Empleado",
        ]
        assert page["rows"][4]["status_label"] == "Pendiente"
