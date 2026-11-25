"""ASSISTANT-F25 · The search the panel's assistant has in every turn (``base.assistant.find_tools``): a turn offers only
the tools the account's words name best, so when none of them does what was asked, the model searches the account's
whole catalogue for the task and the next round of the same request offers what it found. It is the Hub's same search
(``live.assistant.offered``), with the panel's tools and words.

Before it, a phrase that shared no word with the tool it needed left that tool out of the turn, and the model could not
ask for it: «everything's way too bright at night, can you darken this screen?» was offered no way to change the
appearance of the account.
"""

import dataclasses
import json

import pytest
from django.contrib.auth import get_user_model
from live import assistant as shared
from live.operations import get

from base import assistant
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db

SEARCH = "base.assistant.find_tools"
DARKEN = "everything's way too bright at night, can you darken this screen?"


@pytest.fixture
def account():
    return get_user_model().objects.create_user(email="lena@example.com", password=None, first_name="Lena")


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def call(name: str, arguments: dict | str, call_id: str) -> dict:
    """A tool the model asked for, as the browser sends it back pending."""
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"call_id": call_id, "name": shared.tool_name(name), "arguments": raw}


def asked(pending: dict) -> dict:
    """The model's message asking for ``pending``, as the browser keeps it in the conversation."""
    function = {"name": pending["name"], "arguments": pending["arguments"]}
    return {"role": "assistant", "content": "", "tool_calls": [{"id": pending["call_id"], "type": "function", "function": function}]}


def answer(pending: dict, content: str = "{}") -> dict:
    return {"role": "tool", "tool_call_id": pending["call_id"], "content": content}


def turn(context, *messages: dict, pending: tuple[dict, ...] = ()) -> dict:
    op = get("base.assistant.turn")
    return op(context, op.input(messages=list(messages), pending=list(pending))).model_dump(mode="json")


def names(tools: list[dict]) -> list[str]:
    return [tool["name"] for tool in tools]


def searched(context, query: str) -> list[str]:
    op = get(SEARCH)
    return names(op(context, op.input(query=query)).model_dump(mode="json")["tools"])


def test_the_tool_darken_this_screen_left_out_is_offered_once_the_model_searches_for_it(account):
    context = ctx_for(account, "en")
    update = shared.tool_name("accounts.preferences.update")
    first = turn(context, user(DARKEN))
    assert update not in names(first["tools"])  # positive control: the words alone name no appearance
    assert names(first["tools"])[-1] == shared.tool_name(SEARCH)

    search = call(SEARCH, {"query": "change the theme to dark mode"}, "s1")
    second = turn(context, user(DARKEN), asked(search), pending=(search,))
    assert [row["outcome"] for row in second["executed"]] == ["ok"]
    assert update in second["append"][0]["content"]
    assert update in names(second["tools"])

    write = call("accounts.preferences.update", {"theme_mode": "dark"}, "w1")
    third = turn(context, user(DARKEN), asked(search), *second["append"], asked(write), pending=(write,))
    assert third["confirm"] is not None
    assert third["pending"][0]["call_id"] == "w1"


@pytest.mark.parametrize("language", ["en", "es"])
def test_every_turn_offers_the_search_last_within_the_share_of_a_turn(account, language):
    for said in ("zzz", "show me my businesses, their plans, invoices, people and subscriptions"):
        tools = names(turn(ctx_for(account, language), user(said))["tools"])
        assert tools[-1] == shared.tool_name(SEARCH)
        assert len(tools) <= shared.MAX_TOOLS


def test_the_search_is_the_assistants_own_and_takes_no_place_from_the_accounts_tools(account):
    """It is no tool of the account's (``base.assistant.*``): it never ranks, so every tool a turn offers keeps the
    place its words give it, and the search takes the last one."""
    tools = assistant.catalog(ctx_for(account, "en"))
    assert SEARCH not in tools
    said = "show me my businesses, their plans, invoices, people and subscriptions"
    ranked = [op.name for op in shared.relevant(tools, [said], "en", **assistant.ranking())]
    assert len(ranked) > assistant.PLACES  # positive control: the words name more tools than fit
    offered = [op.name for op in assistant.relevant(tools, [said], "en")]
    assert offered == [*ranked[: assistant.PLACES], SEARCH]


def test_a_search_finds_the_tools_of_the_task_with_what_each_does(account):
    op = get(SEARCH)
    found = op(ctx_for(account, "en"), op.input(query="switch to dark mode")).model_dump(mode="json")["tools"]
    assert names(found)[0] == shared.tool_name("accounts.preferences.update")
    assert all(tool["description"] for tool in found)
    assert len(found) <= shared.FOUND


def test_a_search_never_finds_what_every_turn_already_offers(account):
    found = searched(ctx_for(account, "en"), "list my businesses and search the documentation")
    assert found
    assert not set(found) & {shared.tool_name(name) for name in (*assistant.ALWAYS, SEARCH)}


def test_where_nothing_is_sold_a_search_never_finds_the_stores_tools(account, rf):
    request = rf.get("/")
    request.session = {"base.surface": "account"}
    unsold = dataclasses.replace(ctx_for(account, "en"), request=request)
    task = "cancel the plan of a business"
    assert shared.tool_name("billing.plan.cancel") in searched(ctx_for(account, "en"), task)
    assert shared.tool_name("billing.plan.cancel") not in searched(unsold, task)


def test_a_search_the_model_wrote_wrong_finds_nothing_and_the_turn_goes_on(account):
    context = ctx_for(account, "en")
    wrong = call(SEARCH, "switch to dark mode", "s1")
    plan = turn(context, user(DARKEN), asked(wrong), pending=(wrong,))
    assert [row["outcome"] for row in plan["executed"]] != ["ok"]  # the model hears its search was not done
    assert names(plan["tools"]) == names(turn(context, user(DARKEN))["tools"])


def test_a_search_of_an_earlier_request_no_longer_takes_a_place_in_the_turn(account):
    """A turn ranks by the person's last two messages, and what the model searched for counts as long as they do."""
    context = ctx_for(account, "en")
    search = call(SEARCH, {"query": "change the theme to dark mode"}, "s1")
    done = [user(DARKEN), asked(search), answer(search), {"role": "assistant", "content": "Done."}]
    later = [user("Thanks."), user("What do I pay a month?")]
    assert names(turn(context, *done, *later)["tools"]) == names(turn(context, *later)["tools"])
    assert shared.tool_name("accounts.preferences.update") in names(turn(context, *done, user("dark, please"))["tools"])


@pytest.mark.parametrize("sells", [True, False])
def test_the_instructions_say_to_search_before_saying_it_cannot_be_done(sells):
    text = assistant.instructions(language="en", account="Lena", screens={}, sells=sells)
    assert f"`{shared.tool_name(SEARCH)}`" in text
    assert "before you search for it" in text
