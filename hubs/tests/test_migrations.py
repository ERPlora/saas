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

    def test_without_the_free_plan_there_is_no_subscription(self, people):
        from hubs.models import Hub, Plan, Subscription

        Plan.objects.all().delete()
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
    """``migrate hubs 0005`` and back: the round trip of the data migration (its reverse keeps the rows).

    The plans are in the database (0013), so the adoption gives the business its Free subscription. The whole
    round trip runs in the test's one transaction, where a deferred foreign key check would still be pending when
    a later migration alters ``hubs_subscription``: the checks run at once, as each migration's own COMMIT does."""
    from accounts.models import HubMembership
    from hubs.models import Hub

    olga = django_user_model.objects.create_user(email="olga@example.com", password=None)
    HubMembership.objects.create(user=olga, hub_slug="bar-pepe", role="hub_owner")
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    call_command("migrate", "hubs", "0005", verbosity=0)
    call_command("migrate", "hubs", verbosity=0)

    hub = Hub.objects.get(slug="bar-pepe", status="active")
    assert hub.subscription.plan.slug == "free"


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
    """The seed of the time (``sync_hub_plans``, empty since 0013) never overwrote a row, so the rows seeded before
    2026-10-15 kept naming the engine under the database. The migration puts production right on deploy: the
    copy and the ladder of the three plans as the seed says; the upgrade-only tiers stay as they are."""

    @pytest.fixture
    def old_catalogue(self, plans):
        """The catalogue, with the three upgrade-only tiers on sale, as production was."""
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
        """Frozen in literals, the migration writes the copy of its day: the one 0013 seeds a new database with."""
        _three_plans().refresh_the_copy(global_apps, _SchemaEditor())

        seed = _plans_in_the_database().CATALOGUE
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

        Plan.objects.all().delete()
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
    """A migration is history: it carries its own values, so no later change of the code rewrites what it did (the
    seed it was written next to, ``sync_hub_plans``, is empty since 0013)."""
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

        Plan.objects.filter(slug__in=UPGRADE_ONLY_0012).delete()

        _monthly_messages().give_monthly_messages(global_apps, _SchemaEditor())

        assert not Plan.objects.filter(slug__in=UPGRADE_ONLY_0012).exists()
        assert _messages_of(Plan) == MESSAGES_0012

    def test_the_catalogue_the_migrations_leave_carries_its_figures(self):
        from hubs.models import Plan

        assert _messages_of(Plan) == {**MESSAGES_0012, **UPGRADE_ONLY_0012}

    def test_it_is_frozen_and_reads_nothing_of_the_seed(self):
        assert [name for name in _imported_modules(_monthly_messages()) if name.startswith("hubs")] == []

    def test_it_is_idempotent_and_survives_a_database_without_the_rows(self, db):
        from hubs.models import Plan

        Plan.objects.all().delete()
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


# --- 0013: the plans live in the database; no trial (Ioan, 2026-10-15) ---------------------------------------

from decimal import Decimal  # noqa: E402


