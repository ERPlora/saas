"""The accountancy firm (``hub_accountant``): a basic role that only reads, invited like anybody and taking no seat.

* it ranks with the employee (below the manager), so an owner or an admin invites it and changes it as anybody;
* inviting it, renewing its invitation and accepting it need no free seat, and the seats used never count it;
* moving it to a role that takes a seat needs a free one, as inviting that role would;
* it travels to the Hub as one more role: in the snapshot and in the one-time code it redeems.
"""

import json
import time
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone, translation
from live.errors import Conflict

from accounts.services import hub_jump
from accounts.signing import sign
from hubs.models import HubMember, Subscription
from hubs.queries import hub_sync, membership
from hubs.schemas.common import ByIdIn
from hubs.schemas.membership import MemberInviteIn, MemberListIn, MemberRoleIn
from hubs.services import invitation_answers, member_management
from hubs.tests.conftest import SECRET, add_member, ctx_for

pytestmark = pytest.mark.django_db

ACCOUNTANT = "hub_accountant"
HOST = "localhost:8001"


def invite(actor, hub, email, role="hub_employee"):
    return member_management.member_invite(ctx_for(actor), MemberInviteIn(hub_id=hub.id, email=email, role=role))


def change_role(actor, member, role):
    return member_management.member_change_role(ctx_for(actor), MemberRoleIn(id=member.id, role=role))


def members_page(actor, hub):
    return membership.member_list(ctx_for(actor), MemberListIn(hub_id=hub.id)).model_dump(mode="json")


def full(business, owner):
    """Free without its trial: the owner and two live invitations take its three seats."""
    Subscription.objects.filter(hub=business).update(trial_end=timezone.now() - timedelta(seconds=1))
    invite(owner, business, "one@example.com")
    invite(owner, business, "two@example.com")


def post(client, path, data):
    return client.post(f"/api{path}", json.dumps(data, default=str), content_type="application/json", HTTP_HOST=HOST)


class TestTheRole:
    def test_the_database_keeps_it(self, business, make_user):
        member = add_member(business, make_user("firm@example.com"), ACCOUNTANT)

        assert HubMember.objects.get(pk=member.pk).role == ACCOUNTANT

    def test_the_database_still_refuses_a_role_it_does_not_know(self, business, make_user):
        with pytest.raises(IntegrityError), transaction.atomic():
            add_member(business, make_user("firm@example.com"), "hub_auditor")

    def test_it_ranks_with_the_employee_below_the_manager(self):
        assert HubMember.RANK[ACCOUNTANT] == HubMember.RANK[HubMember.Role.EMPLOYEE] == 40

    def test_it_reads_gestoria_in_spanish(self):
        with translation.override("es"):
            assert str(HubMember.Role(ACCOUNTANT).label) == "Gestoría"


class TestInvitingIt:
    def test_the_owner_and_an_admin_may_hand_it_out_and_a_manager_may_not(self, team, business):
        roles = {who: members_page(team[who], business)["invitable_roles"] for who in ("owner", "admin")}

        assert roles == {
            "owner": ["hub_admin", "hub_manager", "hub_employee", ACCOUNTANT],
            "admin": ["hub_manager", "hub_employee", ACCOUNTANT],
        }
        assert membership.assignable_roles(HubMember.Role.MANAGER) == []

    def test_the_invitation_carries_the_role_and_its_label(self, business, owner):
        with translation.override("es"):
            row = invite(owner, business, "firm@example.com", ACCOUNTANT)

        assert (row.role, row.role_label) == (ACCOUNTANT, "Gestoría")
        assert HubMember.objects.get(user__email="firm@example.com").role == ACCOUNTANT

    def test_the_panel_sends_it_through_the_api(self, client, business, owner):
        client.force_login(owner)

        response = post(client, "/hubs/members/invite", {"hub_id": business.id, "email": "firm@example.com", "role": ACCOUNTANT})

        assert response.status_code == 200, response.content
        assert response.json()["role"] == ACCOUNTANT

    def test_the_invitee_sees_it_on_its_invitation(self, client, business, owner, make_user):
        firm = make_user("firm@example.com")
        add_member(business, firm, ACCOUNTANT, invited_by=owner, accepted=False)
        client.force_login(firm)

        response = client.get("/api/hubs/invitations", HTTP_HOST=HOST)

        assert response.status_code == 200, response.content
        assert [row["role"] for row in response.json()["invitations"]] == [ACCOUNTANT]

    def test_an_owner_changes_somebody_to_it_and_back(self, team, business):
        employee = HubMember.objects.get(hub=business, user=team["employee"])

        assert change_role(team["owner"], employee, ACCOUNTANT).role == ACCOUNTANT
        assert change_role(team["admin"], employee, HubMember.Role.MANAGER).role == HubMember.Role.MANAGER


