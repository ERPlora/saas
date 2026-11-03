"""Who enters a hub is read in one place: the answered members of the businesses that still open.

The jump (``accounts.services.issue_code``/``redeem_code``) reads them through ``hubs.member.list_mine``, by its name:
accounts never imports hubs. ``accounts.HubMembership``, the copy the jump read until saas#199, left the code: its table
stays until the contract step (``accounts/0011``), and the guardrail below keeps it out.
"""

import ast
from pathlib import Path

import pytest
from django.apps import apps
from live import operations
from live.errors import Unauthorized

from accounts import services as account_services
from hubs import queries, services
from hubs.models import Hub, HubMember
from hubs.schemas import ByIdIn, MemberListMineIn, MemberRoleIn, OwnershipTransferIn
from hubs.tests.conftest import add_member, create_business, ctx_for, member_of, role_on

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]


def mine(user):
    return [(row.slug, row.role) for row in queries.member_list_mine(ctx_for(user), MemberListMineIn()).rows]


class TestMemberListMine:
    """``hubs.member.list_mine``: the businesses an account enters, with its role on each."""

    def test_the_owner_sees_its_business_with_its_role(self, business, owner):
        assert mine(owner) == [(business.slug, "hub_owner")]

    @pytest.mark.parametrize(
        ("person", "role"), [("admin", "hub_admin"), ("manager", "hub_manager"), ("employee", "hub_employee")]
    )
    def test_each_member_carries_its_own_role(self, business, team, person, role):
        assert mine(team[person]) == [(business.slug, role)]

    def test_an_invitation_without_an_answer_enters_nothing(self, business, team):
        assert member_of(business, team["invitee"]).accepted_at is None
        assert mine(team["invitee"]) == []

    def test_a_stranger_enters_nothing(self, business, team):
        assert mine(team["stranger"]) == []

    @pytest.mark.parametrize("status", [Hub.Status.DELETING, Hub.Status.DELETED])
    def test_nobody_enters_a_deleted_business(self, business, owner, status):
        Hub.objects.filter(pk=business.pk).update(status=status)

        assert mine(owner) == []

    @pytest.mark.parametrize("status", [Hub.Status.PREPARING, Hub.Status.PAST_DUE, Hub.Status.SUSPENDED])
    def test_a_business_that_still_opens_lets_its_members_in(self, business, owner, status):
        Hub.objects.filter(pk=business.pk).update(status=status)

        assert mine(owner) == [(business.slug, "hub_owner")]

    def test_the_previous_address_gives_no_entry(self, business, owner):
        old = business.slug
        Hub.objects.filter(pk=business.pk).update(slug="casa-manolo", previous_slug=old)

        assert mine(owner) == [("casa-manolo", "hub_owner")]

    def test_several_businesses_come_by_address_each_with_its_role(self, business, owner, make_user):
        lola = make_user("lola@example.com")
        other = create_business(lola, name="Aaa Café")
        add_member(other, owner, "hub_employee")

        assert mine(owner) == sorted([(business.slug, "hub_owner"), (other.slug, "hub_employee")])

    def test_two_businesses_do_not_cross(self, business, owner, make_user):
        lola = make_user("lola@example.com")
        other = create_business(lola, name="Café Lola")

        assert mine(lola) == [(other.slug, "hub_owner")]
        assert mine(owner) == [(business.slug, "hub_owner")]

    def test_a_caller_without_an_account_is_refused(self):
        with pytest.raises(Unauthorized):
            queries.member_list_mine(ctx_for(None), MemberListMineIn())

    def test_it_is_reachable_by_name_as_a_read_without_a_route(self):
        operation = operations.get("hubs.member.list_mine")

        assert operation.meta.kind == "query"
        assert operation.meta.permission == "hubs.view"


class TestTheAccessFollowsTheMembersAtOnce:
    """No second copy to keep: each change of people is the jump's next answer."""

    def test_a_whole_member_lifecycle(self, business, team):
        owner, admin, manager, employee, invitee = (
            team["owner"],
            team["admin"],
            team["manager"],
            team["employee"],
            team["invitee"],
        )
        services.member_change_role(
            ctx_for(owner), MemberRoleIn(id=member_of(business, manager).id, role="hub_employee")
        )
        assert role_on(manager, business.slug) == "hub_employee"

        services.member_remove(ctx_for(admin), ByIdIn(id=member_of(business, employee).id))
        assert role_on(employee, business.slug) is None

        services.invitation_accept(ctx_for(invitee), ByIdIn(id=member_of(business, invitee).id))
        assert role_on(invitee, business.slug) is not None

        offer = services.ownership_transfer(
            ctx_for(owner), OwnershipTransferIn(hub_id=business.id, member_id=member_of(business, admin).id)
        )
        services.ownership_accept(ctx_for(admin), ByIdIn(id=offer.id))
        assert role_on(admin, business.slug) == "hub_owner"
        assert role_on(owner, business.slug) == "hub_admin"

        services.business_delete(ctx_for(admin), _delete_in(business))
        assert role_on(admin, business.slug) is None


def _delete_in(hub):
    from hubs.schemas import BusinessDeleteIn

    return BusinessDeleteIn(id=hub.id, confirm_name=hub.name)