PLANS_IN_THE_DATABASE = "0013_plans_in_the_database"
#: What every paid plan shares on the axes the cards do not compare.
_UNCAPPED = {"max_hubs_per_org": 0, "max_devices": 0, "max_users": 0}
#: The catalogue 0013 leaves, field by field: three plans on sale at sign-up, the three upgrade-only tiers (kept,
#: active, going on up the ladder: each twice the one below, Pro 12, Enterprise 24, Max 48) and the internal one, none with a trial (the Free plan is the way in). The copy
#: of Free, Starter and Standard is the one 0011 froze (``COPY``), the messages the ones 0012 gave; history of the
#: same day, so the three migrations must agree.
CATALOGUE_0013 = {
    "free": {
        "name_en": "Free", "name_es": "Gratis", "featured_label_en": "", "featured_label_es": "",
        "price_monthly": Decimal("0"), "price_annual": Decimal("0"),
        "is_active": True, "upgrade_only": False, "internal_only": False, "trial_period_days": 0, "display_order": 10,
        "max_hubs_per_org": 1, "max_devices": 1, "max_users": 3, "max_db_connections": 1, "statement_timeout_seconds": 5,
        "assistant_messages_per_month": 30, "whatsapp_messages_per_month": 30,
        "included_level": "free", "support_level": "community", "includes_custom_domain": False,
    },
    "starter": {
        "name_en": "Starter", "name_es": "Starter", "featured_label_en": "", "featured_label_es": "",
        "price_monthly": Decimal("29.99"), "price_annual": Decimal("299.90"),
        "is_active": True, "upgrade_only": False, "internal_only": False, "trial_period_days": 0, "display_order": 30,
        **_UNCAPPED, "max_db_connections": 3, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 300, "whatsapp_messages_per_month": 150,
        "included_level": "basic", "support_level": "email", "includes_custom_domain": False,
    },
    "standard": {
        "name_en": "Standard", "name_es": "Standard", "featured_label_en": "Recommended", "featured_label_es": "Recomendado",
        "price_monthly": Decimal("54.99"), "price_annual": Decimal("549.90"),
        "is_active": True, "upgrade_only": False, "internal_only": False, "trial_period_days": 0, "display_order": 40,
        **_UNCAPPED, "max_db_connections": 6, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 600, "whatsapp_messages_per_month": 300,
        "included_level": "basic", "support_level": "priority_email", "includes_custom_domain": True,
    },
    "pro": {
        "name_en": "Pro", "name_es": "Pro", "featured_label_en": "", "featured_label_es": "",
        "description_en": "High performance on isolated infrastructure, with a full API for your integrations.",
        "description_es": "Alto rendimiento en infraestructura aislada, con API completa para tus integraciones.",
        "features_en": [
            "Everything in Standard", "Four times the database throughput of Starter", "Isolated infrastructure",
            "Priority email support (business hours)",
        ],
        "features_es": [
            "Todo lo del plan Standard", "El cuádruple de capacidad de base de datos que Starter", "Infraestructura aislada",
            "Soporte por email prioritario (horario laboral)",
        ],
        "price_monthly": Decimal("109.99"), "price_annual": Decimal("1099.90"),
        "is_active": True, "upgrade_only": True, "internal_only": False, "trial_period_days": 0, "display_order": 50,
        **_UNCAPPED, "max_db_connections": 12, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 1000, "whatsapp_messages_per_month": 500,
        "included_level": "pro", "support_level": "priority_email", "includes_custom_domain": True,
    },
    "enterprise": {
        "name_en": "Enterprise", "name_es": "Enterprise", "featured_label_en": "", "featured_label_es": "",
        "description_en": "Dedicated infrastructure with autoscaling, disaster recovery and contract-backed support.",
        "description_es": "Infraestructura dedicada con autoescalado, recuperación ante desastres y soporte acordado en contrato.",
        "features_en": [
            "Everything in Pro", "Eight times the database throughput of Starter", "Automatic container autoscaling",
            "Disaster recovery (PITR)", "Advanced monitoring", "Support channels and escalation agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Pro", "Ocho veces la capacidad de base de datos de Starter",
            "Autoescalado automático de contenedores", "Recuperación ante desastres (PITR)", "Monitoreo avanzado",
            "Canales de soporte y escalado acordados en contrato",
        ],
        "price_monthly": Decimal("209.99"), "price_annual": Decimal("2099.90"),
        "is_active": True, "upgrade_only": True, "internal_only": False, "trial_period_days": 0, "display_order": 60,
        **_UNCAPPED, "max_db_connections": 24, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 3000, "whatsapp_messages_per_month": 800,
        "included_level": "enterprise", "support_level": "contract", "includes_custom_domain": True,
    },
    "max": {
        "name_en": "Max", "name_es": "Max", "featured_label_en": "", "featured_label_es": "",
        "description_en": "Maximum single-node performance, for the most demanding businesses.",
        "description_es": "Máximo rendimiento de un solo nodo, para los negocios más exigentes.",
        "features_en": [
            "Everything in Enterprise", "Sixteen times the database throughput of Starter", "─────────────────────",
            "Custom integrations", "Named technical contact agreed in contract",
        ],
        "features_es": [
            "Todo lo del plan Enterprise", "Dieciséis veces la capacidad de base de datos de Starter",
            "─────────────────────", "Integraciones a medida", "Responsable técnico acordado en contrato",
        ],
        "price_monthly": Decimal("419.99"), "price_annual": Decimal("4199.90"),
        "is_active": True, "upgrade_only": True, "internal_only": False, "trial_period_days": 0, "display_order": 70,
        **_UNCAPPED, "max_db_connections": 48, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 3000, "whatsapp_messages_per_month": 800,
        "included_level": "enterprise", "support_level": "contract", "includes_custom_domain": True,
    },
    "payment-test": {
        "name_en": "Payment Test (internal)", "name_es": "Prueba de pago (interno)",
        "description_en": "Internal plan for end-to-end billing verification. Not for sale.",
        "description_es": "Plan interno para verificar la facturación de punta a punta. No está a la venta.",
        "features_en": ["Internal use only"], "features_es": ["Solo uso interno"],
        "featured_label_en": "", "featured_label_es": "",
        "price_monthly": Decimal("1.00"), "price_annual": Decimal("0"),
        "is_active": True, "upgrade_only": False, "internal_only": True, "trial_period_days": 0, "display_order": 999,
        **_UNCAPPED, "max_db_connections": 3, "statement_timeout_seconds": 15,
        "assistant_messages_per_month": 300, "whatsapp_messages_per_month": 150,
        "included_level": "free", "support_level": "community", "includes_custom_domain": False,
    },
}  # fmt: skip
UPGRADE_ONLY_TIERS = ("pro", "enterprise", "max")
#: The copy fields 0011 froze for the three plans on sale.
COPY_FIELDS = ("description_en", "description_es", "features_en", "features_es")
#: What staff fill in by hand and no migration writes: the link of each plan to Stripe.
STRIPE_FIELDS = ("stripe_product_id", "stripe_price_id", "stripe_price_id_annual")