class TestItTakesNoSeat:
    def test_a_full_plan_still_invites_it_and_counts_it_nowhere(self, business, owner):
        full(business, owner)

        assert invite(owner, business, "firm@example.com", ACCOUNTANT).status == "pending"
        assert members_page(owner, business)["seats"] == {"used": 3, "limit": 3}

    def test_it_accepts_with_every_seat_taken_by_people_inside(self, business, owner, make_user):
        full(business, owner)
        for email in ("one@example.com", "two@example.com"):
            HubMember.objects.filter(user__email=email).update(accepted_at=timezone.now())
        firm = add_member(business, make_user("firm@example.com"), ACCOUNTANT, invited_by=owner, accepted=False)

        invitation_answers.invitation_accept(ctx_for(firm.user), ByIdIn(id=firm.id))

        assert HubMember.objects.get(pk=firm.pk).accepted_at is not None
        assert membership.people_inside(business) == 3

    def test_an_employee_accepts_beside_it_on_a_plan_with_one_seat_left(self, business, owner, make_user):
        Subscription.objects.filter(hub=business).update(trial_end=timezone.now() - timedelta(seconds=1))
        add_member(business, make_user("one@example.com"), HubMember.Role.EMPLOYEE, invited_by=owner)
        add_member(business, make_user("firm@example.com"), ACCOUNTANT, invited_by=owner)
        two = add_member(business, make_user("two@example.com"), HubMember.Role.EMPLOYEE, invited_by=owner, accepted=False)

        invitation_answers.invitation_accept(ctx_for(two.user), ByIdIn(id=two.id))

        assert HubMember.objects.get(pk=two.pk).accepted_at is not None

    def test_the_members_page_says_which_roles_take_no_seat(self, business, owner):
        assert members_page(owner, business)["free_roles"] == [ACCOUNTANT]

    def test_renewing_its_expired_invitation_on_a_full_plan_needs_no_seat(self, business, owner):
        full(business, owner)
        invite(owner, business, "firm@example.com", ACCOUNTANT)
        firm = HubMember.objects.get(user__email="firm@example.com")
        HubMember.objects.filter(pk=firm.pk).update(invitation_expires_at=timezone.now())

        assert member_management.member_resend(ctx_for(owner), ByIdIn(id=firm.id)).status == "pending"

    def test_moving_it_to_a_role_with_a_seat_on_a_full_plan_is_refused(self, business, owner, make_user):
        full(business, owner)
        firm = add_member(business, make_user("firm@example.com"), ACCOUNTANT, invited_by=owner)

        with pytest.raises(Conflict) as refused:
            change_role(owner, firm, HubMember.Role.EMPLOYEE)

        assert (refused.value.code, refused.value.limit, refused.value.used) == ("hubs.seat_limit", 3, 3)
        assert HubMember.objects.get(pk=firm.pk).role == ACCOUNTANT

    def test_moving_it_to_a_role_with_a_seat_takes_a_free_one(self, business, owner, make_user):
        Subscription.objects.filter(hub=business).update(trial_end=timezone.now() - timedelta(seconds=1))
        firm = add_member(business, make_user("firm@example.com"), ACCOUNTANT, invited_by=owner)

        change_role(owner, firm, HubMember.Role.EMPLOYEE)

        assert members_page(owner, business)["seats"] == {"used": 2, "limit": 3}

    def test_moving_somebody_to_it_frees_their_seat(self, business, owner, make_user):
        full(business, owner)
        one = HubMember.objects.get(user__email="one@example.com")

        change_role(owner, one, ACCOUNTANT)

        assert members_page(owner, business)["seats"] == {"used": 2, "limit": 3}


class TestItReachesTheHub:
    def test_the_snapshot_carries_its_role(self, business, owner, make_user):
        firm = add_member(business, make_user("firm@example.com"), ACCOUNTANT, invited_by=owner)

        members = hub_sync.hub_snapshot(business.id)["members"]

        assert {member["user_id"]: member["role"] for member in members}[str(firm.user_id)] == ACCOUNTANT

    def test_its_business_lists_with_its_role_and_opens(self, client, business, owner, make_user):
        firm = make_user("firm@example.com")
        add_member(business, firm, ACCOUNTANT, invited_by=owner)
        client.force_login(firm)

        response = client.get("/api/hubs/businesses", HTTP_HOST=HOST)

        assert response.status_code == 200, response.content
        assert [(row["slug"], row["role"]) for row in response.json()["rows"]] == [(business.slug, ACCOUNTANT)]

    def test_the_code_it_redeems_says_its_role(self, client, settings, business, owner, make_user):
        settings.INTERNAL_SHARED_SECRET = SECRET
        firm = make_user("firm@example.com")
        add_member(business, firm, ACCOUNTANT, invited_by=owner)
        code = hub_jump.issue_code(firm, business.slug)
        body, now = json.dumps({"code": code, "hub": business.slug}).encode(), int(time.time())

        response = client.post(
            "/internal/auth/redeem",
            body,
            content_type="application/json",
            headers={"X-Erplora-Timestamp": str(now), "X-Erplora-Signature": sign(body, now, SECRET)},
        )

        assert response.status_code == 200, response.content
        assert response.json()["role"] == ACCOUNTANT
