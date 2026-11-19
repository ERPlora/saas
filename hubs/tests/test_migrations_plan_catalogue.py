"""The plan catalogue the data migrations of hubs leave: three plans on sale with their copy and ladder
(0011), the monthly messages (0012), the plans in the database (0013) and the module cap (0019)."""

from decimal import Decimal
from importlib import import_module
from io import StringIO

import pytest
from django.apps import apps as global_apps
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from hubs.tests.data_migrations import (
    CATALOGUE_0013,
    COPY_0020,
    COPY_0021,
    COPY_0026,
    COPY_0029,
    _expected_0013,
    _imported_modules,
    _row,
    _SchemaEditor,
    _snapshot,
    _three_plans,
)

# --- 0011: three plans on sale at sign-up, their copy and ladder -----------------------------------

#: The database line the old seed carried and production still showed on 2026-10-15.
OLD_DATABASE_LINE = "Managed PostgreSQL database"


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
        """Pro, Enterprise and Max are kept, active and upgrade-only."""
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
        """The rows seeded before carried the flat paid ladder (3 and 15 s)."""
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


def test_0011_is_frozen_and_reads_nothing_of_the_seed():
    """A migration is history: it carries its own values, so no later change of the code rewrites what it did (the
    seed it was written next to, ``sync_hub_plans``, is empty since 0013)."""
    assert [name for name in _imported_modules(_three_plans()) if name.startswith("hubs")] == []


# --- 0012: the monthly messages of each plan, assistant and WhatsApp --------------------------------

MONTHLY_MESSAGES = "0012_plan_monthly_messages"
#: What 0012 writes, by slug: (assistant, WhatsApp) messages a month. Standard doubles Starter.
MESSAGES_0012 = {"free": (30, 30), "starter": (300, 150), "standard": (600, 300), "payment-test": (300, 150)}
#: The upgrade-only tiers get the figures of the old stack (levels pro/enterprise), so a customer on one
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


# --- 0013: the plans live in the database; no trial -----------------------------------------------


PLANS_IN_THE_DATABASE = "0013_plans_in_the_database"
UPGRADE_ONLY_TIERS = ("pro", "enterprise", "max")
#: What staff fill in by hand and no migration writes: the link of each plan to Stripe.
STRIPE_FIELDS = ("stripe_product_id", "stripe_price_id", "stripe_price_id_annual")


def _plans_in_the_database():
    return import_module(f"hubs.migrations.{PLANS_IN_THE_DATABASE}")


def _assert_the_catalogue_of_0013(Plan):
    for slug, expected in _expected_0013().items():
        assert _row(Plan.objects.get(slug=slug), expected) == expected, slug


def _assert_the_catalogue_the_migrations_leave(Plan):
    """0013's catalogue as the later data migrations leave it: the cards of Pro, Enterprise and Max of 0020, the
    features of Free, Starter and Standard of 0021, Standard's card without the custom domain of 0026 and the database
    line of Free and Starter that says what a recovery keeps of 0029."""
    expected = _expected_0013()
    for slug, fields in (*COPY_0020.items(), *COPY_0021.items(), *COPY_0026.items(), *COPY_0029.items()):
        expected[slug] = {**expected[slug], **fields}
    for slug, fields in expected.items():
        assert _row(Plan.objects.get(slug=slug), fields) == fields, slug


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


@pytest.mark.django_db
class TestThePlansLiveInTheDatabase:
    """The plans live only in the database and staff keep them in the admin; 0013 is the seed
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
        _assert_the_catalogue_the_migrations_leave(Plan)
        assert set(Plan.objects.values_list("trial_period_days", flat=True)) == {0}

    def test_the_test_database_holds_the_catalogue_the_migrations_leave(self):
        """pytest builds its database by running every migration, so every test starts from the catalogue."""
        from hubs.models import Plan

        assert set(Plan.objects.values_list("slug", flat=True)) == set(CATALOGUE_0013)
        _assert_the_catalogue_the_migrations_leave(Plan)

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
        ``saas-migrate`` still calls it: it writes nothing, ``--update`` included."""
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

    _assert_the_catalogue_the_migrations_leave(Plan)