def _plans_in_the_database():
    return import_module(f"hubs.migrations.{PLANS_IN_THE_DATABASE}")


def _expected_0013() -> dict[str, dict]:
    copy = _three_plans().COPY
    return {
        slug: {**fields, **{name: copy[slug][name] for name in COPY_FIELDS if slug in copy}}
        for slug, fields in CATALOGUE_0013.items()
    }


def _row(plan, fields) -> dict:
    return {name: getattr(plan, name) for name in fields}


def _assert_the_catalogue_of_0013(Plan):
    for slug, expected in _expected_0013().items():
        assert _row(Plan.objects.get(slug=slug), expected) == expected, slug


#: The rows production had on 2026-10-15, before 0013: the seven seeded plans as the old seed wrote them (a 15-day
#: trial on Starter and Standard, older prices and copy, the flat paid ladder, no messages), with their Stripe ids.
PRODUCTION_ROWS = {
    "free": {"name_en": "Free", "price_monthly": Decimal("0"), "features_en": ["1 device", OLD_DATABASE_LINE]},
    "starter": {
        "name_en": "Starter", "price_monthly": Decimal("24.99"), "price_annual": Decimal("249.90"), "trial_period_days": 15,
        "description_en": "Your business in the cloud. No servers, no maintenance, always available.",
        "stripe_product_id": "prod_live_starter", "stripe_price_id": "price_live_starter_month",
        "stripe_price_id_annual": "price_live_starter_year",
    },
    "standard": {
        "name_en": "Standard", "price_monthly": Decimal("49.99"), "trial_period_days": 15, "max_db_connections": 3,
        "statement_timeout_seconds": 15, "stripe_product_id": "prod_live_standard", "stripe_price_id": "price_live_standard_month",
    },
    "payment-test": {"name_en": "Payment Test (internal)", "price_monthly": Decimal("1.00"), "internal_only": True},
    "pro": {"name_en": "Pro", "price_monthly": Decimal("99.99"), "upgrade_only": True, "trial_period_days": 15,
            "stripe_price_id": "price_live_pro"},
    "enterprise": {"name_en": "Enterprise", "price_monthly": Decimal("209.99"), "upgrade_only": True},
    "max": {"name_en": "Max", "price_monthly": Decimal("419.99"), "upgrade_only": True},
}  # fmt: skip


