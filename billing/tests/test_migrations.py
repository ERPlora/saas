"""The migrations of billing are reversible, seed today's tax data and match the models.

The round trip runs inside the test's transaction (Postgres DDL is transactional), so it leaves the
test database as it found it.
"""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader

BILLING_TABLES = {
    "billing_taxcategory",
    "billing_taxrule",
    "billing_fiscalpolicy",
    "billing_companyconfig",
    "billing_vatcheck",
}


def _tables():
    return set(connection.introspection.table_names())


def test_every_operation_of_billing_can_be_reversed():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    migrations = [
        migration
        for (app, _), migration in loader.disk_migrations.items()
        if app == "billing"
    ]

    assert migrations
    assert all(
        operation.reversible
        for migration in migrations
        for operation in migration.operations
    )


@pytest.mark.django_db
def test_billing_migrates_to_zero_and_back_with_its_data():
    from billing.models import CompanyConfig, TaxRule

    call_command("migrate", "billing", "zero", verbosity=0)
    assert _tables().isdisjoint(BILLING_TABLES)

    call_command("migrate", "billing", verbosity=0)
    assert BILLING_TABLES <= _tables()
    assert TaxRule.objects.filter(country_code="ES", region_code="").exists()
    assert CompanyConfig.objects.get().tax_id == "B27593136"


@pytest.mark.django_db
def test_the_models_and_the_migrations_agree():
    """``makemigrations --check`` exits non-zero when a model changed without its migration."""
    call_command("makemigrations", "billing", "--check", "--dry-run", verbosity=0)


def test_the_seed_migration_carries_its_own_data():
    """A migration describes a date: it cannot change meaning the day ``billing/seed.py`` changes."""
    import ast
    from pathlib import Path

    from django.conf import settings

    source = (Path(settings.BASE_DIR) / "billing" / "migrations" / "0002_seed_tax_data.py").read_text(encoding="utf-8")
    imported = {
        node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom) and node.module
    } | {alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names}

    assert not {name for name in imported if name.startswith("billing")}


@pytest.mark.django_db
def test_the_spanish_regime_values_become_english_and_back():
    from billing.models import CompanyConfig

    call_command("migrate", "billing", "0002", verbosity=0)
    CompanyConfig.objects.update(vat_regime="recargo")

    call_command("migrate", "billing", verbosity=0)
    assert CompanyConfig.objects.values_list("vat_regime", flat=True).get() == "equivalence_surcharge"

    call_command("migrate", "billing", "0002", verbosity=0)
    assert CompanyConfig.objects.values_list("vat_regime", flat=True).get() == "recargo"
    call_command("migrate", "billing", verbosity=0)
