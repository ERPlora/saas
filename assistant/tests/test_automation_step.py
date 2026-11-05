"""FLOW-F39 (the Hub's ``apps/flow/WORKBOOK.md``; old SAAS_ASSISTANT-F04) · ASSISTANT-F13: an automation's «Ask the
assistant» step, asked by the Hub's worker with nobody in front, is a turn of the door that answers at once
(``POST /internal/assistant/chat``): no door of its own, no field that tells it from a chat. So it spends the same
monthly messages as the chat — its first turn one, the turns that answer its tools with their ``continuation`` none —,
says whether a failure is worth trying again (``retriable``), is refused to a business that does not work, and keeps
nothing of what was said (``test_privacy.py``: ``test_a_turn_at_once_with_a_tool_leaves_nothing_either``). Its
signature is every door's (``test_internal_caller.py``, ``DOORS``).

What the door answers is kept: the Hub writes it in the run and in the log of its step. Brave's terms (§3(b)(i)) forbid
keeping its results, so this door never searches the web, even if the model asks; the chat, whose answer nobody keeps
on a server, still does. Each case runs next to the chat's, with the same key and the same model, so that a search
that is not offered at all cannot pass for one that this door refuses."""

import json
import time
from types import SimpleNamespace

import pytest
from django.core import signing
from django.test import Client
from django.utils import timezone

from assistant import queries, turn
from assistant.models import AssistantUsage
from assistant.tests.conftest import openai_answer, openai_tool_call
from assistant.tests.fake_provider import openai_chunk
from assistant.tests.doors import door, error_code, frames
from hubs.models import Hub

JSON = "/internal/assistant/chat"
STREAM = "/internal/assistant/chat/stream"
COMPLETIONS = "/v1/chat/completions"
SEARCH = "/res/v1/web/search"
SEARCH_CALL = '{"query": "ley de ejemplo", "language": "es"}'
PAGE = "https://www.boe.es/buscar/doc.php?id=BOE-A-2026-1"
TOOLS = [{"type": "function", "name": "task__task__list", "description": "Look for tasks", "parameters": {"type": "object"}}]

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


def step(business, *messages, **extra) -> dict:
    """A step's turn as the Hub's worker sends it: the task filled in, its instructions and the tools it was granted."""
    asked = list(messages) or [{"role": "user", "content": "Find the tasks of today"}]
    return {"hub": business.slug, "messages": asked, "instructions": "Nobody is watching.", "tools": TOOLS, **extra}


def spent(business) -> int:
    row = AssistantUsage.objects.filter(hub=business, month=queries.month_of(timezone.now())).first()
    return row.messages if row else 0


def test_a_step_spends_one_message_and_the_answer_to_its_tools_none(client, internal, business, answering, fake_provider):
    fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("task__task__list", "{}", call_id="call_1"))
    first = door(client, JSON, step(business))
    assert first.status_code == 200
    token = first.json()["continuation"]
    assert token
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("You have one task"))
    conversation = [
        {"role": "user", "content": "Find the tasks of today"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "task__task__list", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"rows": [{"title": "Water the plants"}]}'},
    ]

    second = door(client, JSON, step(business, *conversation, continuation=token))

    assert second.status_code == 200
    assert second.json()["output"] == [{"type": "message", "content": [{"type": "output_text", "text": "You have one task"}]}]
    assert spent(business) == 1
    assert second.json()["quota"]["used"] == 1


def two_changes() -> list:
    """The SSE of an answer that asks for two changes at once."""
    calls = [
        {"index": n, "id": f"call_{n + 1}", "type": "function", "function": {"name": "task__task__create", "arguments": "{}"}}
        for n in range(2)
    ]
    return [openai_chunk(tool_calls=calls), openai_chunk(finish="tool_calls"), openai_chunk(usage={"prompt_tokens": 1, "completion_tokens": 1}), "[DONE]"]