@pytest.fixture
def production_rows(db):
    """The plan table as production had it on 2026-10-15 (``PRODUCTION_ROWS``), and nothing else."""
    from hubs.models import Plan

    Plan.objects.all().delete()
    return {slug: Plan.objects.create(slug=slug, **fields) for slug, fields in PRODUCTION_ROWS.items()}


def _snapshot(Plan) -> dict[str, dict]:
    fields = [field.name for field in Plan._meta.concrete_fields if field.name != "updated_at"]
    return {plan.slug: _row(plan, fields) for plan in Plan.objects.all()}


@pytest.mark.django_db
class TestThePlansLiveInTheDatabase:
    """Ioan, 2026-10-15: the plans live only in the database and staff keep them in the admin; 0013 is the seed
    of a new database and puts production's rows right once. There is no trial any more: Starter and Standard
    carry 0 days (the Free plan is the way in); the mechanism stays, dormant. Pro, Enterprise and Max are kept,
    active and upgrade-only."""

    def test_migrating_an_empty_database_leaves_exactly_the_catalogue(self):
        from hubs.models import Plan

        call_command("migrate", "hubs", "0012", verbosity=0)
        # The model of 0012, not today's: a column a later migration adds is not there yet.
        old_plan = MigrationLoader(connection).project_state(("hubs", "0012_plan_monthly_messages")).apps.get_model(
            "hubs", "Plan"
        )
        old_plan.objects.all().delete()
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        call_command("migrate", "hubs", verbosity=0)

        assert set(Plan.objects.values_list("slug", flat=True)) == set(CATALOGUE_0013)
        _assert_the_catalogue_of_0013(Plan)
        assert set(Plan.objects.values_list("trial_period_days", flat=True)) == {0}

    def test_the_test_database_holds_the_catalogue_the_migrations_leave(self):
        """pytest builds its database by running every migration, so every test starts from the catalogue."""
        from hubs.models import Plan

        assert set(Plan.objects.values_list("slug", flat=True)) == set(CATALOGUE_0013)
        _assert_the_catalogue_of_0013(Plan)

    def test_the_three_migrations_of_that_day_agree(self):
        """0013 writes the copy and the ladder 0011 froze and the messages 0012 gave: one catalogue, read thrice."""
        monthly = _monthly_messages().MONTHLY_MESSAGES
        for slug, fields in CATALOGUE_0013.items():
            assert (fields["assistant_messages_per_month"], fields["whatsapp_messages_per_month"]) == monthly[slug]
            copy = _three_plans().COPY.get(slug)
            if copy:
                assert (fields["max_db_connections"], fields["statement_timeout_seconds"]) == (
                    copy["max_db_connections"],
                    copy["statement_timeout_seconds"],
                ), slug

    def test_production_rows_are_put_right_in_place(self, production_rows):
        from hubs.models import Plan

        stripe_before = {slug: _row(plan, STRIPE_FIELDS) for slug, plan in production_rows.items()}

        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())

        assert Plan.objects.count() == len(PRODUCTION_ROWS)
        _assert_the_catalogue_of_0013(Plan)
        # Updated in place: the subscriptions that point at a plan keep pointing at it.
        for slug, plan in production_rows.items():
            assert Plan.objects.get(slug=slug).pk == plan.pk, slug
        # The link to Stripe is staff's: no migration writes it.
        assert {slug: _row(Plan.objects.get(slug=slug), STRIPE_FIELDS) for slug in production_rows} == stripe_before

    def test_the_upgrade_only_tiers_stay_active_above_the_plans_on_sale(self, production_rows):
        from hubs.models import Plan

        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())

        tiers = Plan.objects.filter(slug__in=UPGRADE_ONLY_TIERS)
        assert tiers.count() == 3
        assert set(tiers.values_list("is_active", "upgrade_only")) == {(True, True)}
        assert set(Plan.objects.public().filter(upgrade_only=True).values_list("slug", flat=True)) == set(UPGRADE_ONLY_TIERS)

    def test_no_plan_has_a_trial_after_it(self, production_rows):
        from hubs.models import Plan

        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())

        assert not Plan.objects.filter(trial_period_days__gt=0).exists()
        assert Plan.objects.signup_trial_days() == {"trial_days_min": None, "trial_days_max": None}

    def test_it_is_idempotent(self, production_rows):
        from hubs.models import Plan

        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())
        first = _snapshot(Plan)
        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())

        assert _snapshot(Plan) == first

    def test_a_plan_staff_added_is_left_as_it_is(self, production_rows):
        from hubs.models import Plan

        Plan.objects.create(slug="bakery-special", name_en="Bakery special", price_monthly=Decimal("9.99"))
        before = _snapshot(Plan)["bakery-special"]

        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())

        assert _snapshot(Plan)["bakery-special"] == before

    def test_on_an_empty_table_it_creates_the_catalogue(self):
        from hubs.models import Plan

        Plan.objects.all().delete()
        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())

        assert set(Plan.objects.values_list("slug", flat=True)) == set(CATALOGUE_0013)
        _assert_the_catalogue_of_0013(Plan)

    def test_reversing_gives_starter_and_standard_their_trial_back_and_keeps_the_rows(self, production_rows):
        """The values before 0013 are nowhere to be read back from; the trial is the one thing it took away."""
        from hubs.models import Plan

        _plans_in_the_database().put_the_catalogue_in(global_apps, _SchemaEditor())
        _plans_in_the_database().give_the_trial_back(global_apps, _SchemaEditor())

        assert Plan.objects.count() == len(PRODUCTION_ROWS)
        assert dict(Plan.objects.filter(trial_period_days__gt=0).values_list("slug", "trial_period_days")) == {
            "starter": 15,
            "standard": 15,
        }

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        """A migration is history: its values are literals, so no later change of the code rewrites them."""
        assert [name for name in _imported_modules(_plans_in_the_database()) if name.startswith("hubs")] == []

    @pytest.mark.parametrize("args", [(), ("--update",)])
    def test_the_seed_command_seeds_nothing(self, args):
        """The plans are kept in the admin. ``sync_hub_plans`` stays only as an empty command, because the deploy's
        ``saas-migrate`` still calls it until aws#4 is applied: it writes nothing, ``--update`` included."""
        from hubs.models import Plan

        before = sorted(Plan.objects.values_list("slug", "updated_at"))
        out, err = StringIO(), StringIO()

        call_command("sync_hub_plans", *args, stdout=out, stderr=err)

        assert sorted(Plan.objects.values_list("slug", "updated_at")) == before
        assert "Plans live in the database; nothing to seed (hubs/0013)." in out.getvalue()
        if args:
            assert "--update is ignored" in err.getvalue()
        else:
            assert err.getvalue() == ""


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_plans_in_the_database_and_forward_again():
    from hubs.models import Plan

    call_command("migrate", "hubs", "0012", verbosity=0)
    assert dict(Plan.objects.filter(trial_period_days__gt=0).values_list("slug", "trial_period_days")) == {
        "starter": 15,
        "standard": 15,
    }
    call_command("migrate", "hubs", verbosity=0)

    _assert_the_catalogue_of_0013(Plan)


