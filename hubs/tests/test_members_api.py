"""The members page and its doors over HTTP (``/api/hubs/members*``, ``/api/hubs/invitations*``,
``/api/hubs/ownership/*``): what each row offers, computed by the server so the panel never guesses, and
what each door allows, whatever a row showed (plan 2026-10-13, L1-B).

Each row of ``hubs.member.list`` carries ``is_me`` and ``actions``, a list in a fixed order
(``change_role``, ``remove``, ``resend``, ``cancel``, ``transfer``) of what the account may do on it: a
role change and «Remove» on somebody it manages and who answered, «Resend» and «Cancel» on an
invitation it manages, «Transfer» only for the owner, on somebody else who answered, while no offer
waits. Nothing on one's own row, on a peer or a superior, nor on a deleted business.

Ported from ERPlora/saas (origin/develop), from the okdt table and the dashboard views to the query and
the ninja routes: ``dashboard/users/tests/`` ``test_users_row_actions`` (14), ``test_users_list_shows_self``
(7), ``test_pending_invitation_status`` (11), ``test_remove_user`` (10), ``test_members_per_hub`` (9),
``test_account_role_choices`` (6), ``test_role_pill_is_translated`` (3) and ``test_ownership_transfer_views``
(28); and the HTTP cases of ``hubs/main/tests/`` ``test_members_role_escalation`` (malformed input),
``test_invitation_accept`` (a poked, malformed or empty body grants nothing; other verbs) and
``test_permissions`` (the account part: a missing, malformed or unknown business). Each file's cases that
are covered elsewhere, or dropped, are listed in the report of the lot.
"""

import json
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from hubs import services
from hubs.models import Hub, HubMember, HubOwnershipTransfer
from hubs.schemas import OwnershipTransferIn
from hubs.tests.conftest import add_member, create_business, ctx_for, member_of

pytestmark = pytest.mark.django_db

User = get_user_model()
HOST = "localhost:8001"
ORDER = ["change_role", "remove", "resend", "cancel", "transfer"]


def get(client, path, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=HOST)


def post(client, path, data):
    return client.post(
        f"/api{path}",
        json.dumps(data, default=str),
        content_type="application/json",
        HTTP_HOST=HOST,
    )


def error(response):
    return response.status_code, response.json()["error"]["code"]


@pytest.fixture
def as_(client):
    def sign_in(user):
        client.force_login(user)
        return client

    return sign_in


def page(client, hub, **params):
    response = get(client, "/hubs/members", hub_id=str(hub.id), **params)
    assert response.status_code == 200, response.content
    return response.json()


def rows(client, hub):
    return {row["email"]: row for row in page(client, hub)["rows"]}


def offer(owner, hub, to_user):
    return services.ownership_transfer(
        ctx_for(owner),
        OwnershipTransferIn(hub_id=hub.id, member_id=member_of(hub, to_user).id),
    )


# --- What each row offers (test_users_row_actions, test_ownership_transfer_views) ----------------


