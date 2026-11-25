"""The people of ERPlora's own business: the team panel of any business, the photo the Hub takes of them, and the jump.

Its photo names its people and its version and nothing else, and only an accepted member of its row enters it.
"""

import pytest
from live.errors import NotFound, OperationError, PermissionDenied

from accounts.services import account_businesses, hub_jump
from accounts.tests.conftest import enter
from billing import stripe_service
from billing.tests.stripe_double import StripeDouble
from hubs.models import Hub, HubMember, SessionRevocation
from hubs.queries import businesses, hub_sync, membership
from hubs.schemas.businesses import BusinessListIn, BusinessOpenIn
from hubs.schemas.common import ByIdIn
from hubs.schemas.membership import MemberInviteIn, MemberListIn, MemberRoleIn
from hubs.schemas.ownership import OwnershipTransferIn
from hubs.services import hub_push, invitation_answers, member_management, opening, ownership
from hubs.tests.conftest import add_member, create_business, ctx_for, member_of, role_on

pytestmark = pytest.mark.django_db

ROLES = ["hub_admin", "hub_manager", "hub_employee", "hub_accountant"]


@pytest.fixture
def stripe_double(monkeypatch):
    double = StripeDouble()
    monkeypatch.setattr(stripe_service, "client", lambda: double)
    return double


def invite(hub, inviter, email, role="hub_employee"):
    data = MemberInviteIn(hub_id=hub.id, email=email, role=role)
    return member_management.member_invite(ctx_for(inviter), data)


def accept(member_id, user):
    invitation_answers.invitation_accept(ctx_for(user), ByIdIn(id=member_id))


def version_of(hub) -> int:
    return Hub.objects.values_list("state_version", flat=True).get(pk=hub.pk)


class TestItsPhoto:
    def test_it_names_its_people_and_its_version_and_nothing_else(self, platform_business, founder):
        photo = hub_sync.hub_snapshot(platform_business.id)

        assert photo == {
            "hub_id": str(platform_business.id),
            "slug": "erp",
            "version": 1,
            "members": [
                {
                    "user_id": str(founder.pk),
                    "email": "founder@example.com",
                    "name": "Fina Founder",
                    "role": "hub_owner",
                }
            ],
        }

    def test_only_accepted_people_are_in_it(self, platform_business, founder, make_user):
        accepted, invited = make_user("ana@example.com"), make_user("leo@example.com")
        add_member(platform_business, accepted, HubMember.Role.MANAGER)
        add_member(platform_business, invited, HubMember.Role.EMPLOYEE, accepted=False)

        photo = hub_sync.hub_snapshot(platform_business.id)

        assert [(member["user_id"], member["role"]) for member in photo["members"]] == [
            (str(founder.pk), "hub_owner"),
            (str(accepted.pk), "hub_manager"),
        ]

    def test_any_other_business_still_sends_its_whole_photo(self, business):
        photo = hub_sync.hub_snapshot(business.id)

        assert {"status", "plan", "modules", "verifactu", "whatsapp"} <= set(photo)
        assert photo["plan"]["slug"] == "free"

    def test_a_push_sends_the_photo_alone(self, platform_business, hub_double):
        hub_push.bump_state(platform_business.id)

        assert hub_push.sync_hub(platform_business.id) is True

        assert [(call.method, call.path) for call in hub_double.calls if call.method != "GET"] == [
            ("PUT", f"/internal/hubs/{platform_business.id}/state")
        ]


