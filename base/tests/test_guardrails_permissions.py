"""Guardrail of the permissions of the SaaS (W11b, phase 2; ARCHITECTURE.md §4 «Un solo camino»; Ioan, 2026-10-31).
The Hub's twin is its ``tests/test_guardrails_permissions.py`` (hub#490).

``live.operations.Operation`` checks ``ctx.has(op.permission)`` before it runs, and ``OperationContext.has(None)`` is
``True``: an ``@operation(..., permission=None)`` runs for every signed-in account and, on a route with ``auth=None``,
for anybody. Here every operation of the SaaS without one must be in :data:`OPEN_OPERATIONS`, closed and with its
reason; what the list names must still exist and still be open, so it never rots; none of them writes; what is public
reads nothing of who asks; and what is the caller's own tells an anonymous visitor nothing.

A signed-in account holds the role ``account`` (``base.operations``), whoever it is: the panel's permissions,
:data:`ACCOUNT_PERMISSIONS`, closed as well. Every other permission is the platform's (the admin's ``staff_context``,
the ``/internal`` doors, the commands and the workers): what asks for one refuses an account, and the staff's account
alike, since the panel gives the staff no more than anybody. What only the platform runs, though an account may hold
its permission, refuses anybody but ``"system"`` itself, first (:data:`SYSTEM_ONLY`), or anybody but ``"system"`` and
the staff holding a permission of the admin (:data:`SYSTEM_OR_STAFF`).

The last part pins that ERPlora's staff (``is_staff``/``is_superuser``: maintenance and support, in the admin at
``erplora.com/admin``) is no customer: only the platform's own doors set those flags, no operation takes them and the
sign-up ignores them. Already pinned elsewhere, not repeated here:

- the admin is the staff's alone: ``accounts/tests/test_admin.py`` (``TestWhoEntersTheAdmin``: no customer role enters,
  an owner is sent to the admin's login and cannot sign in there);
- a customer is never made staff: ``accounts/tests/test_create_platform_user.py``
  (``test_a_customer_of_a_hub_is_never_turned_into_platform_staff``) and ``accounts/tests/test_models.py``
  (``TestUser::test_signs_in_with_the_email_and_has_a_uuid7_primary_key``: a new account is no staff);
- a staff account never joins a business: ``hubs/tests/test_services.py`` (``test_a_staff_account_creates_no_business``),
  ``hubs/tests/test_invite_unverified_account.py`` (``test_a_staff_account_is_never_invited_and_keeps_its_password``)
  and ``hubs/tests/test_members.py``
  (``TestAccept::test_an_account_made_staff_while_invited_cannot_enter_with_the_invitation``).
"""

import ast
import inspect
import textwrap
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import RequestFactory
from live.context import OperationContext, Scope
from live.errors import PermissionDenied, Unauthorized
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import registry

from base.operations import ACCOUNT_ROLE, UserContextBuilder

# ── Why an operation may have no permission ───────────────────────────────────────────────────────────────────────

#: ERPlora's public catalogue and pages, read by anonymous visitors (``auth=None``): nothing of any account.
PUBLIC = "public"
#: What the caller's own session or account says about itself, and nothing about anybody else.
OWN_ACCOUNT = "own account"

#: Every operation of the SaaS without a permission, with its reason: ``name → (kind, why)``. Closed on purpose: a new
#: one is either given its permission or added here with a reason a reviewer can weigh.
OPEN_OPERATIONS: dict[str, tuple[str, str]] = {
    "accounts.hub.list": (
        OWN_ACCOUNT,
        "The signed-in account's own businesses and the jump to each; an anonymous caller is refused (401).",
    ),
    "apps.app.doc": (PUBLIC, "A listed app's user documentation, the store's public page."),
    "apps.app.get": (PUBLIC, "A listed app's page in the public store (/apps/)."),
    "apps.app.list": (PUBLIC, "The public store's listed apps (/apps/, the landing, the industry pages)."),
    "apps.app.sitemap": (PUBLIC, "The listed apps' pages for /sitemap.xml."),
    "apps.doc.list": (
        PUBLIC,
        "Every listed app's user documentation, the same the store's pages publish, for the assistant's index "
        "(assistant.knowledge).",
    ),
    "base.session.me": (
        OWN_ACCOUNT,
        "The SPA's own session, read at start: an anonymous visitor gets no user, no permission and no menu (the "
        "login).",
    ),
    "hubs.business_type.list": (PUBLIC, "The types of business of each sector: the sign-up and /industries/."),
    "hubs.plan.list": (PUBLIC, "The plans on sale and their prices: /pricing/ and the sign-up, never an internal one."),
    "hubs.sector.list": (PUBLIC, "The sectors a business can belong to: the sign-up and /industries/."),
    "public.app.release": (PUBLIC, "The native app's latest version, asked anonymously by the installed app."),
}