class TestWhatEachRowOffers:
    def test_the_owner_may_change_remove_and_hand_over_an_answered_member(
        self, as_, business, team
    ):
        row = rows(as_(team["owner"]), business)["employee@example.com"]

        assert row["actions"] == ["change_role", "remove", "transfer"]
        assert row["assignable_roles"] == ["hub_admin", "hub_manager", "hub_employee"]

    def test_my_own_row_offers_nothing(self, as_, business, team):
        """9 of 9 products deny the destructive action on your own row (saas#1626)."""
        listed = rows(as_(team["owner"]), business)

        # The neighbour proves the check sees actions at all.
        assert listed["admin@example.com"]["actions"], (
            "control: a manageable row carries actions"
        )
        assert listed["owner@example.com"]["actions"] == []
        assert listed["owner@example.com"]["assignable_roles"] == []

    def test_an_admin_cannot_reach_the_owners_row(self, as_, business, team):
        """A business is never left without its owner."""
        listed = rows(as_(team["admin"]), business)

        assert listed["employee@example.com"]["actions"] == ["change_role", "remove"], (
            "control"
        )
        assert listed["owner@example.com"]["actions"] == []

    def test_an_admin_cannot_reach_a_peer(self, as_, business, team, make_user):
        add_member(business, make_user("admin2@example.com"), HubMember.Role.ADMIN)

        assert rows(as_(team["admin"]), business)["admin2@example.com"]["actions"] == []

    def test_an_invitation_is_resent_or_cancelled_never_removed(
        self, as_, business, team
    ):
        listed = rows(as_(team["owner"]), business)

        assert listed["invitee@example.com"]["actions"] == [
            "change_role",
            "resend",
            "cancel",
        ]

    def test_an_expired_invitation_offers_the_same(self, as_, business, team):
        HubMember.objects.filter(user=team["invitee"]).update(
            invitation_expires_at=timezone.now()
        )

        row = rows(as_(team["owner"]), business)["invitee@example.com"]

        assert (row["status"], row["actions"]) == (
            "expired",
            ["change_role", "resend", "cancel"],
        )

    def test_only_the_owner_is_offered_the_hand_over(self, as_, business, team, client):
        by_owner = rows(as_(team["owner"]), business)
        by_admin = rows(as_(team["admin"]), business)

        offered = sorted(
            email for email, row in by_owner.items() if "transfer" in row["actions"]
        )
        assert offered == [
            "admin@example.com",
            "employee@example.com",
            "manager@example.com",
        ]
        assert not any("transfer" in row["actions"] for row in by_admin.values())

    def test_the_hand_over_disappears_while_an_offer_waits(self, as_, business, team):
        offer(team["owner"], business, team["admin"])

        listed = rows(as_(team["owner"]), business)

        assert listed["employee@example.com"]["actions"] == ["change_role", "remove"]

    def test_the_owner_is_never_on_offer(self, as_, business, team):
        """Ownership changes hands only by the hand-over (saas#1626), never from the role menu."""
        listed = page(as_(team["owner"]), business)

        assert all("hub_owner" not in row["assignable_roles"] for row in listed["rows"])
        assert listed["invitable_roles"] == ["hub_admin", "hub_manager", "hub_employee"]

    def test_a_deleted_business_offers_nothing(self, as_, business, team):
        """Every write on it answers 409: the page shows no button that would."""
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        listed = page(as_(team["owner"]), business)

        assert all(row["actions"] == [] for row in listed["rows"])
        assert listed["invitable_roles"] == []

    def test_the_actions_keep_one_order(self, as_, business, team):
        for row in page(as_(team["owner"]), business)["rows"]:
            assert row["actions"] == [
                action for action in ORDER if action in row["actions"]
            ]


# --- The list shows me (test_users_list_shows_self) ----------------------------------------------


class TestTheListShowsMe:
    def test_a_lone_owner_sees_their_own_row(self, as_, owner, plans):
        """One owner, nobody invited: one row, never the empty state (saas#1566)."""
        hub = create_business(owner)

        listed = page(as_(owner), hub)

        assert listed["total"] == 1
        assert [(row["email"], row["is_me"]) for row in listed["rows"]] == [
            ("owner@example.com", True)
        ]

    def test_the_invited_person_is_listed_next_to_the_owner(self, as_, owner, plans):
        hub = create_business(owner)
        client = as_(owner)
        post(
            client,
            "/hubs/members/invite",
            {"hub_id": str(hub.id), "email": "invited@example.com"},
        )

        listed = page(client, hub)

        assert listed["total"] == 2
        assert [row["email"] for row in listed["rows"]] == [
            "owner@example.com",
            "invited@example.com",
        ]

    def test_my_row_is_marked_as_mine_and_only_mine(self, as_, business, team):
        listed = rows(as_(team["admin"]), business)

        assert [email for email, row in listed.items() if row["is_me"]] == [
            "admin@example.com"
        ]

    def test_the_people_of_a_business_i_do_not_manage_stay_hidden(
        self, as_, business, team, make_user
    ):
        """Tenancy (ADR-0201): the list is per business, and somebody else's does not exist for me."""
        lola = make_user("lola@example.com")
        other = create_business(lola, name="Café Lola")
        client = as_(team["owner"])

        assert "lola@example.com" not in rows(client, business)
        assert error(get(client, "/hubs/members", hub_id=str(other.id))) == (
            404,
            "not_found",
        )

    def test_english_is_the_source_of_the_role_names(self, as_, business, team):
        """saas#2176: the role reads through the one translated catalogue (Spanish: test_members)."""
        listed = rows(as_(team["owner"]), business)

        assert [
            listed[f"{who}@example.com"]["role_label"]
            for who in ("owner", "admin", "manager", "employee")
        ] == [
            "Owner",
            "Admin",
            "Manager",
            "Employee",
        ]


