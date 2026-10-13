"""The migrations of hubs are reversible and match the models.

The round trip runs inside the test's transaction (Postgres DDL is transactional), so it leaves the
test database as it found it.
"""

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