KINDS = frozenset({PUBLIC, OWN_ACCOUNT})

#: What every signed-in account holds in the panel (role ``account``): its own profile, sessions and keys, its
#: businesses, their billing, the fiscal status and its assistant. Closed on purpose: one of the platform's
#: (``assistant.manage``, ``billing.manage``, ``fiscal.manage``, ``whatsapp.manage``, or one no app declares)
#: given to ``account`` would open it to every customer.
ACCOUNT_PERMISSIONS = frozenset(
    {
        "accounts.manage",
        "accounts.view",
        "assistant.ask",
        "billing.pay",
        "billing.vat_check",
        "billing.view",
        "fiscal.view",
        "hubs.manage",
        "hubs.view",
    }
)

#: What the platform alone runs (the Hub's doors, the commands, the workers, as ``"system"``): each refuses any other
#: actor itself, first, whatever permissions it holds. Six of them ask for a permission every account holds
#: (``hubs.manage``): that refusal is all that stands between them and a customer.
SYSTEM_ONLY = frozenset(
    {
        "assistant.caller.resolve",
        "assistant.credential.import",
        "assistant.docs.index",
        "assistant.docs.list",
        "assistant.encryption.rotate",
        "assistant.message.claim",
        "assistant.message.release",
        "assistant.report.send",
        "assistant.service.connection",
        "assistant.usage.record",
        "fiscal.representation.notify",
        "fiscal.representation.submit",
        "hubs.business.age_suspension",
        "hubs.business.mark_ready",
        "hubs.business.notify_people",
        "hubs.business.record_hub_error",
        "hubs.subscription.apply",
        "hubs.usage.record",
    }
)

#: What the platform runs, and the staff in the admin with one of its model permissions besides
#: (``assistant.queries.staff_with``): ``name → the admin's permission``. A customer never holds it.
SYSTEM_OR_STAFF = {
    "assistant.route.resolve": "assistant.change_airoutingpolicy",  # the staff try a model before choosing it
    "assistant.usage.show": "assistant.view_assistantusage",  # the staff read what a business spent
}

HOW_TO_FIX = (
    "Give each the permission its callers must hold (`permission=\"<app>.<action>\"`, declared in the app's "
    "`permissions` and, if every account may run it, granted to the role `account` in its `role_permissions`). Only "
    "if anybody signed in, or the public, may run it on purpose, add it to OPEN_OPERATIONS in "
    "base/tests/test_guardrails_permissions.py with its kind and its reason."
)


def open_in_the_registry() -> set[str]:
    return {name for name, op in registry.items() if op.permission is None}


def of_kind(kind: str) -> list[str]:
    return sorted(name for name, (listed_kind, _) in OPEN_OPERATIONS.items() if listed_kind == kind)


def of_the_platform() -> list[str]:
    """The operations whose permission no account holds."""
    return sorted(
        name for name, op in registry.items() if op.permission is not None and op.permission not in ACCOUNT_PERMISSIONS
    )


def body_of(fn) -> ast.FunctionDef:
    return ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]


def reads_who_asks(fn) -> list[str]:
    """What of the caller ``fn`` reads from its context: ``ctx.actor``, ``ctx.permissions``, ``ctx.request``."""
    return sorted(
        {
            ast.unparse(node)
            for node in ast.walk(body_of(fn))
            if isinstance(node, ast.Attribute)
            and node.attr in {"actor", "permissions", "request", "has"}
            and isinstance(node.value, ast.Name)
            and node.value.id == "ctx"
        }
    )