# --- An invitation is not a person inside (test_pending_invitation_status) ------------------------


class TestAnInvitationIsNotSomebodyInside:
    def test_a_pending_invitee_has_not_joined_and_reads_pending(
        self, as_, business, team
    ):
        row = rows(as_(team["owner"]), business)["invitee@example.com"]

        assert (row["status"], row["joined_at"], row["accepted_at"]) == (
            "pending",
            None,
            None,
        )
        assert row["invited_at"] is not None

    def test_an_answered_member_keeps_the_date_and_reads_active(
        self, as_, business, team
    ):
        row = rows(as_(team["owner"]), business)["employee@example.com"]

        assert row["status"] == "active"
        assert row["joined_at"] is not None

    def test_the_owner_reads_active(self, as_, business, team):
        assert (
            rows(as_(team["owner"]), business)["owner@example.com"]["status"]
            == "active"
        )

    def test_signing_in_does_not_answer_an_invitation(self, as_, business, team):
        """Round 17 §2.8: only «Accept» answers it (the old rule took a later sign-in as an answer,
        because then the invitation was a greeting and not the gate it is now)."""
        User.objects.filter(pk=team["invitee"].pk).update(
            last_login=timezone.now() + timedelta(minutes=5)
        )

        row = rows(as_(team["owner"]), business)["invitee@example.com"]

        assert row["status"] == "pending"
        assert member_of(business, team["invitee"]).is_pending


# --- The role change door (test_users_row_actions: TestChangeMembershipRoleDoor) -----------------


class TestTheRoleChangeDoor:
    def change(self, client, member, role):
        return post(
            client, "/hubs/members/change_role", {"id": str(member.id), "role": role}
        )

    def test_the_owner_promotes_an_employee_to_admin(self, as_, business, team):
        response = self.change(
            as_(team["owner"]), member_of(business, team["employee"]), "hub_admin"
        )

        assert response.status_code == 200
        assert response.json()["role"] == "hub_admin"
        assert member_of(business, team["employee"]).role == "hub_admin"

    @pytest.mark.parametrize(
        "who, target, role",
        [
            ("employee", "manager", "hub_employee"),  # below admin, nobody
            ("manager", "employee", "hub_manager"),
            ("admin", "admin", "hub_manager"),  # never one's own row
            ("admin", "employee", "hub_admin"),  # never one's own rank
            ("admin", "owner", "hub_employee"),  # never a superior
        ],
    )
    def test_the_door_refuses_what_the_row_did_not_offer(
        self, as_, business, team, who, target, role
    ):
        before = member_of(business, team[target]).role

        response = self.change(as_(team[who]), member_of(business, team[target]), role)

        assert error(response) == (403, "permission_denied")
        assert member_of(business, team[target]).role == before

    def test_the_owner_is_not_a_role_to_hand_out(self, as_, business, team):
        response = self.change(
            as_(team["owner"]), member_of(business, team["employee"]), "hub_owner"
        )

        assert error(response) == (422, "invalid_payload")
        assert member_of(business, team["employee"]).role == "hub_employee"

    def test_a_member_of_a_business_i_do_not_manage_is_out_of_reach(
        self, as_, business, team, make_user
    ):
        other = create_business(make_user("lola@example.com"), name="Café Lola")
        add_member(other, team["stranger"], HubMember.Role.EMPLOYEE)

        response = self.change(
            as_(team["owner"]), member_of(other, team["stranger"]), "hub_admin"
        )

        assert error(response) == (404, "not_found")
        assert member_of(other, team["stranger"]).role == "hub_employee"

    def test_an_unknown_member_is_404(self, as_, business, team):
        response = post(
            as_(team["owner"]),
            "/hubs/members/change_role",
            {"id": str(uuid.uuid7()), "role": "hub_admin"},
        )

        assert error(response) == (404, "not_found")

    def test_get_never_changes_a_role(self, as_, business, team):
        employee = member_of(business, team["employee"])

        response = get(
            as_(team["owner"]),
            "/hubs/members/change_role",
            id=str(employee.id),
            role="hub_admin",
        )

        assert response.status_code == 405
        assert member_of(business, team["employee"]).role == "hub_employee"

    def test_without_an_account_it_is_401(self, client, business, team):
        response = self.change(
            client, member_of(business, team["employee"]), "hub_admin"
        )

        assert error(response) == (401, "unauthorized")


