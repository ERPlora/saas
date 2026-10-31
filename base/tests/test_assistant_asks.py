"""Layer 1 of the assistant's QA (docs plan 2026-10-31, the assistant's knowledge and QA, §1.4 and §4 T2): what a
person would type to the panel's assistant to ask for each tool (its ``asks``, ``live.assistant_qa``) reaches that
tool among the first ten a turn offers. Each phrase goes through the selection of a turn as the turn makes it: the
real catalogue of the person (``base.assistant.catalog`` over the context ``base.operations`` builds from the
request), with the panel's ``ALWAYS`` and its app words. No model and no network.

The panel has one role, ``account``: who may act on a business is decided inside each operation, so an owner and an
employee of a business hold the same tools. What changes a catalogue is where the panel is used: the app's account
surface sells nothing (PLAN-SAAS §3.6 point 6), so the store's tools are not in it.
"""

import pytest
from django.conf import settings
from django.core import checks
from live.assistant_qa import misses, uncovered
from live.operations import AI, registry

from base import assistant
from base.operations import UserContextBuilder
from hubs.tests.conftest import business, make_user, owner, plans, team  # noqa: F401 - shared fixtures

LANGUAGES = ("en", "es")
#: The people of a business whose catalogue is checked: its owner and one who is not.
PEOPLE = ("owner", "employee")
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


def test_every_app_with_tools_must_say_their_asks():
    """A new app with tools says what people type to ask for them in the same change that adds them (``live.E020``)."""
    assert set(settings.LIVE_ASSISTANT_ASKS_REQUIRED) == labels_with_tools()
    assert isinstance(settings.LIVE_ASSISTANT_ASKS_REQUIRED, tuple)


def test_every_tool_of_the_listed_apps_says_its_asks():
    assert [error.msg for error in checks.run_checks(tags=["live"]) if error.id == "live.E020"] == []


def test_an_owner_and_an_employee_hold_the_same_tools(rf, team):
    for surface in SURFACES:
        assert turn_catalog(rf, team["owner"], language="es", surface=surface) == turn_catalog(
            rf, team["employee"], language="es", surface=surface
        )


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("person", PEOPLE)
@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("label", sorted(labels_with_tools()))
def test_what_people_ask_reaches_the_tool(rf, team, label, language, person, surface):
    tools = turn_catalog(rf, team[person], language=language, surface=surface)
    own = of_app(tools, label)

    assert own or surface == "app"  # on the web every listed app has tools; the app's surface may sell none of one
    assert uncovered(own, language) == []
    missed = [
        miss
        for miss in misses(tools, language=language, top=10, app_words=assistant.app_words, always=assistant.ALWAYS)
        if miss.tool_name.startswith(f"{label}__")
    ]
    assert missed == []


@pytest.mark.parametrize("person", PEOPLE)
def test_where_nothing_is_sold_the_store_is_not_in_the_catalogue(rf, team, person):
    web = turn_catalog(rf, team[person], language="es", surface="web")
    app = turn_catalog(rf, team[person], language="es", surface="app")

    for sold in SOLD:
        assert sold in web
        assert sold not in app
