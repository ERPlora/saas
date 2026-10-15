"""The migrations of fiscal are reversible and match the models; the ``support`` group sees the authorisations
and decides nothing (PLAN-SAAS §2.1 round 11: superuser + ``support``, view only).

The round trip runs inside the test's transaction (Postgres DDL is transactional), so it leaves the test
database as it found it.
"""

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

FISCAL_TABLES = {"fiscal_representationgrant"}


class _SchemaEditor:
    """What a ``RunPython`` function reads from the schema editor: the connection."""

    connection = connection


def _tables():
    return set(connection.introspection.table_names())


def test_every_operation_of_fiscal_can_be_reversed():
    migrations = [
        m for (app, _), m in MigrationLoader(None, ignore_no_migrations=True).disk_migrations.items() if app == "fiscal"
    ]

    assert migrations
    assert all(operation.reversible for migration in migrations for operation in migration.operations)


@pytest.mark.django_db
def test_fiscal_migrates_to_zero_and_back():
    call_command("migrate", "fiscal", "zero", verbosity=0)
    assert _tables().isdisjoint(FISCAL_TABLES)

    call_command("migrate", "fiscal", verbosity=0)
    assert FISCAL_TABLES <= _tables()


@pytest.mark.django_db
def test_the_models_and_the_migrations_agree():
    """``makemigrations --check`` exits non-zero when a model changed without its migration."""
    call_command("makemigrations", "fiscal", "--check", "--dry-run", verbosity=0)


# --- 0002: support sees the authorisations (view only) ------------------------------------------------


def _fiscal_perms_of_support():
    from django.contrib.auth.models import Group

    group = Group.objects.get(name="support")
    return {
        f"{p.content_type.app_label}.{p.codename}"
        for p in group.permissions.select_related("content_type")
        if p.content_type.app_label == "fiscal"
    }


@pytest.mark.django_db
def test_support_views_the_authorisations_and_decides_nothing():
    assert _fiscal_perms_of_support() == {"fiscal.view_representationgrant"}


@pytest.mark.django_db
def test_reverting_0002_takes_the_view_away_and_applying_it_again_restores_it():
    support = import_module("fiscal.migrations.0002_support_views_the_authorisations")

    support.stop_support_viewing(global_apps, _SchemaEditor())
    assert _fiscal_perms_of_support() == set()

    support.let_support_view(global_apps, _SchemaEditor())
    support.let_support_view(global_apps, _SchemaEditor())
    assert _fiscal_perms_of_support() == {"fiscal.view_representationgrant"}
