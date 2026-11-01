"""Layer 1 of the assistant's QA (docs plan 2026-10-31, the assistant's knowledge and QA, §1.4 and §4 T2): what a
person would type to the panel's assistant to ask for each tool (its ``asks``, ``live.assistant_qa``) reaches that
tool among the first ten a turn offers. Each phrase goes through the selection of a turn as the turn makes it: the
real catalogue of the person (``base.assistant.catalog`` over the context ``base.operations`` builds from the
request), with the panel's ``ALWAYS``, its app words, its words (``SYNONYMS``) and its how-to search (``HOWTO``); the
asks of an ``ALWAYS`` tool are ranked without it, so they reach it on their own words. No model and no network.

How far the asks reach their tool on the other asks' words (``own_asks=False``: as a person's new phrase would) is
printed as a warning per app and language (``AsksReach``), information only; the phrases that reach so only through
what ``live`` reads since live#22 or the panel's words (``REACH_ON_OTHERS``) must.

The panel has one role, ``account``: who may act on a business is decided inside each operation, so an owner and an
employee of a business hold the same tools (one regression test says so). What changes a catalogue is where the panel is used: the app's account
surface sells nothing (PLAN-SAAS §3.6 point 6), so the store's tools are not in it.
"""

import warnings
from functools import cache

import pytest
from django.conf import settings
from django.core import checks
from live.assistant import asks_of, tool_name
from live.assistant_qa import Reach, misses, report, uncovered
from live.operations import AI, registry

from base import assistant
from base.operations import ACCOUNT_ROLE, UserContextBuilder
from hubs.tests.conftest import business, make_user, owner, plans, team  # noqa: F401 - shared fixtures

LANGUAGES = ("en", "es")
#: Where the panel is used: the web, and the app's account surface (``base.surface``), which sells nothing.
SURFACES = {"web": {}, "app": {"base.surface": "account"}}
#: The tools of the store, offered on the web only.
SOLD = ("billing.plan.cancel", "billing.plan.keep", "billing.store.catalog", "billing.promo.check", "apps.app.list")
#: Asks that reach their tool on the other asks' words too only because of what ``live`` reads since live#22 or of
#: what the panel passes a turn: its words (``base.assistant.SYNONYMS``: a person's own, other, new or old «tienda»
#: and a «shop» are a business) and its how-to search (``HOWTO``). The first ten were kept out of the asks until then.
REACH_ON_OTHERS = (
    ("accounts.preferences.update", "en", "turn off the alerts from my businesses"),
    ("accounts.preferences.update", "es", "no quiero recibir avisos de los negocios"),
    ("accounts.preferences.get", "es", "¿tengo activados los avisos de mis negocios?"),
    ("hubs.business.delete", "en", "get rid of Bar Manolo"),
    ("hubs.business.delete", "es", "quiero cerrar para siempre la tienda vieja"),
    ("hubs.address.propose", "es", "¿qué enlace tendría mi nueva tienda?"),
    ("hubs.data_copy.list", "es", "quiero descargarme los datos de la peluquería"),
    ("assistant.docs.search", "en", "how do I invite someone to my business?"),
    ("assistant.docs.search", "en", "how do I connect WhatsApp to my business?"),
    ("assistant.docs.search", "es", "¿cómo invito a un empleado?"),
    ("hubs.business.delete", "en", "close down my old shop"),
    ("hubs.business.list", "en", "list my shops"),
)


class AsksReach(UserWarning):
    """How many asks of each app reach their tool among the first ten on the other asks' words: information only."""


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


def ranking() -> dict:
    """How a turn ranks (``base.assistant.relevant``): with the panel's app words, its words and its how-to search."""
    return {"top": 10, "app_words": assistant.app_words, "synonyms": assistant.SYNONYMS, "howto": assistant.HOWTO}


def always_offered() -> set[str]:
    return {tool_name(name) for name in assistant.ALWAYS}


def missed(tools: dict, language: str) -> list:
    """The asks whose tool a turn does not offer among its first ten. Those of a tool always offered (``ALWAYS``) are
    ranked as any other's, with nothing put first: they reach their tool on their own words, never by its place."""
    always = always_offered()
    return [
        *(miss for miss in misses(tools, language=language, always=assistant.ALWAYS, **ranking())
          if miss.tool_name not in always),
        *(miss for miss in misses(tools, language=language, always=(), **ranking()) if miss.tool_name in always),
    ]


@cache
def reach(language: str) -> tuple[Reach, ...]:
    """Where each ask in ``language`` brings its tool in the catalogue of the panel's role (``role_catalog``, the turn's
    of every account on the web), counting itself and on the other asks' words (``live.assistant_qa.report``); the
    tools of ``ALWAYS`` ranked as in ``missed``."""
    tools = assistant.role_catalog(ACCOUNT_ROLE)
    always = always_offered()
    return tuple(
        sorted(
            [
                *(one for one in report(tools, language, always=assistant.ALWAYS, **ranking())
                  if one.tool_name not in always),
                *(one for one in report(tools, language, always=(), **ranking()) if one.tool_name in always),
            ]
        )
    )


def reach_on_others(language: str) -> dict[str, tuple[int, int]]:
    """Per app with tools: how many of its asks in ``language`` reach their tool among the first ten on the other
    asks' words, and of how many."""
    found: dict[str, tuple[int, int]] = {}
    for one in reach(language):
        label = one.tool_name.split("__", 1)[0]
        within, total = found.get(label, (0, 0))
        found[label] = (within + one.unseen_within, total + len(one.asks))
    return found


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


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_phrase_once_out_of_reach_is_an_ask_and_reaches_on_the_others_words(language):
    tools = assistant.role_catalog(ACCOUNT_ROLE)
    unseen = {(one.tool_name, ask): position for one in reach(language) for ask, position in zip(one.asks, one.unseen)}
    phrases = [(name, ask) for name, lang, ask in REACH_ON_OTHERS if lang == language]

    assert phrases
    assert [ask for name, ask in phrases if ask not in asks_of(tools[name]).get(language, ())] == []
    far = [(ask, unseen[(tool_name(name), ask)]) for name, ask in phrases]
    assert [(ask, position) for ask, position in far if position is None or position > 10] == []


@pytest.mark.parametrize("language", LANGUAGES)
def test_how_many_asks_reach_on_the_others_words_is_printed_per_app(language):
    by_app = reach_on_others(language)

    assert set(by_app) == labels_with_tools()
    assert all(0 <= within <= total for within, total in by_app.values())
    assert sum(total for _, total in by_app.values()) == sum(
        len(asks_of(op).get(language, ())) for op in assistant.role_catalog(ACCOUNT_ROLE).values()
    )
    summary = ", ".join(f"{label} {within}/{total}" for label, (within, total) in sorted(by_app.items()))
    warnings.warn(AsksReach(f"asks reaching their tool among the first 10 on the others' words, {language}: {summary}"),
                  stacklevel=1)