class TestItsTeam:
    @pytest.mark.parametrize("role", ROLES)
    def test_its_owner_invites_with_the_roles_of_any_business(self, platform_business, founder, make_user, role):
        invited = make_user("ana@example.com")

        row = invite(platform_business, founder, invited.email, role)

        assert (row.role, row.status) == (role, "pending")
        assert row.role in membership.assignable_roles("hub_owner")
        assert role_on(invited, "erp") is None

    def test_who_accepts_enters_the_photo_with_a_newer_version(
        self, platform_business, founder, make_user, hub_double, django_capture_on_commit_callbacks
    ):
        invited = make_user("ana@example.com")
        row = invite(platform_business, founder, invited.email, "hub_manager")
        assert version_of(platform_business) == 1

        with django_capture_on_commit_callbacks(execute=True):
            accept(row.id, invited)

        assert role_on(invited, "erp") == "hub_manager"
        photo = hub_double.calls_to("PUT", "/state")[-1].body
        assert photo["version"] == version_of(platform_business) == 2
        assert [member["email"] for member in photo["members"]] == ["founder@example.com", "ana@example.com"]

    def test_a_change_of_role_goes_out(self, platform_business, founder, make_user, hub_double, django_capture_on_commit_callbacks):
        employee = make_user("ana@example.com")
        member = add_member(platform_business, employee, HubMember.Role.EMPLOYEE)

        with django_capture_on_commit_callbacks(execute=True):
            member_management.member_change_role(ctx_for(founder), MemberRoleIn(id=member.id, role="hub_admin"))

        photo = hub_double.calls_to("PUT", "/state")[-1].body
        assert (photo["version"], photo["members"][1]["role"]) == (2, "hub_admin")

    def test_who_is_taken_out_leaves_the_photo_and_its_sessions_end(
        self, platform_business, founder, make_user, hub_double, django_capture_on_commit_callbacks
    ):
        employee = make_user("ana@example.com")
        member = add_member(platform_business, employee, HubMember.Role.EMPLOYEE)

        with django_capture_on_commit_callbacks(execute=True):
            member_management.member_remove(ctx_for(founder), ByIdIn(id=member.id))

        photo = hub_double.calls_to("PUT", "/state")[-1].body
        assert (photo["version"], [m["email"] for m in photo["members"]]) == (2, ["founder@example.com"])
        assert hub_double.calls_to("POST", "/internal/sessions/revoke")[-1].body == {
            "user_id": str(employee.pk),
            "hub_id": str(platform_business.id),
        }
        assert role_on(employee, "erp") is None

    def test_no_plan_caps_its_people(self, platform_business, founder, make_user):
        for number in range(6):
            add_member(platform_business, make_user(f"person{number}@example.com"), HubMember.Role.EMPLOYEE)

        assert membership.member_list(ctx_for(founder), MemberListIn(hub_id=platform_business.id)).seats.limit is None
        assert invite(platform_business, founder, "one-more@example.com").status == "pending"

    def test_its_owner_hands_it_over_without_asking_stripe_anything(
        self, platform_business, founder, make_user, stripe_double, django_capture_on_commit_callbacks
    ):
        heir = make_user("ana@example.com")
        member = add_member(platform_business, heir, HubMember.Role.ADMIN)
        offer = ownership.ownership_transfer(
            ctx_for(founder), OwnershipTransferIn(hub_id=platform_business.id, member_id=member.id)
        )

        with django_capture_on_commit_callbacks(execute=True):
            ownership.ownership_accept(ctx_for(heir), ByIdIn(id=offer.id))

        assert (role_on(heir, "erp"), role_on(founder, "erp")) == ("hub_owner", "hub_admin")
        assert stripe_double.calls == []

    def test_the_staff_never_joins_it(self, platform_business, founder, make_user):
        make_user("staff@example.com", is_staff=True)

        with pytest.raises(OperationError) as caught:
            invite(platform_business, founder, "staff@example.com")

        assert caught.value.code == "hubs.platform_account"


class TestItsPage:
    def test_it_is_listed_to_its_people_without_a_plan(self, platform_business, founder):
        (row,) = businesses.business_list(ctx_for(founder), BusinessListIn()).rows

        assert (row.id, row.slug, row.plan, row.is_platform) == (platform_business.id, "erp", None, True)
        assert (row.can.open, row.can.manage) == (True, True)
        assert (row.can.delete, row.can.restore) == (False, False)

    def test_its_page_offers_its_people_and_nothing_to_pay_rename_or_delete(self, platform_business, founder):
        page = businesses.business_get(ctx_for(founder), ByIdIn(id=platform_business.id))

        assert (page.is_platform, page.plan, page.trial_plan, page.usage) == (True, None, None, None)
        assert page.seats.limit is None
        allowed = {name for name, may in page.can.model_dump().items() if may}
        assert allowed == {"open", "manage", "manage_members", "transfer", "download_data"}

    def test_any_other_business_is_none_of_it(self, business, owner):
        (row,) = businesses.business_list(ctx_for(owner), BusinessListIn()).rows
        page = businesses.business_get(ctx_for(owner), ByIdIn(id=business.id))

        assert (row.is_platform, page.is_platform) == (False, False)
        assert all(
            getattr(page.can, name) for name in ("manage_settings", "manage_billing", "delete", "change_address")
        )

    def test_a_stranger_does_not_learn_it_exists(self, platform_business, make_user):
        stranger = make_user("stranger@example.com")

        with pytest.raises(NotFound):
            businesses.business_get(ctx_for(stranger), ByIdIn(id=platform_business.id))
        assert businesses.business_list(ctx_for(stranger), BusinessListIn()).rows == []

    def test_an_employee_enters_it_and_manages_nothing(self, platform_business, make_user):
        employee = make_user("ana@example.com")
        add_member(platform_business, employee, HubMember.Role.EMPLOYEE)

        assert "erp" in opening.business_open(ctx_for(employee), BusinessOpenIn(id=platform_business.id)).url
        with pytest.raises(PermissionDenied):
            invite(platform_business, employee, "leo@example.com")