def refuses_all_but_the_system(fn) -> bool:
    """Whether ``fn`` compares its actor with ``"system"`` or calls ``platform_only``: the platform's own refusal."""
    for node in ast.walk(body_of(fn)):
        if (
            isinstance(node, ast.Compare)
            and ast.unparse(node.left) == "ctx.actor"
            and any(isinstance(c, ast.Constant) and c.value == "system" for c in node.comparators)
        ):
            return True
        if isinstance(node, ast.Call) and ast.unparse(node.func).split(".")[-1] == "platform_only":
            return True
    return False


# ── The inventory of what runs without a permission ───────────────────────────────────────────────────────────────


def test_every_operation_without_a_permission_is_listed_with_its_reason():
    unlisted = sorted(open_in_the_registry() - OPEN_OPERATIONS.keys())
    assert not unlisted, (
        f"These operations run for any signed-in account (or anybody, on a public route): {unlisted}. " + HOW_TO_FIX
    )


def test_the_list_names_only_operations_that_exist_and_are_still_open():
    gone = sorted(name for name in OPEN_OPERATIONS if name not in registry)
    closed = sorted(name for name in OPEN_OPERATIONS if name in registry and registry[name].permission is not None)
    assert not gone, f"OPEN_OPERATIONS names operations that no longer exist: {gone}. Take them out of the list."
    assert not closed, f"These operations have a permission now: {closed}. Take them out of OPEN_OPERATIONS."


def test_every_reason_says_its_kind_and_why():
    for name, (kind, why) in OPEN_OPERATIONS.items():
        assert kind in KINDS, f"{name}: {kind!r} is no kind of reason ({sorted(KINDS)})."
        assert why.strip(), f"{name}: say why it needs no permission."


def test_nothing_writes_without_a_permission():
    # In the SaaS even the platform's own commands ask for a permission no account holds.
    writes = sorted(name for name in OPEN_OPERATIONS if name in registry and registry[name].kind != "query")
    assert not writes, f"These commands would let any account, or anybody, write: {writes}. " + HOW_TO_FIX


@pytest.mark.parametrize("name", of_kind(PUBLIC))
def test_what_is_public_reads_nothing_of_who_asks(name):
    # The same page for a visitor, a customer and the staff: what it shows never depends on who reads it.
    read = reads_who_asks(registry[name].fn)
    assert not read, f"{name} is public but reads {read}: give it a permission, or move it to OWN_ACCOUNT."


def anonymous_context() -> OperationContext:
    request = RequestFactory().get("/api/session/me")
    request.user = AnonymousUser()
    return UserContextBuilder().from_request(request)


@pytest.mark.django_db
def test_what_is_the_caller_s_own_tells_an_anonymous_visitor_nothing():
    assert of_kind(OWN_ACCOUNT) == ["accounts.hub.list", "base.session.me"], (
        "Say here what a new operation of the caller's own answers to an anonymous visitor."
    )
    anonymous = anonymous_context()
    hubs = registry["accounts.hub.list"]
    with pytest.raises(Unauthorized):
        hubs(anonymous, hubs.input())

    session = registry["base.session.me"]
    me = session(anonymous, session.input())
    assert (me.user, me.permissions, me.menu) == (None, [], [])


def test_the_scan_of_who_asks_catches_its_positive():
    def public(ctx, data):
        return {"plans": ctx.language}

    def by_who(ctx, data):
        return {"plans": ctx.actor.is_staff and ctx.has("x")}

    assert (reads_who_asks(public), reads_who_asks(by_who)) == ([], ["ctx.actor", "ctx.has"])


# ── What the platform alone runs ──────────────────────────────────────────────────────────────────────────────────


def test_an_account_holds_the_panel_s_permissions_and_nothing_else():
    held = permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE)
    assert held == ACCOUNT_PERMISSIONS, (
        f"Every signed-in account now holds {sorted(held - ACCOUNT_PERMISSIONS)} and no longer "
        f"{sorted(ACCOUNT_PERMISSIONS - held)}. A permission of the panel goes into ACCOUNT_PERMISSIONS; one of the "
        "platform's never goes to the role `account`."
    )


