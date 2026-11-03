"""``accounts.HubMembership`` mirrors the answered members of every business (plan 2026-10-13, L1-A2).

The jump to a hub (``accounts.services.issue_code``/``redeem_code``) still reads the access in
``HubMembership``; ``HubMember`` is the source of truth. Until the jump moves to ``hubs`` and the mirror is
retired, ``hubs.services.sync_access`` is its only writer (guardrail below) and
``hubs.queries.verify_access_mirror`` says where the two disagree: a ``manage.py check --database default``
warning (``hubs.W001``) and these tests.
"""

import ast
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from accounts.models import HubMembership
from hubs import queries, services
from hubs.models import Hub, HubMember
from hubs.schemas import ByIdIn, MemberRoleIn, OwnershipTransferIn
from hubs.tests.conftest import add_member, create_business, ctx_for, member_of

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]


def drift():
    return queries.verify_access_mirror()


class TestVerifyAccessMirror:
    def test_a_business_and_its_team_agree(self, business, team):
        assert drift() == []

    def test_a_whole_member_lifecycle_keeps_them_agreeing(self, business, team):
        owner, admin = team["owner"], team["admin"]
        services.member_change_role(
            ctx_for(owner),
            MemberRoleIn(
                id=member_of(business, team["manager"]).id, role="hub_employee"
            ),
        )
        services.member_remove(
            ctx_for(admin), ByIdIn(id=member_of(business, team["employee"]).id)
        )
        services.invitation_accept(
            ctx_for(team["invitee"]), ByIdIn(id=member_of(business, team["invitee"]).id)
        )
        offer = services.ownership_transfer(
            ctx_for(owner),
            OwnershipTransferIn(
                hub_id=business.id, member_id=member_of(business, admin).id
            ),
        )
        services.ownership_accept(ctx_for(admin), ByIdIn(id=offer.id))
        assert drift() == []

        services.business_delete(ctx_for(admin), _delete_in(business))
        assert drift() == []

    def test_a_slug_without_a_business_is_reported(self, owner):
        HubMembership.objects.create(user=owner, hub_slug="seed-hub", role="hub_owner")

        assert drift() == [("seed-hub", str(owner.pk), None, "hub_owner")]

    def test_a_missing_mirror_row_is_reported(self, business, owner):
        HubMembership.objects.filter(hub_slug=business.slug).delete()

        assert drift() == [(business.slug, str(owner.pk), "hub_owner", None)]

    def test_another_role_is_reported(self, business, owner):
        HubMembership.objects.filter(hub_slug=business.slug).update(role="hub_employee")

        assert drift() == [(business.slug, str(owner.pk), "hub_owner", "hub_employee")]

    def test_an_invitation_has_no_access_to_mirror(self, business, team):
        HubMembership.objects.create(
            user=team["invitee"], hub_slug=business.slug, role="hub_employee"
        )

        assert drift() == [
            (business.slug, str(team["invitee"].pk), None, "hub_employee")
        ]

    def test_nobody_has_access_to_a_deleted_business(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        assert drift() == [(business.slug, str(owner.pk), None, "hub_owner")]


def _delete_in(hub):
    from hubs.schemas import BusinessDeleteIn

    return BusinessDeleteIn(id=hub.id, confirm_name=hub.name)


# --- Guardrail: ``sync_access`` is the only writer of the mirror ----------------------------------

#: The calls that write rows through a queryset, a manager or an instance.
WRITES = {
    "create",
    "get_or_create",
    "update_or_create",
    "bulk_create",
    "bulk_update",
    "update",
    "delete",
    "save",
}
#: The one function allowed to write ``HubMembership`` outside migrations and tests.
ALLOWED = {("hubs/services.py", "sync_access")}


def _production_files():
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        parts = relative.split("/")
        if parts[0] in {
            "packages",
            "node_modules",
            "tests",
            "frontend",
            "static",
        } or parts[0].startswith("."):
            continue
        if "tests" in parts or "migrations" in parts or "__pycache__" in parts:
            continue
        yield relative, path


def _mentions_mirror(node, tainted: set[str]) -> bool:
    return any(
        (
            isinstance(child, ast.Name)
            and (child.id == "HubMembership" or child.id in tainted)
        )
        for child in ast.walk(node)
    )


def _mirror_writes(tree):
    """``(function, line)`` of every write whose receiver comes from ``HubMembership``."""
    found = []
    for function in [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]:
        tainted: set[str] = set()
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and _mentions_mirror(node.value, tainted):
                tainted |= {
                    target.id for target in node.targets if isinstance(target, ast.Name)
                }
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in WRITES
                and _mentions_mirror(node.func.value, tainted)
            ):
                found.append((function.name, node.lineno))
    return found