# --- The remove door (test_remove_user, test_members_per_hub) -------------------------------------


class TestTheRemoveDoor:
    def remove(self, client, member_id):
        return post(client, "/hubs/members/remove", {"id": str(member_id)})

    def test_an_admin_removes_a_member_and_only_from_this_business(
        self, as_, business, team, make_user
    ):
        other = create_business(make_user("lola@example.com"), name="Café Lola")
        add_member(other, team["manager"], HubMember.Role.MANAGER)
        manager = member_of(business, team["manager"])

        response = self.remove(as_(team["admin"]), manager.id)

        assert (response.status_code, response.json()) == (200, {"id": str(manager.id)})
        assert not HubMember.objects.filter(pk=manager.pk).exists()
        assert HubMember.objects.filter(hub=other, user=team["manager"]).exists()

    def test_a_member_of_a_business_i_do_not_manage_is_out_of_reach(
        self, as_, business, team, make_user
    ):
        other = create_business(make_user("lola@example.com"), name="Café Lola")
        theirs = add_member(other, team["stranger"], HubMember.Role.EMPLOYEE)

        assert error(self.remove(as_(team["owner"]), theirs.id)) == (404, "not_found")
        assert HubMember.objects.filter(pk=theirs.pk).exists()

    def test_an_unknown_member_is_404(self, as_, business, team):
        assert error(self.remove(as_(team["owner"]), uuid.uuid7())) == (
            404,
            "not_found",
        )

    @pytest.mark.parametrize("method", ["get", "put", "delete"])
    def test_only_post_removes(self, as_, business, team, method):
        employee = member_of(business, team["employee"])
        client = as_(team["owner"])

        response = getattr(client, method)(
            f"/api/hubs/members/remove?id={employee.id}",
            content_type="application/json",
            HTTP_HOST=HOST,
        )

        assert response.status_code == 405
        assert HubMember.objects.filter(pk=employee.pk).exists()

    def test_without_an_account_it_is_401(self, client, business, team):
        response = self.remove(client, member_of(business, team["employee"]).id)

        assert error(response) == (401, "unauthorized")
        assert HubMember.objects.filter(hub=business, user=team["employee"]).exists()


# --- The invite door (test_account_role_choices, test_members_per_hub, role escalation input) ----


class TestTheInviteDoor:
    def invite(self, client, hub, **data):
        return post(client, "/hubs/members/invite", {"hub_id": str(hub.id), **data})

    def test_without_a_role_it_hands_out_the_least(self, as_, business, team):
        response = self.invite(
            as_(team["owner"]), business, email="newcomer@example.com"
        )

        assert response.status_code == 200
        assert (
            HubMember.objects.get(hub=business, user__email="newcomer@example.com").role
            == "hub_employee"
        )

    def test_it_needs_a_business(self, as_, business, team):
        response = post(
            as_(team["owner"]), "/hubs/members/invite", {"email": "new@example.com"}
        )

        assert error(response) == (422, "invalid_payload")
        assert set(response.json()["error"]["fields"]) == {"hub_id"}
        assert not User.objects.filter(email="new@example.com").exists()

    @pytest.mark.parametrize(
        "role",
        ["hub_owner", "owner", "admin", "member", "manager", "employee", "superuser"],
    )
    def test_only_the_three_invitable_roles_are_accepted(
        self, as_, business, team, role
    ):
        """The four roles are new (round 11): an old key is not quietly collapsed, it is refused."""
        response = self.invite(
            as_(team["owner"]), business, email="nope@example.com", role=role
        )

        assert error(response) == (422, "invalid_payload")
        assert not User.objects.filter(email="nope@example.com").exists()

    @pytest.mark.parametrize(
        "data",
        [
            {"email": "weird@example.com", "role": ["hub_admin"]},
            {"email": {"a": 1}, "role": "hub_employee"},
        ],
    )
    def test_a_value_of_the_wrong_type_is_a_422_not_a_500(
        self, as_, business, team, data
    ):
        response = self.invite(as_(team["owner"]), business, **data)

        assert error(response) == (422, "invalid_payload")
        assert not User.objects.filter(email="weird@example.com").exists()


