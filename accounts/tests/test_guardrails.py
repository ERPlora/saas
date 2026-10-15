"""Guardrails of accounts (django-ninja-live: one road to the server), as hubs' ``test_guardrails.py``.

- Only ``services.py`` and ``queries.py`` touch the database: no ``Model.objects``, cursor, connection or
  transaction anywhere else of accounts (routes, the API keys' authentication, the session tracker, the jump,
  ``/internal``, mails, photos, live, events, schemas). Allowed besides: ``models.py``, ``admin.py`` and the
  migrations.
- Nowhere ``using=``, ``.using(`` nor ``connections[``: one database (the SaaS has no tenancy).
- accounts never imports the apps that depend on it (``hubs``, ``billing``): it reads businesses through the
  operation ``hubs.business.list`` and tells them what happened through ``accounts.signals``.

Each scan is shown to catch its positive (rule 10 of the working rules: the control catches it).
"""

import ast
from pathlib import Path

from django.conf import settings

ACCOUNTS = Path(settings.BASE_DIR) / "accounts"
DATABASE_FILES = {"services.py", "queries.py", "models.py", "admin.py"}
DATABASE_NAMES = {"connection", "connections", "transaction"}
DATABASE_ATTRIBUTES = {"objects", "select_for_update", "cursor", "atomic", "on_commit", "raw"}
DEPENDENT_APPS = ("hubs", "billing", "fiscal")


def code_files() -> list[Path]:
    return sorted(
        path
        for path in ACCOUNTS.rglob("*.py")
        if not {"tests", "migrations"} & set(path.relative_to(ACCOUNTS).parts)
    )


def database_touches(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in DATABASE_ATTRIBUTES:
            found.append(f"line {node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in DATABASE_NAMES:
            found.append(f"line {node.lineno}: {node.id}")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "django.db"
            and any(alias.name in DATABASE_NAMES for alias in node.names)
        ):
            found.append(f"line {node.lineno}: from django.db import …")
    return found


def other_databases(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "using":
            found.append(f"line {node.value.lineno}: using=")
        elif isinstance(node, ast.Attribute) and node.attr == "using":
            found.append(f"line {node.lineno}: .using(")
        elif isinstance(node, ast.Subscript) and getattr(node.value, "id", None) == "connections":
            found.append(f"line {node.lineno}: connections[…]")
    return found


def dependent_imports(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        found += [
            f"line {node.lineno}: {name}" for name in names if name.split(".")[0] in DEPENDENT_APPS
        ]
    return found


def test_only_services_and_queries_touch_the_database():
    problems = {
        str(path.relative_to(ACCOUNTS)): touches
        for path in code_files()
        if path.name not in DATABASE_FILES and (touches := database_touches(path.read_text()))
    }

    assert problems == {}


def test_the_scan_catches_a_database_touch():
    assert database_touches("User.objects.get(pk=1)") == ["line 1: .objects"]
    assert database_touches("from django.db import transaction") != []


def test_no_other_database_is_named():
    problems = {
        str(path.relative_to(ACCOUNTS)): found for path in code_files() if (found := other_databases(path.read_text()))
    }

    assert problems == {}


def test_the_scan_catches_another_database():
    assert other_databases("User.objects.using('x').all()") == ["line 1: .using("]
    assert other_databases("connections['default']") == ["line 1: connections[…]"]


def test_accounts_never_imports_the_apps_that_depend_on_it():
    problems = {
        str(path.relative_to(ACCOUNTS)): found for path in code_files() if (found := dependent_imports(path.read_text()))
    }

    assert problems == {}


def test_the_scan_catches_an_import_of_hubs():
    assert dependent_imports("from hubs.models import Hub") == ["line 1: hubs.models"]
    assert dependent_imports("import billing.services") == ["line 1: billing.services"]