def test_only_sync_access_writes_the_mirror():
    offenders = [
        f"{relative}:{line} ({function})"
        for relative, path in _production_files()
        for function, line in _mirror_writes(
            ast.parse(path.read_text(), filename=relative)
        )
        if (relative, function) not in ALLOWED
    ]

    assert offenders == []


def test_the_guardrail_catches_a_write_through_a_queryset_variable():
    """The positive: the lint sees what it must refuse."""
    source = (
        "def seed(user):\n"
        "    rows = HubMembership.objects.filter(user=user)\n"
        "    rows.exclude(hub_slug='a').delete()\n"
        "    HubMembership.objects.get_or_create(user=user, hub_slug='b')\n"
        "    user.save()\n"
    )

    assert _mirror_writes(ast.parse(source)) == [("seed", 3), ("seed", 4)]


def test_the_admin_of_the_mirror_writes_nothing(admin_client_factory):
    """Staff change people on the business (``hubs`` admin, ``HubMember``); the mirror is only seen."""
    from django.contrib import admin

    from accounts.admin import HubMembershipInline

    request = admin_client_factory()
    model_admin = admin.site._registry[HubMembership]
    inline = HubMembershipInline(HubMembership, admin.site)

    assert not model_admin.has_add_permission(request)
    assert not inline.has_add_permission(request, None)
    for each in (model_admin, inline):
        assert not each.has_change_permission(request, None)
        assert not each.has_delete_permission(request, None)
    assert model_admin.has_view_permission(request, None)


@pytest.fixture
def admin_client_factory(rf):
    from django.contrib.auth import get_user_model

    def make():
        request = rf.get("/admin/")
        request.user = get_user_model().objects.create_superuser(
            email="root@example.com", password=None
        )
        return request

    return make


# --- The demo businesses ----------------------------------------------------------------------------


class TestSeedDemoBusiness:
    """``hubs.services.seed_demo_business``: a hub that already runs in the local Hub (``a``, ``b``) becomes
    a business the SaaS knows, with its people, without provisioning it again."""

    def test_adopts_the_hub_as_an_active_ready_business_that_owes_the_hub_nothing(
        self, owner, make_user, plans
    ):
        employee = make_user("employee@example.com")

        hub = services.seed_demo_business(
            "a", {owner: "hub_owner", employee: "hub_employee"}
        )

        assert (hub.slug, hub.name, hub.country, hub.status) == (
            "a",
            "a",
            "ES",
            "active",
        )
        assert hub.ready_at is not None and hub.provision_requested_at is None
        assert (hub.pending_hub_call, hub.pushed_state_version) == (
            "",
            hub.state_version,
        )
        assert sorted(
            HubMember.objects.filter(hub=hub).values_list("user__email", "role")
        ) == [
            ("employee@example.com", "hub_employee"),
            ("owner@example.com", "hub_owner"),
        ]
        assert all(member.accepted_at for member in HubMember.objects.filter(hub=hub))
        assert hub.subscription.plan.slug == "free"
        assert drift() == []

    def test_running_it_again_changes_nothing(self, owner, plans):
        first = services.seed_demo_business("a", {owner: "hub_owner"})
        again = services.seed_demo_business("a", {owner: "hub_owner"})

        assert again.pk == first.pk
        assert (
            Hub.objects.count(),
            HubMember.objects.count(),
            HubMembership.objects.count(),
        ) == (1, 1, 1)

    def test_a_business_the_panel_created_keeps_its_people(
        self, business, owner, make_user
    ):
        ana = make_user("ana@example.com")

        services.seed_demo_business(business.slug, {ana: "hub_employee"})

        assert member_of(business, ana).role == "hub_employee"
        assert member_of(business, owner).role == "hub_owner"
        assert drift() == []

    def test_a_customer_role_only(self, owner, plans):
        with pytest.raises(ValueError):
            services.seed_demo_business("a", {owner: "platform_admin"})

        assert not Hub.objects.exists()


def test_the_seeded_member_enters_through_the_jump(owner, plans):
    """The mirror is what the jump reads: a seeded owner gets a code for its hub."""
    from accounts import services as account_services

    services.seed_demo_business("a", {owner: "hub_owner"})

    identity = account_services.redeem_code(
        account_services.issue_code(owner, "a"), "a"
    )
    assert identity.role == "hub_owner"


def test_add_member_of_the_tests_keeps_the_mirror(business, owner, make_user):
    add_member(business, make_user("ana@example.com"), "hub_manager")

    assert drift() == []


def test_a_second_business_does_not_disturb_the_first(business, owner, make_user):
    create_business(make_user("lola@example.com"), name="Café Lola")

    assert drift() == []