# --- 0019: how many modules a business may choose to turn on ---------------------------------------


MODULE_CAP = "0019_plan_max_apps"
#: What 0019 writes, by slug: Free 20, each plan up doubles the one below, ``payment-test`` reads as Starter and the
#: upgrade-only tiers have no cap (0).
MAX_APPS_0019 = {"free": 20, "starter": 40, "standard": 80, "payment-test": 40}
UPGRADE_ONLY_0019 = {"pro": 0, "enterprise": 0, "max": 0}


def _module_cap():
    return import_module(f"hubs.migrations.{MODULE_CAP}")


def _caps_of(Plan) -> dict[str, int]:
    return dict(Plan.objects.order_by("slug").values_list("slug", "max_apps"))


@pytest.mark.django_db
class TestEachPlanGetsItsModuleCap:
    """The column is new, so every row already in production reads 0 (no limit) until the migration gives the plans
    of the catalogue their figure; a plan staff added keeps 0. Only a row that exists is written."""

    @pytest.fixture
    def catalogue_without_caps(self, plans):
        from hubs.models import Plan

        Plan.objects.update(max_apps=0)
        return Plan

    def test_each_plan_gets_its_figure_and_the_upgrade_only_tiers_none(self, catalogue_without_caps):
        _module_cap().give_module_caps(global_apps, _SchemaEditor())

        assert _caps_of(catalogue_without_caps) == {**MAX_APPS_0019, **UPGRADE_ONLY_0019}

    def test_a_plan_staff_added_is_left_without_a_cap(self, catalogue_without_caps):
        catalogue_without_caps.objects.create(slug="staff-plan", name_en="Staff plan", price_monthly=Decimal("9.99"))

        _module_cap().give_module_caps(global_apps, _SchemaEditor())

        assert catalogue_without_caps.objects.get(slug="staff-plan").max_apps == 0

    def test_a_plan_without_its_row_is_not_created(self):
        from hubs.models import Plan

        Plan.objects.filter(slug__in=MAX_APPS_0019).delete()

        _module_cap().give_module_caps(global_apps, _SchemaEditor())

        assert not Plan.objects.filter(slug__in=MAX_APPS_0019).exists()

    def test_the_catalogue_the_migrations_leave_carries_its_figures(self):
        from hubs.models import Plan

        assert _caps_of(Plan) == {**MAX_APPS_0019, **UPGRADE_ONLY_0019}

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        assert [name for name in _imported_modules(_module_cap()) if name.startswith("hubs")] == []

    def test_it_is_idempotent_and_survives_a_database_without_the_rows(self, db):
        from hubs.models import Plan

        Plan.objects.all().delete()
        _module_cap().give_module_caps(global_apps, _SchemaEditor())
        _module_cap().give_module_caps(global_apps, _SchemaEditor())

        assert Plan.objects.count() == 0


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_module_cap_and_forward_again():
    """``migrate hubs 0018`` and back: the column goes and comes back with the figure of each plan, and a row written
    without it, as the code before the column writes, gets the database's 0 (no limit)."""
    from hubs.models import Plan

    slugs = set(Plan.objects.values_list("slug", flat=True))
    call_command("migrate", "hubs", "0018", verbosity=0)
    with connection.cursor() as cursor:
        columns = {column.name for column in connection.introspection.get_table_description(cursor, "hubs_plan")}
    assert "max_apps" not in columns
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
    assert _caps_of(Plan) == {**MAX_APPS_0019, **UPGRADE_ONLY_0019, "old-code": 0}


# --- The catalogue a transactional test puts back ------------------------------------------------


@pytest.mark.django_db
def test_putting_the_catalogue_back_leaves_what_the_migrations_leave():
    """A transactional test starts from a flushed database: ``put_the_catalogue_back`` runs the data migrations of the
    plans again, so it reads what pytest's migrated database reads — 0019's caps and 0020's cards included."""
    from hubs.models import Plan
    from hubs.tests.conftest import put_the_catalogue_back

    Plan.objects.all().delete()
    put_the_catalogue_back()

    assert _caps_of(Plan) == {**MAX_APPS_0019, **UPGRADE_ONLY_0019}
    _assert_the_catalogue_the_migrations_leave(Plan)
