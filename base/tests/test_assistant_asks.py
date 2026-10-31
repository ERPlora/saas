"""Layer 1 of the assistant's QA (docs plan 2026-10-31, the assistant's knowledge and QA, §1.4 and §4 T2): what a
person would type to the panel's assistant to ask for each tool (its ``asks``, ``live.assistant_qa``) reaches that
tool among the first ten a turn offers. Each phrase goes through the selection of a turn as the turn makes it: the
real catalogue of the person (``base.assistant.catalog`` over the context ``base.operations`` builds from the
request), with the panel's ``ALWAYS`` and its app words; the asks of an ``ALWAYS`` tool are ranked without it, so they
reach it on their own words. No model and no network.

The panel has one role, ``account``: who may act on a business is decided inside each operation, so an owner and an
employee of a business hold the same tools (one regression test says so). What changes a catalogue is where the panel is used: the app's account
surface sells nothing (PLAN-SAAS §3.6 point 6), so the store's tools are not in it.
"""

import pytest
from django.conf import settings
from django.core import checks
from live.assistant import tool_name
from live.assistant_qa import misses, uncovered
from live.operations import AI, registry

from base import assistant
from base.operations import UserContextBuilder
from hubs.tests.conftest import business, make_user, owner, plans, team  # noqa: F401 - shared fixtures

LANGUAGES = ("en", "es")
#: Where the panel is used: the web, and the app's account surface (``base.surface``), which sells nothing.
SURFACES = {"web": {}, "app": {"base.surface": "account"}}
#: The tools of the store, offered on the web only.
SOLD = ("billing.plan.cancel", "billing.plan.keep", "billing.store.catalog", "billing.promo.check", "apps.app.list")


def labels_with_tools() -> set[str]:
    """The apps with at least one tool of the assistant (``AI``), whatever its permission."""
    return {op.app_label for op in registry.values() if isinstance(op.ai_spec(), AI) and assistant.is_tool(op)}


def turn_catalog(rf, person, *, language: str, surface: str) -> dict:
    """The catalogue a turn of ``person``'s builds (``base.services.assistant_turn``), from the context of its
    request."""
    request = rf.post("/api/assistant/turn")
    request.user = person
    request.session = dict(SURFACES[surface])
    request.LANGUAGE_CODE = language
    return assistant.catalog(UserContextBuilder().from_request(request))


def of_app(tools: dict, label: str) -> dict:
    return {name: op for name, op in tools.items() if op.app_label == label}


def missed(tools: dict, language: str) -> list:
    """The asks whose tool a turn does not offer among its first ten. Those of a tool always offered (``ALWAYS``) are
    ranked as any other's, with nothing put first: they reach their tool on their own words, never by its place."""
    always = {tool_name(name) for name in assistant.ALWAYS}
    ranked = {"language": language, "top": 10, "app_words": assistant.app_words}
    return [
        *(miss for miss in misses(tools, always=assistant.ALWAYS, **ranked) if miss.tool_name not in always),
        *(miss for miss in misses(tools, always=(), **ranked) if miss.tool_name in always),
    ]


def test_every_app_with_tools_must_say_their_asks():
    """A new app with tools says what people type to ask for them in the same change that adds them (``live.E020``)."""
    assert set(settings.LIVE_ASSISTANT_ASKS_REQUIRED) == labels_with_tools()
    assert isinstance(settings.LIVE_ASSISTANT_ASKS_REQUIRED, tuple)


def test_every_tool_of_the_listed_apps_says_its_asks():
    assert [error.msg for error in checks.run_checks(tags=["live"]) if error.id == "live.E020"] == []


def test_an_employee_gets_the_same_catalogue_as_the_owner(rf, team):
    for surface in SURFACES:
        assert turn_catalog(rf, team["owner"], language="es", surface=surface) == turn_catalog(
            rf, team["employee"], language="es", surface=surface
        )


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("label", sorted(labels_with_tools()))
def test_what_people_ask_reaches_the_tool(rf, owner, label, language, surface):
    tools = turn_catalog(rf, owner, language=language, surface=surface)
    own = of_app(tools, label)

    assert own or surface == "app"  # on the web every listed app has tools; the app's surface may sell none of one
    assert uncovered(own, language) == []
    assert [miss for miss in missed(tools, language) if miss.tool_name.startswith(f"{label}__")] == []


def test_where_nothing_is_sold_the_store_is_not_in_the_catalogue(rf, owner):
    web = turn_catalog(rf, owner, language="es", surface="web")
    app = turn_catalog(rf, owner, language="es", surface="app")

    for sold in SOLD:
        assert sold in web
        assert sold not in app