class TestTheJump:
    def test_each_person_enters_it_with_its_role(self, platform_business, founder, make_user):
        people = {role: make_user(f"{role}@example.com") for role in ROLES}
        for role, person in people.items():
            add_member(platform_business, person, role)

        for role, person in {"hub_owner": founder, **people}.items():
            identity = hub_jump.redeem_code(hub_jump.issue_code(person, "erp"), "erp")
            assert (identity.user_id, identity.role) == (str(person.pk), role)

    def test_who_is_no_member_gets_no_code(self, platform_business, make_user):
        with pytest.raises(hub_jump.HubAccessDenied):
            hub_jump.issue_code(make_user("stranger@example.com"), "erp")

    def test_an_invitation_without_an_answer_gets_no_code(self, platform_business, make_user):
        invited = make_user("ana@example.com")
        add_member(platform_business, invited, HubMember.Role.ADMIN, accepted=False)

        with pytest.raises(hub_jump.HubAccessDenied):
            hub_jump.issue_code(invited, "erp")

    @pytest.mark.parametrize("person", ["owner", "admin", "employee"])
    def test_the_people_of_another_business_do_not_enter_it(self, platform_business, business, team, person):
        assert hub_jump.issue_code(team[person], business.slug)
        with pytest.raises(hub_jump.HubAccessDenied):
            hub_jump.issue_code(team[person], "erp")

    def test_its_people_do_not_enter_another_business(self, platform_business, business, founder):
        with pytest.raises(hub_jump.HubAccessDenied):
            hub_jump.issue_code(founder, business.slug)

    def test_a_code_for_it_opens_no_other_business(self, platform_business, business, founder, owner):
        with pytest.raises(hub_jump.InvalidCode):
            hub_jump.redeem_code(hub_jump.issue_code(founder, "erp"), business.slug)
        with pytest.raises(hub_jump.InvalidCode):
            hub_jump.redeem_code(hub_jump.issue_code(owner, business.slug), "erp")

    def test_a_code_does_not_outlive_the_access(self, platform_business, founder, make_user):
        employee = make_user("ana@example.com")
        member = add_member(platform_business, employee, HubMember.Role.EMPLOYEE)
        code = hub_jump.issue_code(employee, "erp")
        member_management.member_remove(ctx_for(founder), ByIdIn(id=member.id))

        with pytest.raises(hub_jump.InvalidCode):
            hub_jump.redeem_code(code, "erp")

    def test_a_business_that_took_its_name_before_lets_nobody_in(self, make_user):
        """Until the name was reserved a business could bear it: its people never enter ERPlora's own."""
        squatter = make_user("squatter@example.com")
        enter(squatter, "erp", "hub_owner")

        assert role_on(squatter, "erp") is None
        with pytest.raises(hub_jump.HubAccessDenied):
            hub_jump.issue_code(squatter, "erp")


class TestTwoBusinesses:
    def test_a_change_of_its_people_moves_its_photo_alone(self, platform_business, business, founder, make_user):
        before = version_of(business)
        member = add_member(platform_business, make_user("ana@example.com"), HubMember.Role.EMPLOYEE)

        member_management.member_change_role(ctx_for(founder), MemberRoleIn(id=member.id, role="hub_manager"))

        assert (version_of(platform_business), version_of(business)) == (2, before)

    def test_a_change_of_another_s_people_leaves_its_photo_alone(self, platform_business, business, owner, make_user):
        member = add_member(business, make_user("ana@example.com"), HubMember.Role.EMPLOYEE)

        member_management.member_change_role(ctx_for(owner), MemberRoleIn(id=member.id, role="hub_manager"))

        assert version_of(platform_business) == 1

    def test_its_owner_manages_nobody_of_another_business(self, platform_business, business, founder, make_user):
        member = add_member(business, make_user("ana@example.com"), HubMember.Role.EMPLOYEE)

        with pytest.raises(NotFound):
            member_management.member_remove(ctx_for(founder), ByIdIn(id=member.id))
        with pytest.raises(NotFound):
            invite(business, founder, "leo@example.com")

    def test_one_person_is_something_else_in_each(self, platform_business, business, owner):
        add_member(platform_business, owner, HubMember.Role.EMPLOYEE)

        assert (role_on(owner, "erp"), role_on(owner, business.slug)) == ("hub_employee", "hub_owner")
        assert SessionRevocation.objects.count() == 0


class TestItsOwnersAccount:
    def test_owning_it_takes_no_free_business(self, platform_business, founder):
        assert create_business(founder).slug == "bar-manolo"

    def test_it_holds_the_account_of_its_owner(self, platform_business, founder):
        owned, paid = account_businesses.businesses_holding(ctx_for(founder))

        assert (owned, paid) == ([{"id": str(platform_business.id), "name": "ERPlora", "is_platform": True}], [])

    def test_it_does_not_hold_the_account_of_another_member(self, platform_business, make_user):
        admin = make_user("ana@example.com")
        add_member(platform_business, admin, HubMember.Role.ADMIN)

        assert account_businesses.businesses_holding(ctx_for(admin)) == ([], [])

    def test_a_person_s_account_that_goes_leaves_its_photo(
        self, platform_business, make_user, hub_double, django_capture_on_commit_callbacks
    ):
        from hubs.services.account_changes import account_leaving

        admin = make_user("ana@example.com")
        add_member(platform_business, admin, HubMember.Role.ADMIN)

        with django_capture_on_commit_callbacks(execute=True):
            account_leaving(None, admin.pk)

        assert [m["email"] for m in hub_double.calls_to("PUT", "/state")[-1].body["members"]] == ["founder@example.com"]
        assert not HubMember.objects.filter(hub=platform_business, user=admin).exists()
        assert member_of(platform_business, platform_business.members.get().user)
