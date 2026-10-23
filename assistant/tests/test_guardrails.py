"""Guardrails of the assistant (CLAUDE.md, one road to the server), the scans of ``hubs/tests/test_guardrails.py``.

- Only ``services.py`` and ``queries.py`` touch the database: the clients of the providers, the commands and the
  tester call operations. Allowed besides: ``models.py`` and ``admin.py`` (Django's admin) and the migrations.
- Nowhere ``using=``, ``.using(`` nor ``connections[``.
- A provider's key never reaches a log: no logging call names the key, the token nor what was typed.

Each scan is shown to catch its positive (rule 10 of the working rules: the control catches it).
"""

import ast
from pathlib import Path

from django.conf import settings

from hubs.tests.test_guardrails import database_touches, other_databases

ASSISTANT = Path(settings.BASE_DIR) / "assistant"
DATABASE_FILES = {"services.py", "queries.py", "models.py", "admin.py"}
SECRETS = {"api_key", "plaintext", "token", "new_key", "secret", "key", "get_secret_value"}
LOG_CALLS = {"debug", "info", "warning", "error", "exception", "critical"}


def code_files() -> list[Path]:
    return sorted(
        path
        for path in ASSISTANT.rglob("*.py")
        if not {"tests", "migrations"} & set(path.relative_to(ASSISTANT).parts)
    )


def logged_secrets(source: str) -> list[str]:
    """Every logging call that passes a name or attribute that is a provider's key."""
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
        path.relative_to(ASSISTANT).as_posix(): touches
        for path in code_files()
        if path.name not in DATABASE_FILES
        if (touches := database_touches(path.read_text()))
    }

    assert offenders == {}


def test_nothing_picks_another_database():
    offenders = {
        path.relative_to(ASSISTANT).as_posix(): found
        for path in code_files()
        if (found := other_databases(path.read_text()))
    }

    assert offenders == {}


def test_no_log_names_a_provider_key():
    offenders = {
        path.relative_to(ASSISTANT).as_posix(): found
        for path in code_files()
        if (found := logged_secrets(path.read_text()))
    }

    assert offenders == {}


def test_the_log_scan_catches_its_positive():
    assert logged_secrets("logger.info('x %s', credential.api_key)") == ["line 1: logs api_key"]
    assert set(logged_secrets("logger.warning('x %s', data.api_key.get_secret_value())")) == {
        "line 1: logs get_secret_value",
        "line 1: logs api_key",
    }


def test_the_database_scan_catches_its_positive():
    assert database_touches("AIProvider.objects.all()") == ["line 1: .objects"]
