"""The migrations of hubs are reversible and match the models.

The round trip runs inside the test's transaction (Postgres DDL is transactional), so it leaves the
test database as it found it.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

HUBS_TABLES = {
    "hubs_plan",
    "hubs_sector",
    "hubs_businesstype",
    # The account plane of a business (0002).
    "hubs_billingprofile",
    "hubs_hub",
    "hubs_hubmember",
    "hubs_hubownershiptransfer",
    "hubs_subscription",
    "hubs_subscriptionitem",
    # The usage of each business, day by day (0010, L4-A).
    "hubs_hubusagedaily",
}


def _tables():
    return set(connection.introspection.table_names())


def test_every_operation_of_hubs_can_be_reversed():
    migrations = [m for (app, _), m in MigrationLoader(None, ignore_no_migrations=True).disk_migrations.items() if app == "hubs"]

    assert migrations
    assert all(operation.reversible for migration in migrations for operation in migration.operations)


@pytest.mark.django_db
def test_hubs_migrates_to_zero_and_back():
    call_command("migrate", "hubs", "zero", verbosity=0)
    assert _tables().isdisjoint(HUBS_TABLES)

    call_command("migrate", "hubs", verbosity=0)
    assert HUBS_TABLES <= _tables()


@pytest.mark.django_db
def test_the_models_and_the_migrations_agree():
    """``makemigrations --check`` exits non-zero when a model changed without its migration."""
    call_command("makemigrations", "hubs", "--check", "--dry-run", verbosity=0)


# --- 0006: the hubs of the phase-1 seed become businesses (plan 2026-10-13, L1-A2) -----------------

from datetime import timedelta  # noqa: E402
from importlib import import_module  # noqa: E402

from django.apps import apps as global_apps  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

ADOPTION = "0006_adopt_seed_hubs"


def _adoption():
    return import_module(f"hubs.migrations.{ADOPTION}")


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _adopt():
    _adoption().adopt_seed_hubs(global_apps, _SchemaEditor())


@pytest.mark.django_db
class TestTheSeedHubsBecomeBusinesses:
    @pytest.fixture
    def people(self):
        make = get_user_model().objects.create_user
        return {
            "olga": make(email="olga@example.com", password=None, language="es"),
            "eva": make(email="eva@example.com", password=None),
            "ana": make(email="ana@example.com", password=None),
        }

    def _membership(self, user, slug, role, days_ago=0):
        from accounts.models import HubMembership

        return HubMembership.objects.create(
            user=user, hub_slug=slug, role=role, created_at=timezone.now() - timedelta(days=days_ago)
        )

    def test_a_seed_hub_becomes_an_active_ready_business_that_owes_the_hub_nothing(self, people, plans):
        from hubs.models import Hub, HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner", days_ago=2)
        self._membership(people["eva"], "bar-pepe", "hub_employee", days_ago=1)

        _adopt()

        hub = Hub.objects.get(slug="bar-pepe")
        assert (hub.name, hub.country, hub.language, hub.status) == ("bar-pepe", "ES", "es", "active")
        assert hub.ready_at is not None and hub.provision_requested_at is None
        assert (hub.pending_hub_call, hub.pushed_state_version, hub.state_version) == ("", 1, 1)
        members = {m.user.email: m for m in HubMember.objects.filter(hub=hub).select_related("user")}
        assert {email: m.role for email, m in members.items()} == {
            "olga@example.com": "hub_owner",
            "eva@example.com": "hub_employee",
        }
        assert all(m.accepted_at == m.joined_at for m in members.values())
        assert hub.subscription.plan.slug == "free"

    def test_without_the_free_plan_seeded_there_is_no_subscription(self, people):
        from hubs.models import Hub, Subscription

        self._membership(people["olga"], "bar-pepe", "hub_owner")

        _adopt()

        assert not Subscription.objects.filter(hub=Hub.objects.get(slug="bar-pepe")).exists()

    def test_without_an_owner_the_oldest_member_becomes_it_in_both_tables(self, people):
        from accounts.models import HubMembership
        from hubs.models import HubMember

        self._membership(people["ana"], "bar-pepe", "hub_employee", days_ago=1)
        self._membership(people["eva"], "bar-pepe", "hub_admin", days_ago=5)

        _adopt()

        assert HubMember.objects.get(user=people["eva"]).role == "hub_owner"
        assert HubMembership.objects.get(user=people["eva"]).role == "hub_owner"
        assert HubMember.objects.get(user=people["ana"]).role == "hub_employee"

    def test_two_owners_keep_the_oldest_and_the_other_becomes_admin(self, people):
        from accounts.models import HubMembership
        from hubs.models import HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner", days_ago=3)
        self._membership(people["eva"], "bar-pepe", "hub_owner", days_ago=1)

        _adopt()

        assert HubMember.objects.get(user=people["olga"]).role == "hub_owner"
        assert HubMember.objects.get(user=people["eva"]).role == "hub_admin"
        assert HubMembership.objects.get(user=people["eva"]).role == "hub_admin"

    @pytest.mark.parametrize("slug", ["www", "hubs", "-bad-", "xn--abc"])
    def test_a_slug_that_is_no_hubs_gives_no_business_and_its_dead_rows_go(self, people, slug):
        """``is_hub_slug`` already refused them at the jump: they opened nothing."""
        from accounts.models import HubMembership
        from hubs.models import Hub

        self._membership(people["olga"], slug, "hub_owner")

        _adopt()

        assert not Hub.objects.exists()
        assert not HubMembership.objects.exists()

    def test_a_business_of_the_panel_has_its_mirror_put_right(self, business, owner, people):
        """A row written around ``sync_access`` (``demo_seed`` before L1-A2) is dropped, a missing one is added."""
        from accounts.models import HubMembership
        from hubs import queries

        HubMembership.objects.filter(hub_slug=business.slug).delete()
        self._membership(people["ana"], business.slug, "hub_admin")

        _adopt()

        assert queries.verify_access_mirror() == []
        assert list(HubMembership.objects.values_list("user_id", "role")) == [(owner.pk, "hub_owner")]

    def test_a_deleted_business_keeps_no_access(self, business, owner):
        from accounts.models import HubMembership
        from hubs.models import Hub

        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        _adopt()

        assert not HubMembership.objects.exists()

    def test_after_it_both_tables_agree_and_running_it_again_changes_nothing(self, people, business):
        from hubs import queries
        from hubs.models import Hub, HubMember

        self._membership(people["olga"], "bar-pepe", "hub_owner")
        self._membership(people["eva"], "cafe-lola", "hub_manager")

        _adopt()
        counts = (Hub.objects.count(), HubMember.objects.count())
        _adopt()

        assert queries.verify_access_mirror() == []
        assert (Hub.objects.count(), HubMember.objects.count()) == counts == (3, 3)

    def test_the_adopted_hubs_are_not_provisioned_again(self, people, hub_double):
        """``reconcile_hub_states`` finds nothing owed: no registry, no snapshot, no poll."""
        from io import StringIO

        self._membership(people["olga"], "bar-pepe", "hub_owner")
        _adopt()

        call_command("reconcile_hub_states", stdout=StringIO())

        assert hub_double.calls == []

    def test_going_back_keeps_the_businesses_and_coming_forward_finds_them(self, people):
        from hubs.models import Hub

        self._membership(people["olga"], "bar-pepe", "hub_owner")
        _adopt()
        first = Hub.objects.get(slug="bar-pepe").pk

        _adoption().keep_the_businesses(global_apps, _SchemaEditor())
        _adopt()

        assert list(Hub.objects.values_list("pk", flat=True)) == [first]


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_adoption_and_forward_again(django_user_model):
    """``migrate hubs 0005`` and back: the round trip of the data migration (its reverse keeps the rows)."""
    from accounts.models import HubMembership
    from hubs.models import Hub

    olga = django_user_model.objects.create_user(email="olga@example.com", password=None)
    HubMembership.objects.create(user=olga, hub_slug="bar-pepe", role="hub_owner")

    call_command("migrate", "hubs", "0005", verbosity=0)
    call_command("migrate", "hubs", verbosity=0)

    assert Hub.objects.filter(slug="bar-pepe", status="active").exists()


# --- 0007: support sees the account plane (view only) ----------------------------------------------

SUPPORT_VIEWS = {
    "hubs.view_hub",
    "hubs.view_hubmember",
    "hubs.view_hubownershiptransfer",
    "hubs.view_billingprofile",
    "hubs.view_subscription",
    "hubs.view_subscriptionitem",
    "hubs.view_sessionrevocation",
}


def _hubs_perms_of_support():
    from django.contrib.auth.models import Group

    group = Group.objects.get(name="support")
    return {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.select_related("content_type")
            if p.content_type.app_label == "hubs"}


@pytest.mark.django_db
def test_support_views_the_account_plane_and_nothing_more():
    assert _hubs_perms_of_support() == SUPPORT_VIEWS


@pytest.mark.django_db
def test_reverting_0007_takes_the_views_away_and_applying_it_again_restores_them():
    support = import_module("hubs.migrations.0007_support_views_the_account_plane")

    support.stop_support_viewing(global_apps, _SchemaEditor())
    assert _hubs_perms_of_support() == set()

    support.let_support_view(global_apps, _SchemaEditor())
    support.let_support_view(global_apps, _SchemaEditor())
    assert _hubs_perms_of_support() == SUPPORT_VIEWS


# --- 0011: three plans on sale at sign-up, their copy and ladder (Ioan, 2026-10-15) -------------------

THREE_PLANS = "0011_three_plans_on_sale"
#: The database line the old seed carried and production still showed on 2026-10-15.
OLD_DATABASE_LINE = "Managed PostgreSQL database"


def _three_plans():
    return import_module(f"hubs.migrations.{THREE_PLANS}")


@pytest.mark.django_db
class TestTheCardsReadTheNewCopy:
    """The seed never overwrites a row (``sync_hub_plans`` without ``--update``), so the rows seeded before
    2026-10-15 kept naming the engine under the database. The migration puts production right on deploy: the
    copy and the ladder of the three plans as the seed says; the upgrade-only tiers stay as they are."""

    @pytest.fixture
    def old_catalogue(self, plans):
        """The seed, with the three upgrade-only tiers on sale, as production was."""
        from decimal import Decimal

        from hubs.models import Plan

        assert Plan.objects.filter(slug__in=("pro", "enterprise", "max"), is_active=True).count() == 3
        Plan.objects.filter(slug="free").update(
            features_en=["1 device", OLD_DATABASE_LINE], features_es=["1 dispositivo", "Base de datos PostgreSQL gestionada"]
        )
        Plan.objects.filter(slug="starter").update(description_en="Edited by staff", price_monthly=Decimal("1"))
        return Plan

    def test_the_upgrade_only_tiers_stay_on_sale_as_they_were(self, old_catalogue):
        """Ioan, 2026-10-15: Pro, Enterprise and Max are kept, active and upgrade-only."""
        before = list(old_catalogue.objects.filter(slug__in=("pro", "enterprise", "max")).order_by("slug").values())

        _three_plans().refresh_the_copy(global_apps, _SchemaEditor())

        after = list(old_catalogue.objects.filter(slug__in=("pro", "enterprise", "max")).order_by("slug").values())
        assert after == before
        assert {(plan["is_active"], plan["upgrade_only"]) for plan in after} == {(True, True)}

    def test_the_three_plans_read_the_seed_copy_but_keep_their_prices(self, old_catalogue):
        """Frozen in literals, the migration still writes the copy the seed carried the day it was written."""
        from hubs.management.commands.sync_hub_plans import PLANS

        _three_plans().refresh_the_copy(global_apps, _SchemaEditor())

        seed = {plan["slug"]: plan for plan in PLANS}
        for slug in ("free", "starter", "standard"):
            plan = old_catalogue.objects.get(slug=slug)
            assert plan.features_en == seed[slug]["features_en"], slug
            assert plan.features_es == seed[slug]["features_es"], slug
            assert plan.description_en == seed[slug]["description_en"], slug
            assert plan.description_es == seed[slug]["description_es"], slug
        assert OLD_DATABASE_LINE not in old_catalogue.objects.get(slug="free").features_en
        # A price set by staff is theirs: only the copy and the resource ladder are refreshed.
        assert old_catalogue.objects.get(slug="starter").price_monthly == 1

    def test_standard_gets_twice_the_resources_of_starter(self, old_catalogue):
        """Ioan, 2026-10-15: the rows seeded before carried the flat paid ladder (3 and 15 s)."""
        old_catalogue.objects.filter(slug="standard").update(max_db_connections=3)

        _three_plans().refresh_the_copy(global_apps, _SchemaEditor())

        standard, starter = (old_catalogue.objects.get(slug=s) for s in ("standard", "starter"))
        assert (standard.max_db_connections, standard.statement_timeout_seconds) == (6, 15)
        assert standard.max_db_connections == 2 * starter.max_db_connections

    def test_the_migration_is_idempotent_and_survives_a_database_without_the_rows(self, db):
        from hubs.models import Plan

        _three_plans().refresh_the_copy(global_apps, _SchemaEditor())
        _three_plans().refresh_the_copy(global_apps, _SchemaEditor())

        assert Plan.objects.count() == 0

    def test_the_reverse_undoes_nothing(self):
        """The old copy is nowhere to be read back from: going back leaves the new one, a valid catalogue."""
        from django.db import migrations

        assert _three_plans().Migration.operations[0].reverse_code is migrations.RunPython.noop


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_three_plans_and_forward_again(plans):
    from hubs.models import Plan

    Plan.objects.filter(slug="free").update(features_en=["1 device", OLD_DATABASE_LINE])
    call_command("migrate", "hubs", "0010", verbosity=0)
    call_command("migrate", "hubs", verbosity=0)

    # Only columns 0010 has: the model of today carries columns a later migration adds (0012).
    free = Plan.objects.filter(slug="free").values_list("features_en", flat=True).get()
    assert OLD_DATABASE_LINE not in free
    assert Plan.objects.filter(slug="pro").values_list("is_active", flat=True).get() is True


def _imported_modules(module) -> set[str]:
    import ast
    from pathlib import Path

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    names = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    return names


def test_0011_is_frozen_and_reads_nothing_of_the_seed():
    """A migration is history: it carries its own values, so a later change of the seed (``sync_hub_plans``) does
    not rewrite what it did, and the seed can drop or rename what 0011 read without breaking it."""
    assert [name for name in _imported_modules(_three_plans()) if name.startswith("hubs")] == []


# --- 0012: the monthly messages of each plan, assistant and WhatsApp (Ioan, 2026-10-15) -----------------

MONTHLY_MESSAGES = "0012_plan_monthly_messages"
#: What 0012 writes, by slug: (assistant, WhatsApp) messages a month. Standard doubles Starter.
MESSAGES_0012 = {"free": (30, 30), "starter": (300, 150), "standard": (600, 300), "payment-test": (300, 150)}
#: The upgrade-only tiers get the figures of the old stack (ADR-0474, levels pro/enterprise), so a customer on one
#: never has fewer than Free.
UPGRADE_ONLY_0012 = {"pro": (1000, 500), "enterprise": (3000, 800), "max": (3000, 800)}


def _monthly_messages():
    return import_module(f"hubs.migrations.{MONTHLY_MESSAGES}")


def _messages_of(Plan) -> dict[str, tuple[int, int]]:
    return {
        plan.slug: (plan.assistant_messages_per_month, plan.whatsapp_messages_per_month)
        for plan in Plan.objects.order_by("slug")
    }


@pytest.mark.django_db
class TestEachPlanGetsItsMonthlyMessages:
    """The columns are new, so the rows already in production read 0 (none) until the migration gives them the
    figures of the seed; the upgrade-only tiers get the old stack's. Only a row that exists is written."""

    @pytest.fixture
    def catalogue_without_messages(self, plans):
        from hubs.models import Plan

        Plan.objects.update(assistant_messages_per_month=0, whatsapp_messages_per_month=0)
        return Plan

    def test_each_plan_on_sale_and_the_internal_one_get_their_figures(self, catalogue_without_messages):
        _monthly_messages().give_monthly_messages(global_apps, _SchemaEditor())

        assert _messages_of(catalogue_without_messages) == {**MESSAGES_0012, **UPGRADE_ONLY_0012}

    def test_a_customer_on_an_upgrade_only_tier_never_has_fewer_than_free(self, catalogue_without_messages):
        _monthly_messages().give_monthly_messages(global_apps, _SchemaEditor())

        messages = _messages_of(catalogue_without_messages)
        assert messages["pro"] == (1000, 500)
        for slug in UPGRADE_ONLY_0012:
            assert messages[slug] >= messages["free"], slug

    def test_a_plan_without_its_row_is_not_created(self):
        """The migration only writes rows that exist."""
        from hubs.models import Plan

        call_command("sync_hub_plans", stdout=StringIO())
        Plan.objects.filter(slug__in=UPGRADE_ONLY_0012).delete()

        _monthly_messages().give_monthly_messages(global_apps, _SchemaEditor())

        assert not Plan.objects.filter(slug__in=UPGRADE_ONLY_0012).exists()
        assert _messages_of(Plan) == MESSAGES_0012

    def test_the_figures_are_the_seeds(self, plans):
        from hubs.management.commands.sync_hub_plans import PLANS

        seed = {
            plan["slug"]: (plan["assistant_messages_per_month"], plan["whatsapp_messages_per_month"]) for plan in PLANS
        }
        assert seed == {**MESSAGES_0012, **UPGRADE_ONLY_0012}

    def test_it_is_frozen_and_reads_nothing_of_the_seed(self):
        assert [name for name in _imported_modules(_monthly_messages()) if name.startswith("hubs")] == []

    def test_it_is_idempotent_and_survives_a_database_without_the_rows(self, db):
        from hubs.models import Plan

        _monthly_messages().give_monthly_messages(global_apps, _SchemaEditor())
        _monthly_messages().give_monthly_messages(global_apps, _SchemaEditor())

        assert Plan.objects.count() == 0


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_monthly_messages_and_forward_again(plans):
    """Back to 0011 the two columns go; forward, they come back with the figures of each plan."""
    from django.db import connection as db

    from hubs.models import Plan

    call_command("migrate", "hubs", "0011", verbosity=0)
    with db.cursor() as cursor:
        columns = {column.name for column in db.introspection.get_table_description(cursor, "hubs_plan")}
    assert {"assistant_messages_per_month", "whatsapp_messages_per_month"}.isdisjoint(columns)

    call_command("migrate", "hubs", verbosity=0)

    assert _messages_of(Plan) == {**MESSAGES_0012, **UPGRADE_ONLY_0012}
