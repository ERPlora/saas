"""ASSISTANT-F25 · The panel's words for the writes of its assistant (``assistant/frontend/options.ts``, plan
2026-10-30-asistente-saas §6): the card and the receipt of a write name it by its verb, in English and in Spanish.

The catalogue of the entry (``frontend/locale/<lang>.json``, ``saas.assistant.card``) has one verb per write the
assistant of an account may run (``operations.<app>.<entity>.<action>``) and none for one it does not run, and a verb
for every action of those writes (``actions``), so a write that comes later still says what it does before its own
verb is written. A new ``AI`` write, or one that goes ``INTERNAL``, fails here until the catalogue follows (the Hub's
guard: ``hub/base/tests/test_assistant.py``).
"""

import json
from pathlib import Path

import pytest

from base import assistant
from hubs.tests.conftest import ctx_for, make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

LOCALE = Path(__file__).resolve().parents[2] / "frontend" / "locale"


def catalogue(language: str) -> dict:
    return json.loads((LOCALE / f"{language}.json").read_text(encoding="utf-8"))["saas"]["assistant"]["card"]


def named(operations: dict) -> set[str]:
    return {
        f"{app}.{entity}.{action}"
        for app, entities in operations.items()
        for entity, actions in entities.items()
        for action in actions
    }


@pytest.fixture
def writes(make_user, plans):
    """The writes an account's assistant may run: its catalogue's commands."""
    tools = assistant.catalog(ctx_for(make_user("lena@example.com")))
    return {name for name, op in tools.items() if op.kind == "command"}


def test_the_writes_are_the_ones_this_guard_was_written_for(writes):
    """The guard reads a real catalogue: the account's businesses and its plans are among its writes."""
    assert {"hubs.business.create", "hubs.business.delete", "billing.plan.cancel", "accounts.session.close"} <= writes
    assert "accounts.apikey.create" not in writes and "hubs.business.open" not in writes


@pytest.mark.parametrize("language", ["en", "es"])
def test_every_write_has_its_own_verb_and_no_verb_is_of_a_write_it_does_not_run(writes, language):
    verbs = catalogue(language)["operations"]

    assert named(verbs) == writes
    for name in writes:
        app, entity, action = name.split(".")
        assert verbs[app][entity][action].strip(), name


@pytest.mark.parametrize("language", ["en", "es"])
def test_every_action_of_those_writes_has_its_verb(writes, language):
    actions = catalogue(language)["actions"]

    assert {name.split(".")[-1] for name in writes} <= set(actions)
    assert all(text.strip() for text in actions.values())