def panel_context(user) -> OperationContext:
    """The context the panel builds for ``user`` from its request (``settings.LIVE["context_builder"]``)."""
    request = RequestFactory().get("/api/session/me")
    request.user = user
    return UserContextBuilder().from_request(request)


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user(email="customer@example.com", password=None)


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(
        email="root@erplora.com", password=None, is_staff=True, is_superuser=True
    )


@pytest.fixture
def support(db):
    helper = get_user_model().objects.create_user(email="help@erplora.com", password=None, is_staff=True)
    helper.groups.add(Group.objects.get(name="support"))
    return helper


def test_the_platform_s_operations_are_there_to_refuse():
    # The parametrised test below would pass with none at all.
    assert len(of_the_platform()) > 40


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["customer", "staff"])
@pytest.mark.parametrize("name", of_the_platform())
def test_what_asks_for_a_platform_permission_refuses_an_account_and_the_staff_s_alike(name, who, request):
    op = registry[name]
    with pytest.raises(PermissionDenied) as refused:
        op(panel_context(request.getfixturevalue(who)), op.input.model_construct())
    assert refused.value.code == "permission_denied"  # live's own check, before the operation's body


def test_what_refuses_all_but_the_system_is_listed():
    listed = SYSTEM_ONLY | SYSTEM_OR_STAFF.keys()
    detected = sorted(name for name, op in registry.items() if refuses_all_but_the_system(op.fn))
    unlisted = sorted(set(detected) - listed)
    gone = sorted(listed - registry.keys())
    assert not SYSTEM_ONLY & SYSTEM_OR_STAFF.keys()
    assert not unlisted, f"Add these to SYSTEM_ONLY or SYSTEM_OR_STAFF, so that their refusal is tested: {unlisted}."
    assert not gone, f"These lists name operations that no longer exist: {gone}. Take them out."


def holding_everything(user) -> OperationContext:
    """``user`` holding every permission there is: ``*`` passes live's check, so what refuses is the operation."""
    return OperationContext(scope=Scope("user", str(user.pk)), actor=user, permissions=frozenset({"*"}))


def refused_by_itself(name: str, ctx: OperationContext) -> str:
    op = registry[name]
    with pytest.raises(PermissionDenied) as refused:
        op(ctx, op.input.model_construct())
    assert refused.value.code != "permission_denied"  # the operation's own refusal, first
    return refused.value.code


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(SYSTEM_ONLY | SYSTEM_OR_STAFF.keys()))
def test_what_only_the_platform_runs_refuses_a_customer_holding_every_permission(name, customer):
    refused_by_itself(name, holding_everything(customer))


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(SYSTEM_ONLY))
def test_what_the_system_alone_runs_refuses_even_the_staff_s_superuser(name, staff):
    refused_by_itself(name, holding_everything(staff))


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(SYSTEM_OR_STAFF))
def test_the_staff_need_the_admin_s_permission_besides(name, support):
    # The positive side (the staff with it, and the platform) is the assistant's own tests.
    assert not support.has_perm(SYSTEM_OR_STAFF[name])
    assert refused_by_itself(name, holding_everything(support)) == "assistant.staff_only"


def test_the_scan_of_the_system_s_refusal_catches_its_positive():
    def compares(ctx, data):
        if ctx.actor != "system":
            raise PermissionDenied("no")

    def calls(ctx, data):
        queries.platform_only(ctx)  # noqa: F821 (only parsed)

    def neither(ctx, data):
        return ctx.actor

    assert [refuses_all_but_the_system(fn) for fn in (compares, calls, neither)] == [True, True, False]


# ── ERPlora's staff is no customer ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_panel_gives_the_staff_what_it_gives_any_account(customer, staff, support):
    for user in (customer, staff, support):
        held = panel_context(user).permissions
        assert held == ACCOUNT_PERMISSIONS, f"{user.email} holds {sorted(held)} in the panel."
        assert "*" not in held