def told(*results) -> list[dict]:
    """The conversation the Hub sends back: the task, the calls it was asked for and one result per call."""
    calls = [{"id": call_id, "type": "function", "function": {"name": "task__task__create", "arguments": "{}"}} for call_id, _ in results]
    return [
        {"role": "user", "content": "Find the tasks of today"},
        {"role": "assistant", "content": "", "tool_calls": calls},
        *({"role": "tool", "tool_call_id": call_id, "content": content} for call_id, content in results),
    ]


CREATE = [*TOOLS, {"type": "function", "name": "task__task__create", "description": "Add a task", "parameters": {"type": "object"}}]


def test_a_step_that_answers_a_made_change_and_one_not_made_spends_nothing_more(
    client, internal, business, answering, fake_provider
):
    # FLOW-F38: with «Ask me first» one change waits at a time; after the yes the Hub sends back the made one and,
    # for the other of that answer, that it was not made: every call answered, so the pass still holds.
    fake_provider.reply("POST", COMPLETIONS, sse=two_changes())
    token = door(client, JSON, step(business, tools=CREATE)).json()["continuation"]
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("One left; the other was not made"))
    results = ("call_1", '{"title": "Call Ana"}'), ("call_2", '{"error": {"code": "not_made"}}')

    second = door(client, JSON, step(business, *told(*results), tools=CREATE, continuation=token))

    assert second.status_code == 200
    assert spent(business) == 1


def test_a_step_that_comes_back_after_its_15_minutes_spends_one_more_message(
    client, internal, business, answering, fake_provider, monkeypatch
):
    # FLOW-F38/F39: the pass of a step's tools lasts 15 minutes; a change that waited longer for a person's yes comes
    # back as a first turn of its own, one message of the month.
    fake_provider.reply("POST", COMPLETIONS, sse=two_changes())
    token = door(client, JSON, step(business, tools=CREATE)).json()["continuation"]
    later = time.time() + turn.CONTINUATION_SECONDS + 1
    monkeypatch.setattr(signing, "time", SimpleNamespace(time=lambda: later))
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Done"))
    results = ("call_1", '{"title": "Call Ana"}'), ("call_2", '{"error": {"code": "not_made"}}')

    second = door(client, JSON, step(business, *told(*results), tools=CREATE, continuation=token))

    assert second.status_code == 200
    assert spent(business) == 2


def test_a_step_of_a_spent_month_is_refused_and_waiting_does_not_mend_it(client, internal, business, answering, fake_provider):
    AssistantUsage.objects.create(hub=business, month=queries.month_of(timezone.now()), messages=30)

    response = door(client, JSON, step(business))

    assert (response.status_code, error_code(response)) == (429, "assistant.quota_exceeded")
    assert response.json()["error"]["retriable"] is False
    assert fake_provider.requests == []


@pytest.mark.parametrize(("status", "retriable"), [(503, True), (401, False)])
def test_a_step_the_provider_fails_says_whether_to_try_again_and_spends_nothing(
    client, internal, business, answering, fake_provider, status, retriable
):
    fake_provider.reply("POST", COMPLETIONS, status=status, json={"error": {"message": "no"}})

    response = door(client, JSON, step(business))

    assert response.status_code == 502
    assert response.json()["error"]["retriable"] is retriable
    assert spent(business) == 0


@pytest.mark.parametrize("status", [Hub.Status.PREPARING, Hub.Status.SUSPENDED, Hub.Status.DELETING])
def test_a_business_that_does_not_work_gets_no_step_answered(client, internal, business, answering, fake_provider, status):
    Hub.objects.filter(pk=business.pk).update(status=status)

    response = door(client, JSON, step(business))

    assert (response.status_code, error_code(response)) == (403, "hub_inactive")
    assert fake_provider.requests == []
    assert spent(business) == 0


# --- What a step keeps: no web search ------------------------------------------------------------------------------


@pytest.fixture
def brave(settings, fake_provider):
    """The web search on, as the chat has it: Brave's key, and its address at the fake provider, which finds a page."""
    settings.BRAVE_SEARCH_API_KEY = "made-up-brave-key"
    settings.ASSISTANT_SEARCH_URL = f"{fake_provider.url}{SEARCH}"
    row = {"type": "search_result", "title": "BOE", "url": PAGE, "description": "Ley de ejemplo"}
    fake_provider.reply("GET", SEARCH, always=True, json={"type": "search", "web": {"type": "search", "results": [row]}})
    return fake_provider


