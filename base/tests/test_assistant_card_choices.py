"""ASSISTANT-F25 · A value of a closed list on the card of the panel's assistant: «English», «Oscuro» or «España» says
which option was chosen, never which datum it is. ``live`` marks it (``live.assistant.CHOICE``) and the card's line of
``@erplora/ui`` names it even when it goes first: asked only for the language, the card reads «Cambiar en Cuenta: Idioma:
English», never «Cambiar en Cuenta: English»."""

import json

import pytest
from live.assistant import CHOICE, resolved
from live.assistant.tools import input_schema, risk
from live.operations import Operation
from live.operations import get as get_operation

from assistant.tests.conftest import answering, fake_provider, openai_key, provider  # noqa: F401 - the gateway's fixtures
from assistant.tests.doors import frames
from base import assistant
from base.tests.test_assistant_turn import account, ask, post_turn, signed_in  # noqa: F401 - the turn's fixtures
from hubs.tests.conftest import create_business, ctx_for, make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db


def drawn(account, op: Operation, arguments: dict, name: str, language: str) -> dict:
    """The datum ``name`` of the card of ``op`` with ``arguments``, in ``language``."""
    fields = assistant.card(op, arguments, ctx_for(account, language))["fields"]
    return next(field for field in fields if field["name"] == name)


@pytest.mark.parametrize(
    ("arguments", "language", "said"),
    [
        ({"language": "en"}, "es", ("Idioma", "English")),
        ({"language": "es"}, "en", ("Language", "Español")),
        ({"theme_mode": "dark"}, "es", ("Apariencia", "Oscuro")),
        ({"theme_mode": "dark"}, "en", ("Appearance", "Dark")),
    ],
)
def test_the_one_preference_asked_is_said_by_its_label_and_marked_a_choice(account, arguments, language, said):
    [name] = arguments
    shown = drawn(account, get_operation("accounts.preferences.update"), arguments, name, language)

    assert ((shown["label"], shown["value"]), shown["kind"], shown.get(CHOICE)) == (said, "text", True)


def test_the_country_of_a_payer_is_marked_a_choice_and_its_business_is_not(account):
    hub = create_business(account, name="Bar Lena")
    arguments = {"hub_id": str(hub.id), "billing_country": "ES"}
    op = get_operation("hubs.billing_profile.update")

    country = drawn(account, op, arguments, "billing_country", "es")
    business = drawn(account, op, arguments, "hub_id", "es")

    assert ((country["label"], country["value"]), country.get(CHOICE)) == (("País", "España"), True)
    assert (business["value"], business.get(CHOICE)) == ("Bar Lena", None)


def test_every_closed_list_of_a_normal_write_of_the_panel_is_said_as_a_choice(account):
    """Each write of the account's catalogue, asked only for the first value of each closed list it takes."""
    ctx = ctx_for(account, "es")
    lists = []
    for op in assistant.catalog(ctx).values():
        if op.kind != "command" or risk(op) != "normal":
            continue
        schema = input_schema(op)
        for name, prop in schema.get("properties", {}).items():
            enum = resolved(prop, schema.get("$defs", {})).get("enum", ())
            value = next((one for one in enum if one not in ("", None) and not isinstance(one, bool)), None)
            if value is not None:
                lists.append((op, name, value))

    shown = {f"{op.name}.{name}": drawn(account, op, {name: value}, name, "es") for op, name, value in lists}

    assert {"accounts.preferences.update.language", "accounts.preferences.update.theme_mode"} <= set(shown)
    assert [key for key, datum in shown.items() if datum.get(CHOICE) is not True] == []


def test_a_name_is_no_choice(account):
    shown = drawn(account, get_operation("hubs.business.create"), {"name": "Bar Lena"}, "name", "es")

    assert (shown["value"], shown.get(CHOICE)) == ("Bar Lena", None)


def test_the_card_a_turn_sends_to_the_screen_keeps_the_mark(signed_in, account, answering, fake_provider):
    """The turn's schema (``AssistantFieldOut``) lets the mark through: without it the screen says «English» bare."""
    pending = {"call_id": "c1", "name": "accounts__preferences__update", "arguments": json.dumps({"language": "en"})}

    got = frames(post_turn(signed_in, {"messages": [ask("Put the panel in English")], "pending": [pending]}))

    [shown] = got[0]["card"]["fields"]
    assert (shown["name"], shown["value"], shown.get(CHOICE)) == ("language", "English", True)
