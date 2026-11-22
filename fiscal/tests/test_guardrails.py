"""Guardrails of fiscal (the guardrails of django-ninja-live; CLAUDE.md, one road to the server).

- Only ``services`` and ``queries`` (a file or a package) touch the database: no ``Model.objects``, cursor,
  connection or transaction anywhere else of fiscal (the route, the ``/internal`` views, live, events, schemas, the
  encryption and the documents' checks call operations or plain functions). Allowed besides: ``models.py``
  (managers), ``admin.py`` (Django's admin) and the migrations.
- Nowhere ``using=``, ``.using(`` nor ``connections[``: one database (the SaaS has no tenancy).

The scans are ``hubs/tests/test_guardrails.py``'s, over fiscal; each is shown to catch its positive.
"""

from pathlib import Path

from django.conf import settings

from hubs.tests.test_guardrails import database_touches, may_touch_the_database, other_databases

FISCAL = Path(settings.BASE_DIR) / "fiscal"


def code_files() -> list[Path]:
    return sorted(
        path
        for path in FISCAL.rglob("*.py")
        if "tests" not in path.relative_to(FISCAL).parts and "migrations" not in path.relative_to(FISCAL).parts
    )


def test_only_services_and_queries_touch_the_database():
    offenders = {
        path.relative_to(FISCAL).as_posix(): touches
        for path in code_files()
        if not may_touch_the_database(path.relative_to(FISCAL).as_posix())
        if (touches := database_touches(path.read_text()))
    }

    assert offenders == {}


def test_the_database_scan_catches_its_positive():
    assert database_touches("from fiscal.models import RepresentationGrant\nRepresentationGrant.objects.all()\n") == [
        "line 2: .objects"
    ]


def test_nothing_picks_another_database():
    offenders = {path.name: found for path in code_files() if (found := other_databases(path.read_text()))}

    assert offenders == {}


def test_the_database_choice_scan_catches_its_positive():
    assert other_databases("RepresentationGrant.objects.using('other').all()\n") == ["line 1: .using("]


def test_a_module_of_a_packaged_door_may_touch_the_database():
    assert may_touch_the_database("services.py")
    assert may_touch_the_database("services/__init__.py")
    assert may_touch_the_database("services/representation_grants.py")
    assert not may_touch_the_database("internal.py")
    assert not may_touch_the_database("services/inner/deep.py")


def test_the_scan_sees_the_files_that_matter():
    names = {path.relative_to(FISCAL).as_posix() for path in code_files()}

    assert {
        "api.py",
        "internal.py",
        "live.py",
        "events.py",
        "schemas.py",
        "crypto.py",
        "documents.py",
        "checks.py",
        "services/__init__.py",
        "queries.py",
        "admin.py",
    } <= names