def model_requests(fake_provider) -> list:
    return [seen for seen in fake_provider.requests if seen.path.endswith(COMPLETIONS)]


def offered(request) -> list[str]:
    return [tool["function"]["name"] for tool in request.body["tools"]]


def searches(fake_provider) -> list:
    return [seen for seen in fake_provider.requests if seen.path.split("?")[0] == SEARCH]


def test_a_step_is_neither_offered_the_search_nor_told_of_it(client, internal, business, answering, brave):
    brave.reply("POST", COMPLETIONS, sse=openai_answer("Done"))

    assert door(client, JSON, step(business)).status_code == 200

    [asked] = model_requests(brave)
    assert offered(asked) == ["task__task__list", "current_datetime", "currency_rate"]
    assert "web_search" not in asked.body["messages"][0]["content"]


def test_the_chat_with_the_same_key_is_offered_it_and_told_of_it(client, internal, business, answering, brave):
    brave.reply("POST", COMPLETIONS, sse=openai_answer("Done"))

    frames(door(client, STREAM, step(business)))

    [asked] = model_requests(brave)
    assert offered(asked) == ["task__task__list", "current_datetime", "currency_rate", "web_search"]
    assert "`web_search`" in asked.body["messages"][0]["content"]


def test_a_search_the_model_asks_a_step_for_reaches_nobody_and_it_hears_why(client, internal, business, answering, brave):
    brave.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", SEARCH_CALL, call_id="call_s"))
    brave.reply("POST", COMPLETIONS, sse=openai_answer("I could not search the web."))

    answer = door(client, JSON, step(business))

    assert answer.status_code == 200
    assert searches(brave) == []
    _first, second = model_requests(brave)
    told = json.loads(second.body["messages"][-1]["content"])
    assert told["code"] == "web_search.not_here"
    assert not {"results", "sources"} & set(told)
    assert "web_search" not in offered(second)
    body = answer.json()
    assert body["continuation"] is None
    assert body["output"] == [{"type": "message", "content": [{"type": "output_text", "text": "I could not search the web."}]}]


def test_the_chat_asked_the_same_does_search_and_writes_the_source(client, internal, business, answering, brave):
    brave.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", SEARCH_CALL, call_id="call_s"))
    brave.reply("POST", COMPLETIONS, sse=openai_answer("The law changed."))

    got = frames(door(client, STREAM, step(business)))

    assert len(searches(brave)) == 1
    assert {"type": "text_delta", "text": f"\n\n{PAGE}"} in got


def test_a_tool_of_the_hub_named_as_the_search_is_no_way_round(client, internal, business, answering, brave):
    named = {"type": "function", "name": "web_search", "description": "The Hub's", "parameters": {"type": "object"}}
    brave.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", SEARCH_CALL, call_id="call_s"))
    brave.reply("POST", COMPLETIONS, sse=openai_answer("I could not search the web."))

    body = door(client, JSON, step(business, tools=[*TOOLS, named])).json()

    assert searches(brave) == []
    assert "web_search" not in offered(model_requests(brave)[0])
    assert [item["type"] for item in body["output"]] == ["message"]
    assert body["continuation"] is None


def test_a_search_refused_to_a_step_spends_nothing_of_the_chats_budget(client, internal, business, answering, brave, settings):
    settings.ASSISTANT_WEB_SEARCH_RATELIMIT = "1/h"
    brave.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", SEARCH_CALL, call_id="call_s"))
    brave.reply("POST", COMPLETIONS, sse=openai_answer("I could not search the web."))
    door(client, JSON, step(business))
    brave.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", SEARCH_CALL, call_id="call_c"))
    brave.reply("POST", COMPLETIONS, sse=openai_answer("The law changed."))

    frames(door(client, STREAM, step(business)))

    assert len(searches(brave)) == 1
    assert "results" in json.loads(model_requests(brave)[-1].body["messages"][-1]["content"])