# --- Reading and answering (test_invitation_accept, test_ownership_transfer_views) ----------------


class TestTheAnswers:
    def test_every_invitation_waiting_gets_its_own_answer(
        self, as_, business, team, make_user
    ):
        other = create_business(make_user("lola@example.com"), name="Peluquería Rosa")
        add_member(other, team["invitee"], HubMember.Role.MANAGER, accepted=False)

        invitations = get(as_(team["invitee"]), "/hubs/invitations").json()[
            "invitations"
        ]

        assert sorted(item["hub"]["name"] for item in invitations) == [
            "Bar Manolo",
            "Peluquería Rosa",
        ]

    @pytest.mark.parametrize("body", [{"id": "../../etc/passwd"}, {}])
    def test_a_malformed_or_empty_answer_grants_nothing(
        self, as_, business, team, body
    ):
        response = post(as_(team["invitee"]), "/hubs/invitations/accept", body)

        assert error(response) == (422, "invalid_payload")
        assert member_of(business, team["invitee"]).is_pending

    def test_the_body_cannot_choose_the_role(self, as_, business, team):
        """Accepting writes no role: the invitation's role is the role."""
        invitation = member_of(business, team["invitee"])

        response = post(
            as_(team["invitee"]),
            "/hubs/invitations/accept",
            {"id": str(invitation.id), "role": "hub_owner"},
        )

        assert response.status_code == 200
        assert member_of(business, team["invitee"]).role == "hub_employee"

    @pytest.mark.parametrize(
        "path",
        [
            "/hubs/invitations/accept",
            "/hubs/invitations/decline",
            "/hubs/ownership/accept",
            "/hubs/ownership/decline",
            "/hubs/ownership/cancel",
        ],
    )
    def test_get_is_not_an_answer(self, as_, business, team, path):
        transfer = offer(team["owner"], business, team["admin"])
        target = (
            transfer.id
            if "ownership" in path
            else member_of(business, team["invitee"]).id
        )

        response = get(as_(team["admin"]), path, id=str(target))

        assert response.status_code == 405
        assert HubOwnershipTransfer.objects.get().status == "pending"
        assert member_of(business, team["invitee"]).is_pending

    def test_an_unknown_offer_is_404(self, as_, business, team):
        response = post(
            as_(team["owner"]), "/hubs/ownership/accept", {"id": str(uuid.uuid7())}
        )

        assert error(response) == (404, "not_found")

    def test_a_bystander_sees_no_offer_received_nor_sent(self, as_, business, team):
        offer(team["owner"], business, team["admin"])
        client = as_(team["manager"])

        listed = get(client, "/hubs/businesses").json()

        assert listed["ownership_offers"] == []
        assert error(get(client, "/hubs/businesses/detail", id=str(business.id))) == (
            403,
            "permission_denied",
        )
        detail = get(
            as_(team["admin"]), "/hubs/businesses/detail", id=str(business.id)
        ).json()
        assert (
            detail["pending_transfer"] is None
        )  # only the owner sees the one they started


# --- Which business (test_permissions, the account part) ------------------------------------------


class TestWhichBusiness:
    def test_a_missing_or_malformed_business_is_422(self, as_, business, team):
        client = as_(team["owner"])

        assert error(get(client, "/hubs/members")) == (422, "invalid_payload")
        assert error(get(client, "/hubs/members", hub_id="not-a-uuid")) == (
            422,
            "invalid_payload",
        )

    def test_an_unknown_business_is_404_never_a_hint(self, as_, business, team):
        assert error(
            get(as_(team["owner"]), "/hubs/members", hub_id=str(uuid.uuid7()))
        ) == (404, "not_found")