# --- 0016: the clock of a suspended business (HUBS-F20) ----------------------------------------------------------

from hubs.tests.conftest import create_business  # noqa: E402

CLOCK = "0016_hub_suspension_clock"


def _clock():
    return import_module(f"hubs.migrations.{CLOCK}")


@pytest.mark.django_db
class TestTheBusinessesAlreadySuspendedGetTheirClock:
    """A business suspended before the clock arrived has no date: without one the hourly pass would only log it,
    forever. Its clock starts on the day of the deploy, so it is never deleted sooner than a new suspension."""

    def test_a_business_already_suspended_counts_from_the_deploy(self, business):
        from hubs.models import Hub

        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.SUSPENDED, suspended_at=None)
        before = timezone.now()

        _clock().date_the_suspended(global_apps, _SchemaEditor())

        business.refresh_from_db()
        assert business.suspended_at is not None
        assert business.suspended_at >= before

    def test_a_dated_suspension_and_a_running_business_are_left_as_they_are(self, business, make_user):
        from hubs.models import Hub

        dated = create_business(make_user("dora@example.com"), name="Dora's")
        since = timezone.now() - timedelta(days=40)
        Hub.objects.filter(pk=dated.pk).update(status=Hub.Status.SUSPENDED, suspended_at=since)

        _clock().date_the_suspended(global_apps, _SchemaEditor())

        assert Hub.objects.get(pk=dated.pk).suspended_at == since
        assert Hub.objects.get(pk=business.pk).suspended_at is None

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        assert [name for name in _imported_modules(_clock()) if name.startswith("hubs")] == []


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_clock_and_forward_again_dating_the_suspended(owner, plans):
    """``migrate hubs 0015`` and back: the deploy itself dates a business that was already suspended (the deferred
    foreign key checks run at once, as in the round trip of 0006)."""
    from hubs.models import Hub

    business = create_business(owner)
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.SUSPENDED)
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

    call_command("migrate", "hubs", "0015", verbosity=0)
    call_command("migrate", "hubs", verbosity=0)

    assert Hub.objects.get(pk=business.pk).suspended_at is not None


