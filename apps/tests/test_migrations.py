"""Migrations of apps: the ``shared`` schema and its two tables, then ``Module`` (spec §3.2).

``0001_shared_schema`` creates the schema ``shared`` (``IF NOT EXISTS``) and, in it, ``app`` and
``app_doc``, never in ``public``. It is reversible: ``migrate apps zero`` drops both tables and keeps
the schema, which production's ``bootstrap_databases`` creates with its default privileges for the
Hub's role. ``0002_module`` creates ``Module`` in the SaaS's own schema (plan §3.l).

The tests migrate inside the test's transaction (Postgres DDL is transactional), so the rollback at
the end restores everything: ``TestCase``-style, as spec §3.2 asks of every test of these tables.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db

CATALOG = [("shared", "app"), ("shared", "app_doc")]
MODULE = [("public", "apps_module")]


def tables() -> list[tuple[str, str]]:
    """Where ``app``, ``app_doc`` and ``apps_module`` live, whatever the schema."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_name IN ('app', 'app_doc', 'apps_module') ORDER BY table_schema, table_name"
        )
        return cursor.fetchall()


def constraints(kind: str) -> list[tuple[str, str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_schema, table_name, constraint_name FROM information_schema.table_constraints "
            "WHERE constraint_type = %s AND table_schema = 'shared' ORDER BY table_name, constraint_name",
            [kind],
        )
        return cursor.fetchall()


def foreign_keys() -> list[tuple[str, str, str, str]]:
    """Each FK of the ``shared`` tables: (schema, table) → (schema, table) it references."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT tc.table_schema, tc.table_name, ccu.table_schema, ccu.table_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'shared'"
        )
        return cursor.fetchall()


def schema_exists() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'shared'"
        )
        return cursor.fetchone() is not None


def migrate_apps(target: str | None) -> None:
    """``manage.py migrate apps <target>`` (``None`` = ``zero``) on the test database."""
    executor = MigrationExecutor(connection)
    executor.migrate([("apps", target)])


def test_the_catalog_lives_in_shared_and_module_in_public():
    assert tables() == MODULE + CATALOG


def test_one_doc_per_app_and_language_is_a_named_unique_constraint():
    assert constraints("UNIQUE") == [
        ("shared", "app_doc", "shared_app_doc_app_lang_unique")
    ]


def test_the_only_foreign_key_is_app_doc_to_app_inside_shared():
    """No FK leaves shared in either direction (spec §3.1): Module.slug has none."""
    assert foreign_keys() == [("shared", "app_doc", "shared", "app")]


def test_the_first_migration_creates_only_the_catalog():
    migrate_apps("0001_shared_schema")

    assert tables() == CATALOG

    migrate_apps("0002_module")
    assert tables() == MODULE + CATALOG


def test_migrating_to_zero_drops_the_tables_keeps_the_schema_and_migrating_again_restores_them():
    migrate_apps(None)

    assert tables() == []
    assert schema_exists()

    migrate_apps("0002_module")

    assert tables() == MODULE + CATALOG
    assert constraints("UNIQUE") == [
        ("shared", "app_doc", "shared_app_doc_app_lang_unique")
    ]
