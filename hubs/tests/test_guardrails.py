"""Guardrails of hubs (the guardrails of django-ninja-live; CLAUDE.md, one road to the server).

- Only ``services.py`` and ``queries.py`` touch the database: no ``Model.objects``, cursor, connection
  or transaction anywhere else of hubs (routes, the ``/internal`` view, the Hub client, mails, live,
  events, schemas and the ``saas-cron`` commands call operations or service functions). Allowed besides:
  ``models.py`` (managers and ``clean``), ``admin.py`` (Django's admin), the migrations and the two seed
  loaders (``seed_taxonomy``, ``sync_hub_plans``: fixtures of reference data, run by hand).
- Nowhere ``using=``, ``.using(`` nor ``connections[``: one database (the SaaS has no tenancy).
- ``hubs`` never names the catalog's ``App`` or ``AppDoc`` (``apps/tests/test_lint.py``): it reads apps
  through ``apps.queries`` and the operations ``apps.app.*``.

Each scan is shown to catch its positive (rule 10 of the working rules: the control catches it).
"""

import ast
from pathlib import Path

from django.conf import settings

HUBS = Path(settings.BASE_DIR) / "hubs"
DATABASE_FILES = {"services.py", "queries.py", "models.py", "admin.py"}
SEED_LOADERS = {
    "management/commands/seed_taxonomy.py",
    "management/commands/sync_hub_plans.py",
}
DATABASE_NAMES = {"connection", "connections", "transaction"}
DATABASE_ATTRIBUTES = {
    "objects",
    "select_for_update",
    "cursor",
    "atomic",
    "on_commit",
    "raw",
}


def code_files() -> list[Path]:
    return sorted(
        path
        for path in HUBS.rglob("*.py")
        if "tests" not in path.relative_to(HUBS).parts
        and "migrations" not in path.relative_to(HUBS).parts
    )


def database_touches(source: str) -> list[str]:
    """Every place ``source`` reaches the database directly: ``X.objects``, a cursor, a transaction."""
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
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "connections"
        ):
            found.append(f"line {node.lineno}: connections[")
    return found


def catalog_models(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name in {"App", "AppDoc"} for alias in node.names
        ):
            found.append(
                f"line {node.lineno}: imports {', '.join(alias.name for alias in node.names)}"
            )
    return found


def test_only_services_and_queries_touch_the_database():
    offenders = {
        path.relative_to(HUBS).as_posix(): touches
        for path in code_files()
        if path.name not in DATABASE_FILES
        and path.relative_to(HUBS).as_posix() not in SEED_LOADERS
        if (touches := database_touches(path.read_text()))
    }

    assert offenders == {}


def test_the_database_scan_catches_its_positive():
    assert database_touches("from hubs.models import Hub\nHub.objects.all()\n") == [
        "line 2: .objects"
    ]
    assert database_touches("from django.db import transaction\ntransaction.atomic()\n")
    assert database_touches("member.save()\n") == []


def test_nothing_picks_another_database():
    offenders = {
        path.name: found
        for path in code_files()
        if (found := other_databases(path.read_text()))
    }

    assert offenders == {}


def test_the_database_choice_scan_catches_its_positive():
    assert other_databases("Hub.objects.using('other').all()\n") == ["line 1: .using("]
    assert other_databases("Hub.objects.create(using='x')\n") == ["line 1: using="]


def test_hubs_never_names_the_catalogs_models():
    offenders = {
        path.name: found
        for path in code_files()
        if (found := catalog_models(path.read_text()))
    }

    assert offenders == {}


def test_the_catalog_scan_catches_its_positive():
    assert catalog_models("from apps.models import App, Module\n") == [
        "line 1: imports App, Module"
    ]


def test_the_scan_sees_the_files_that_matter():
    names = {path.relative_to(HUBS).as_posix() for path in code_files()}

    assert {
        "api.py",
        "internal.py",
        "hub_client.py",
        "emails.py",
        "live.py",
        "events.py",
        "schemas.py",
        "management/commands/reconcile_hub_states.py",
        "management/commands/push_hub_snapshots.py",
    } <= names