class TestHubsWithMembers:
    """«Hubs» of the SaaS admin (``hubs.admin.hubs_view``): every business people enter, once, with how many."""

    def test_counts_the_members_that_enter_by_address(self, business, team, make_user):
        other = create_business(make_user("lola@example.com"), name="Aaa Café")

        # The invitee has not answered: four people enter ``business``.
        assert queries.hubs_with_members() == sorted([(business.slug, 4), (other.slug, 1)])

    def test_a_deleted_business_is_not_listed(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        assert queries.hubs_with_members() == []


# --- Guardrail: the retired copy stays out of the code ------------------------------------------------


def _production_files():
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        parts = relative.split("/")
        if parts[0] in {"packages", "node_modules", "tests", "frontend", "static"} or parts[0].startswith("."):
            continue
        if "tests" in parts or "migrations" in parts or "__pycache__" in parts:
            continue
        yield relative, path


def _names_the_retired_copy(tree) -> list[int]:
    """The lines of ``tree`` that use ``HubMembership`` as code; its name in prose is history, not a use."""
    found = []
    for node in ast.walk(tree):
        if (
            (isinstance(node, ast.Name) and node.id == "HubMembership")
            or (isinstance(node, ast.Attribute) and node.attr == "HubMembership")
            or (isinstance(node, ast.alias) and node.name == "HubMembership")
        ):
            found.append(node.lineno)
    return found


def test_no_production_code_uses_the_retired_copy():
    offenders = [
        f"{relative}:{line}"
        for relative, path in _production_files()
        for line in _names_the_retired_copy(ast.parse(path.read_text(), filename=relative))
    ]

    assert offenders == []


def test_the_guardrail_catches_an_import_a_use_and_an_attribute():
    """The positive: the lint sees what it must refuse, and leaves prose alone."""
    source = (
        "from accounts.models import HubMembership\n"
        "import accounts.models as m\n"
        "def f(user):\n"
        '    """HubMembership in a docstring is prose."""\n'
        "    HubMembership.objects.filter(user=user)\n"
        "    m.HubMembership.objects.all()\n"
    )

    assert _names_the_retired_copy(ast.parse(source)) == [1, 5, 6]


def test_the_model_is_gone_from_the_app_registry():
    with pytest.raises(LookupError):
        apps.get_model("accounts", "HubMembership")


# --- The demo businesses ----------------------------------------------------------------------------


class TestSeedDemoBusiness:
    """``hubs.services.seed_demo_business``: a hub that already runs in the local Hub (``a``, ``b``) becomes
    a business the SaaS knows, with its people, without provisioning it again."""

    def test_adopts_the_hub_as_an_active_ready_business_that_owes_the_hub_nothing(self, owner, make_user, plans):
        employee = make_user("employee@example.com")

        hub = services.seed_demo_business("a", {owner: "hub_owner", employee: "hub_employee"})

        assert (hub.slug, hub.name, hub.country, hub.status) == ("a", "a", "ES", "active")
        assert hub.ready_at is not None and hub.provision_requested_at is None
        assert (hub.pending_hub_call, hub.pushed_state_version) == ("", hub.state_version)
        assert sorted(HubMember.objects.filter(hub=hub).values_list("user__email", "role")) == [
            ("employee@example.com", "hub_employee"),
            ("owner@example.com", "hub_owner"),
        ]
        assert all(member.accepted_at for member in HubMember.objects.filter(hub=hub))
        assert hub.subscription.plan.slug == "free"

    def test_running_it_again_changes_nothing(self, owner, plans):
        first = services.seed_demo_business("a", {owner: "hub_owner"})
        again = services.seed_demo_business("a", {owner: "hub_owner"})

        assert again.pk == first.pk
        assert (Hub.objects.count(), HubMember.objects.count()) == (1, 1)

    def test_a_business_the_panel_created_keeps_its_people(self, business, owner, make_user):
        ana = make_user("ana@example.com")

        services.seed_demo_business(business.slug, {ana: "hub_employee"})

        assert member_of(business, ana).role == "hub_employee"
        assert member_of(business, owner).role == "hub_owner"

    def test_a_customer_role_only(self, owner, plans):
        with pytest.raises(ValueError):
            services.seed_demo_business("a", {owner: "platform_admin"})

        assert not Hub.objects.exists()


def test_the_seeded_member_enters_through_the_jump(owner, plans):
    """The members are what the jump reads: a seeded owner gets a code for its hub."""
    services.seed_demo_business("a", {owner: "hub_owner"})

    identity = account_services.redeem_code(account_services.issue_code(owner, "a"), "a")

    assert identity.role == "hub_owner"


class TestTheJumpReadsTheMembers:
    """The jump end to end, through the name of the operation."""

    def test_a_stranger_gets_no_code(self, business, team):
        with pytest.raises(account_services.HubAccessDenied):
            account_services.issue_code(team["stranger"], business.slug)

    def test_an_invitee_gets_no_code(self, business, team):
        with pytest.raises(account_services.HubAccessDenied):
            account_services.issue_code(team["invitee"], business.slug)

    def test_a_member_of_another_business_gets_no_code(self, business, owner, make_user):
        lola = make_user("lola@example.com")
        create_business(lola, name="Café Lola")

        with pytest.raises(account_services.HubAccessDenied):
            account_services.issue_code(lola, business.slug)

    def test_a_code_does_not_outlive_the_member(self, business, team):
        code = account_services.issue_code(team["employee"], business.slug)
        services.member_remove(ctx_for(team["admin"]), ByIdIn(id=member_of(business, team["employee"]).id))

        with pytest.raises(account_services.InvalidCode):
            account_services.redeem_code(code, business.slug)

    def test_a_code_does_not_outlive_the_business(self, business, owner):
        code = account_services.issue_code(owner, business.slug)
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(account_services.InvalidCode):
            account_services.redeem_code(code, business.slug)

    def test_the_old_address_gets_no_code_after_a_move(self, business, owner):
        old = business.slug
        Hub.objects.filter(pk=business.pk).update(slug="casa-manolo", previous_slug=old)

        with pytest.raises(account_services.HubAccessDenied):
            account_services.issue_code(owner, old)
        assert account_services.issue_code(owner, "casa-manolo")
