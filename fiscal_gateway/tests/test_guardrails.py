"""Guardrails of the fiscal gateway (the guardrails of django-ninja-live; CLAUDE.md, one road to the server).

- Only ``queries.py`` touches the database: no ``Model.objects``, cursor, connection or transaction in the
  views, the AEAT's client, the seal or the schemas (the gateway writes nothing).
- Nowhere ``using=``, ``.using(`` nor ``connections[``: one database (the SaaS has no tenancy).

The scans are ``hubs/tests/test_guardrails.py``'s, over the gateway; each is shown to catch its positive in
``fiscal/tests/test_guardrails.py``.
"""

from pathlib import Path

from django.conf import settings

from hubs.tests.test_guardrails import database_touches, other_databases

GATEWAY = Path(settings.BASE_DIR) / "fiscal_gateway"
DATABASE_FILES = {"queries.py"}


def code_files() -> list[Path]:
    return sorted(
        path
        for path in GATEWAY.rglob("*.py")
        if "tests" not in path.relative_to(GATEWAY).parts
    )


def test_only_queries_touches_the_database():
    offenders = {
        path.name: touches
        for path in code_files()
        if path.name not in DATABASE_FILES
        if (touches := database_touches(path.read_text()))
    }

    assert offenders == {}


def test_nothing_picks_another_database():
    offenders = {
        path.name: found
        for path in code_files()
        if (found := other_databases(path.read_text()))
    }

    assert offenders == {}


def test_the_scan_sees_the_files_that_matter():
    names = {path.name for path in code_files()}

    assert {"internal.py", "aeat.py", "seal.py", "schemas.py", "queries.py"} <= names