# --- 0019: how many modules a business may choose to turn on (Ioan, 2026-10-24) -----------------------------------


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_module_cap_and_forward_again_with_no_plan_capped():
    """``migrate hubs 0018`` and back: the column goes and comes with a 0 (no limit) on every plan, and a row written
    without it, as the code before the column writes, gets the database's 0 too."""
    from hubs.models import Plan

    slugs = set(Plan.objects.values_list("slug", flat=True))
    call_command("migrate", "hubs", "0018", verbosity=0)
    call_command("migrate", "hubs", verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO hubs_plan (id, slug, name_en, name_es, description_en, description_es, price_monthly, price_annual,"
            " features_en, features_es, featured_label_en, featured_label_es, is_active, upgrade_only, internal_only,"
            " stripe_product_id, stripe_price_id, stripe_price_id_annual, trial_period_days, display_order,"
            " max_hubs_per_org, max_devices, max_users, max_db_connections, statement_timeout_seconds,"
            " assistant_messages_per_month, whatsapp_messages_per_month, included_level, support_level,"
            " includes_custom_domain, created_at, updated_at)"
            " VALUES (gen_random_uuid(), 'old-code', 'Old', '', '', '', 0, 0, '[]', '[]', '', '', true, false, false, '', '', '', 0, 0,"
            " 1, 0, 0, 1, 5, 0, 0, 'free', 'community', false, now(), now())"
        )

    assert set(Plan.objects.values_list("slug", flat=True)) == slugs | {"old-code"}
    assert set(Plan.objects.values_list("max_apps", flat=True)) == {0}