#: The flags only the platform sets.
STAFF_FLAGS = frozenset({"is_staff", "is_superuser"})
#: Where they may be set: ``createsuperuser`` and ``manage.py create_platform_user`` (the platform's ``admin`` and
#: ``support``). The admin's user form sets them too, for a superuser of the staff alone (Django's own fields).
STAFF_DOORS = frozenset({("accounts/models.py", "create_superuser"), ("accounts/services.py", "create_platform_user")})
#: Calls that read the flags (``filter(is_staff=True)``) rather than write them.
READS = frozenset({"filter", "exclude", "get", "first", "exists", "count"})
CODE_DIRS = ("accounts", "apps", "assistant", "base", "billing", "config", "fiscal", "fiscal_gateway", "hubs", "public",
             "whatsapp")


def sets_a_staff_flag(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return any(isinstance(t, ast.Attribute) and t.attr in STAFF_FLAGS for t in targets)
    if not isinstance(node, ast.Call):
        return False
    called = ast.unparse(node.func).split(".")[-1]
    if called in {"setattr", "setdefault"}:
        return any(isinstance(a, ast.Constant) and a.value in STAFF_FLAGS for a in node.args[:2])
    return called not in READS and any(kw.arg in STAFF_FLAGS for kw in node.keywords)


def staff_flags_set_in(source: str) -> list[tuple[str, int]]:
    """``(function, line)`` of every place in ``source`` that sets a staff flag."""
    found = []

    def visit(node: ast.AST, function: str) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            function = node.name
        if sets_a_staff_flag(node):
            found.append((function, node.lineno))
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(ast.parse(source), "<module>")
    return found


def test_only_the_platform_s_doors_set_the_staff_flags():
    root = Path(settings.BASE_DIR)
    found = []
    for directory in CODE_DIRS:
        for path in sorted((root / directory).rglob("*.py")):
            if {"tests", "migrations"} & set(path.parts):
                continue
            relative = path.relative_to(root).as_posix()
            found += [
                f"{relative}:{line} ({function})"
                for function, line in staff_flags_set_in(path.read_text())
                if (relative, function) not in STAFF_DOORS
            ]
    assert not found, (
        f"These make an account staff or superuser outside the platform's doors: {found}. A customer never becomes "
        "staff: the platform's staff is made by `manage.py create_platform_user`."
    )


def test_the_scan_of_the_staff_flags_catches_its_positive():
    source = textwrap.dedent(
        """
        def raise_it(user):
            user.is_superuser = True
        def make(email):
            return User.objects.create_user(email=email, is_staff=True)
        def flag(user):
            setattr(user, "is_staff", True)
        def reads(users):
            return users.filter(is_staff=True).exclude(is_superuser=True)
        """
    )
    assert [function for function, _ in staff_flags_set_in(source)] == ["raise_it", "make", "flag"]


def fields_of(schema: dict) -> set[str]:
    """Every property name in a JSON schema, nested models included."""
    names = set()
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            names |= set(value)
        if isinstance(value, dict):
            names |= fields_of(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    names |= fields_of(item)
    return names


def test_no_operation_takes_the_staff_flags():
    taking = sorted(
        name
        for name, op in registry.items()
        if fields_of(op.input.model_json_schema()) & (STAFF_FLAGS | {"groups", "user_permissions"})
    )
    assert not taking, f"These operations take the platform's flags from their caller: {taking}."


@pytest.mark.django_db
def test_signing_up_never_makes_staff_whatever_the_request_says(client):
    response = client.post(
        "/_allauth/browser/v1/auth/signup",
        {
            "email": "new@example.com",
            "password": "a long pass phrase 2026",
            "is_staff": True,
            "is_superuser": True,
            "groups": ["support"],
        },
        content_type="application/json",
        HTTP_HOST="localhost:8001",
    )

    user = get_user_model().objects.get(email="new@example.com")  # the sign-up went through
    assert response.status_code == 401, response.content  # it waits for the mailed code (verify_email)
    assert (user.is_staff, user.is_superuser, user.groups.exists()) == (False, False, False)
