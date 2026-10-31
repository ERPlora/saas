"""``manage.py export_assistant_catalog``: the panel assistant's catalogue of a role, as JSON, for the QA with the real
model (layer 2, docs plan 2026-10-31 §1.5): the same tools a turn of that role offers, each with its asks in the
language asked (``live.assistant_qa.export_catalog``)."""

import io
import json

import pytest
from django.core.management import CommandError, call_command
from live.assistant_qa import export_catalog

from base import assistant
from base.operations import UserContextBuilder
from hubs.tests.conftest import make_user, plans  # noqa: F401 - shared fixtures

STORE = ("billing.plan.cancel", "billing.store.catalog", "apps.app.list")


def export(*args: str) -> list[dict]:
    out = io.StringIO()
    call_command("export_assistant_catalog", *args, stdout=out)
    return json.loads(out.getvalue())


@pytest.fixture
def account(make_user, plans):  # noqa: F811
    return make_user("lena@example.com", first_name="Lena", language="es")


def turn_catalog(rf, person, *, surface: dict) -> dict:
    """The catalogue a turn of ``person`` builds, from the context of its request."""
    request = rf.post("/api/assistant/turn")
    request.user = person
    request.session = dict(surface)
    request.LANGUAGE_CODE = "es"
    return assistant.catalog(UserContextBuilder().from_request(request))


@pytest.mark.parametrize("language", ["en", "es"])
def test_it_prints_the_catalogue_a_turn_of_the_role_offers(rf, account, language):
    printed = export("--language", language)

    assert printed == export_catalog(turn_catalog(rf, account, surface={}), language)
    assert [tool["name"] for tool in printed] == sorted(tool["name"] for tool in printed)
    assert all(len(tool["asks"]) >= 2 for tool in printed)


def test_the_role_is_the_account_by_default():
    assert export("--language", "es", "--role", "account") == export("--language", "es")


def test_the_apps_surface_has_none_of_the_stores_tools(rf, account):
    printed = export("--language", "en", "--surface", "app")

    assert printed == export_catalog(turn_catalog(rf, account, surface={"base.surface": "account"}), "en")
    assert not {tool["name"] for tool in printed} & set(STORE)
    assert set(STORE) <= {tool["name"] for tool in export("--language", "en", "--surface", "web")}


def test_it_keeps_only_the_apps_asked():
    printed = export("--language", "es", "--apps", "hubs, billing")

    assert {tool["app_label"] for tool in printed} == {"hubs", "billing"}
    assert {tool["name"] for tool in printed} == {
        tool["name"] for tool in export("--language", "es") if tool["app_label"] in {"hubs", "billing"}
    }


def test_a_role_or_a_surface_the_panel_lacks_is_refused():
    with pytest.raises(ValueError, match="owner"):
        assistant.role_catalog("owner")
    with pytest.raises(ValueError, match="kiosk"):
        assistant.role_catalog("account", surface="kiosk")


def test_an_app_without_tools_there_is_refused_by_its_name():
    with pytest.raises(CommandError, match="fiscal"):
        export("--language", "es", "--apps", "hubs,fiscal")
    with pytest.raises(CommandError, match="apps"):
        export("--language", "es", "--apps", "apps", "--surface", "app")


@pytest.mark.parametrize(
    ("args", "named"),
    [
        (("--language", "fr"), "--language"),
        (("--language", "es", "--role", "owner"), "--role"),
        (("--language", "es", "--surface", "kiosk"), "--surface"),
        ((), "--language"),
    ],
)
def test_what_it_does_not_know_is_refused(args, named):
    with pytest.raises(CommandError, match=f"argument.*{named}|arguments are required: {named}"):
        export(*args)
