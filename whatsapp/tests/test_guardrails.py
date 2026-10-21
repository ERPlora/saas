"""Guardrails of whatsapp (CLAUDE.md, one road to the server), the same scans as ``hubs/tests/test_guardrails.py``.

- Only ``services.py`` and ``queries.py`` touch the database: the doors (``internal.py``), Meta's webhook, the
  media route, Meta's client, the Hub's client, the mails and the ``saas-cron`` commands call operations.
  Allowed besides: ``models.py`` and ``admin.py`` (Django's admin) and the migrations.
- Nowhere ``using=``, ``.using(`` nor ``connections[``.
- The Meta credentials never reach a log: no logging call names the token, the PIN or the app's secret.

Each scan is shown to catch its positive (rule 10 of the working rules: the control catches it).
"""

import ast
from pathlib import Path

from django.conf import settings

from hubs.tests.test_guardrails import database_touches, other_databases

WHATSAPP = Path(settings.BASE_DIR) / "whatsapp"
DATABASE_FILES = {"services.py", "queries.py", "models.py", "admin.py"}
SECRETS = {"access_token", "registration_pin", "WHATSAPP_APP_SECRET", "app_secret", "token", "pin"}
LOG_CALLS = {"debug", "info", "warning", "error", "exception", "critical"}


def code_files() -> list[Path]:
    return sorted(
        path
        for path in WHATSAPP.rglob("*.py")
        if "tests" not in path.relative_to(WHATSAPP).parts
        and "migrations" not in path.relative_to(WHATSAPP).parts
    )


def logged_secrets(source: str) -> list[str]:
    """Every logging call that passes a name or attribute that is a Meta credential."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_CALLS):
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            for inner in ast.walk(argument):
                name = inner.id if isinstance(inner, ast.Name) else inner.attr if isinstance(inner, ast.Attribute) else None
                if name in SECRETS:
                    found.append(f"line {node.lineno}: logs {name}")
    return found


def test_only_services_and_queries_touch_the_database():
    offenders = {
        path.relative_to(WHATSAPP).as_posix(): touches
        for path in code_files()
        if path.name not in DATABASE_FILES
        if (touches := database_touches(path.read_text()))
    }

    assert offenders == {}


def test_nothing_picks_another_database():
    offenders = {
        path.relative_to(WHATSAPP).as_posix(): found
        for path in code_files()
        if (found := other_databases(path.read_text()))
    }

    assert offenders == {}


def test_no_log_names_a_meta_credential():
    offenders = {
        path.relative_to(WHATSAPP).as_posix(): found
        for path in code_files()
        if (found := logged_secrets(path.read_text()))
    }

    assert offenders == {}


def test_the_log_scan_catches_its_positive():
    assert logged_secrets("logger.info('x %s', number.access_token)") == ["line 1: logs access_token"]
    assert logged_secrets("logger.error('x', extra={'t': token})") == ["line 1: logs token"]
    assert logged_secrets("logger.info('x %s', number.display_phone)") == []


def test_the_scan_sees_the_files_that_matter():
    names = {path.name for path in code_files()}

    assert {"models.py", "crypto.py", "fields.py"} <= names
