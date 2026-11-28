"""Guardrails of the assistant (CLAUDE.md, one road to the server), the scans of ``hubs/tests/test_guardrails.py``.

- Only ``services`` and ``queries`` (a file or a package) touch the database: the clients of the providers, the
  commands and the tester call operations. Allowed besides: ``models.py`` and ``admin.py`` (Django's admin) and the
  migrations.
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
DATABASE_PACKAGES = {"services", "queries", "models", "admin"}
SECRETS = {"api_key", "plaintext", "token", "new_key", "secret", "key", "get_secret_value"}
LOG_CALLS = {"debug", "info", "warning", "error", "exception", "critical"}


def code_files() -> list[Path]:
    return sorted(
        path
        for path in ASSISTANT.rglob("*.py")
        if not {"tests", "migrations"} & set(path.relative_to(ASSISTANT).parts)
    )


def may_touch_the_database(relative: str) -> bool:
    """A door file or a module of a door package one level deep (``services/__init__.py``)."""
    parts = relative.split("/")
    return relative in DATABASE_FILES or (len(parts) == 2 and parts[0] in DATABASE_PACKAGES)


def is_log_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_CALLS


def name_of(node: ast.AST) -> str | None:
    """The name a variable or an attribute reads."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def logged_secrets(source: str) -> list[str]:
    """Every logging call that passes a name or attribute that is a provider's key."""
    found = []
    for call in filter(is_log_call, ast.walk(ast.parse(source))):
        for argument in [*call.args, *(keyword.value for keyword in call.keywords)]:
            names = (name_of(inner) for inner in ast.walk(argument))
            found += [f"line {call.lineno}: logs {name}" for name in names if name in SECRETS]
    return found


def test_only_services_and_queries_touch_the_database():
    offenders = {
        path.relative_to(ASSISTANT).as_posix(): touches
        for path in code_files()
        if not may_touch_the_database(path.relative_to(ASSISTANT).as_posix())
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


def test_a_module_of_a_packaged_door_may_touch_the_database():
    assert may_touch_the_database("services.py")
    assert may_touch_the_database("services/__init__.py")
    assert may_touch_the_database("services/model_choice.py")
    assert not may_touch_the_database("turn.py")
    assert not may_touch_the_database("services/inner/deep.py")
    assert not may_touch_the_database("providers/services/openai.py")
