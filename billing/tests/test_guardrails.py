"""Guardrails of billing (the guardrails of django-ninja-live; CLAUDE.md, one road to the server).

- Only ``services.py`` and ``queries.py`` touch the database: the VAT engine (``vat.py``), the VIES
  client (``vies.py``), the Stripe mapping (``stripe_tax_rates.py``), the routes, schemas and events
  call them. Allowed besides: ``models.py`` (the singletons' ``save``), ``admin.py`` (Django's admin),
  the migrations and the seed loader (``seed.py`` with the models it is handed, and the command that
  runs it).
- Nowhere ``using=``, ``.using(`` nor ``connections[``: one database (the SaaS has no tenancy).
- The network: only ``vies.py`` talks to VIES (``requests``); nothing of billing calls Stripe yet (lot
  L2-B), so no module imports ``stripe``.

Each scan is shown to catch its positive (rule 10 of the working rules: the control catches it).
"""

import ast
from pathlib import Path

from django.conf import settings

BILLING = Path(settings.BASE_DIR) / "billing"
DATABASE_FILES = {
    "services.py",
    "queries.py",
    "models.py",
    "admin.py",
    "seed.py",
    "management/commands/seed_tax_rules.py",
}
DATABASE_NAMES = {"connection", "connections", "transaction"}
DATABASE_ATTRIBUTES = {
    "objects",
    "select_for_update",
    "cursor",
    "atomic",
    "on_commit",
    "raw",
    "save",
    "delete",
}


def code_files() -> list[Path]:
    return sorted(
        path
        for path in BILLING.rglob("*.py")
        if "tests" not in path.relative_to(BILLING).parts
        and "migrations" not in path.relative_to(BILLING).parts
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
            and any(a.name in DATABASE_NAMES for a in node.names)
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


def imported_modules(source: str) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def _relative(path: Path) -> str:
    return path.relative_to(BILLING).as_posix()


def test_the_scans_catch_their_positive():
    assert database_touches(
        "from django.db import transaction\nVatCheck.objects.all()\nrow.save()"
    )
    assert other_databases(
        "Model.objects.using('other')\nconnections['x']\nqs.get(using='y')"
    )
    assert imported_modules("import stripe\nfrom requests import post") == {
        "stripe",
        "requests",
    }


def test_there_is_code_to_scan():
    names = {_relative(path) for path in code_files()}

    assert {"vat.py", "vies.py", "services.py", "queries.py", "api.py"} <= names


def test_only_services_and_queries_touch_the_database():
    offenders = {
        _relative(path): touches
        for path in code_files()
        if _relative(path) not in DATABASE_FILES
        and (touches := database_touches(path.read_text(encoding="utf-8")))
    }

    assert offenders == {}


def test_nothing_names_another_database():
    offenders = {
        _relative(path): found
        for path in code_files()
        if (found := other_databases(path.read_text(encoding="utf-8")))
    }

    assert offenders == {}


def test_only_the_vies_client_talks_to_the_network_and_nothing_to_stripe_yet():
    importers = {
        _relative(path): imported_modules(path.read_text(encoding="utf-8"))
        for path in code_files()
    }

    assert [name for name, modules in importers.items() if "requests" in modules] == [
        "vies.py"
    ]
    assert [name for name, modules in importers.items() if "stripe" in modules] == []
