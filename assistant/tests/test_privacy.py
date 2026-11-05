"""ASSISTANT-F17 (ASSISTANT-G49) · Do not keep the conversation: erplora.com uses it for the call and forgets it.

No table, log, audit entry nor event of the outbox keeps what a person wrote or what the model answered: only
numbers (messages, tokens, cost). The old product kept the first 50 characters of a dictation in its log and the
provider's error words could carry them (SAAS_ASSISTANT-F09, «parcial»): here the provider's words of a failure never
reach a log either. Checked by dumping the whole database and reading every log record of every logger.
"""

import io
import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client

from assistant.tests.conftest import openai_answer, openai_tool_call
from assistant.tests.doors import door, frames

SECRET_QUESTION = "Mi cliente Rosalía Quintanar debe 400 euros"
SECRET_ANSWER = "Apunta la deuda de Rosalía Quintanar"
SECRET_RESULT = "Una página sobre Rosalía Quintanar"
INSTRUCTIONS = "Negocio Bar Manolo, cajera Iratxe Bengoetxea"
SECRET_ADDRESS = "https://example.com/quintanar"
COMPLETIONS = "/v1/chat/completions"
SEARCH = "/res/v1/web/search"
SEARCH_KEY = "made-up-brave-key"
#: Brave's answer: a page whose title and text are both the secret.
FOUND = {
    "type": "search",
    "web": {"type": "search", "results": [{"title": SECRET_RESULT, "url": SECRET_ADDRESS, "description": SECRET_RESULT}]},
}

pytestmark = pytest.mark.django_db


def everything_kept() -> str:
    out = io.StringIO()
    call_command("dumpdata", stdout=out)
    return out.getvalue()


@pytest.fixture
def every_log(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


def cached() -> bytes:
    """All the (local memory) cache holds, keys and values; ``_cache`` is its pickled store."""
    return b"".join(key.encode() + value for key, value in cache._cache.items())


def assert_forgotten(every_log, *phrases):
    kept = everything_kept()
    logged = "\n".join(record.getMessage() for record in every_log.records)
    held = cached()
    for phrase in phrases:
        assert phrase not in kept
        assert phrase not in logged
        assert phrase.encode() not in held


@pytest.fixture
def a_search(settings, fake_provider):
    """A turn whose model searches, gets the secret page and answers naming no source."""
    settings.BRAVE_SEARCH_API_KEY = SEARCH_KEY
    settings.ASSISTANT_SEARCH_URL = f"{fake_provider.url}{SEARCH}"
    fake_provider.reply("GET", SEARCH, json=FOUND)
    fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", json.dumps({"query": SECRET_QUESTION})))
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer(SECRET_ANSWER))
    return fake_provider


def test_a_live_turn_leaves_nothing_of_what_was_said(internal, business, answering, fake_provider, every_log):
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer(SECRET_ANSWER))

    got = frames(
        door(
            Client(),
            "/internal/assistant/chat/stream",
            {"hub": business.slug, "messages": [{"role": "user", "content": SECRET_QUESTION}], "instructions": INSTRUCTIONS},
        )
    )

    assert got[0]["text"] == SECRET_ANSWER
    assert_forgotten(every_log, SECRET_QUESTION, SECRET_ANSWER, INSTRUCTIONS, "Rosalía")


def test_a_search_leaves_nothing_of_what_was_searched(internal, business, answering, a_search, every_log):
    frames(
        door(
            Client(),
            "/internal/assistant/chat/stream",
            {"hub": business.slug, "messages": [{"role": "user", "content": SECRET_QUESTION}], "instructions": INSTRUCTIONS},
        )
    )

    [seen] = [seen for seen in a_search.requests if seen.path.startswith(SEARCH)]
    assert parse_qs(urlsplit(seen.path).query)["q"] == [SECRET_QUESTION]
    assert_forgotten(every_log, SECRET_QUESTION, SECRET_ANSWER, SECRET_RESULT, SECRET_ADDRESS, "Rosalía", SEARCH_KEY)


def test_what_a_search_returned_goes_to_the_model_and_no_further_in_a_live_turn(internal, business, answering, a_search):
    """Brave's terms allow no keeping of its results (§3(b)(i)): the caller keeps the conversation, so what it gets is all
    that can be kept. Its answer and where it comes from, never the page."""
    got = frames(door(Client(), "/internal/assistant/chat/stream", {"hub": business.slug, "messages": [{"role": "user", "content": SECRET_QUESTION}]}))

    second = [seen for seen in a_search.requests if seen.path == COMPLETIONS][1]
    assert SECRET_RESULT in second.body["messages"][-1]["content"]
    said = json.dumps(got, ensure_ascii=False)
    assert SECRET_RESULT not in said
    assert [frame["text"] for frame in got if isinstance(frame, dict) and frame.get("type") == "text_delta"] == [SECRET_ANSWER, f"\n\n{SECRET_ADDRESS}"]


def test_a_turn_at_once_sends_nothing_to_the_search_so_nothing_of_it_can_be_kept(internal, business, answering, a_search, every_log):
    """The Hub keeps what this door answers (ASSISTANT-F13), so this door never searches, even if the model asks: the
    question does not leave for Brave and no page or address of its comes back."""
    response = door(Client(), "/internal/assistant/chat", {"hub": business.slug, "messages": [{"role": "user", "content": SECRET_QUESTION}]})

    assert response.status_code == 200
    assert [seen for seen in a_search.requests if seen.path.startswith(SEARCH)] == []
    said = json.dumps(response.json(), ensure_ascii=False)
    assert SECRET_ANSWER in said
    assert SECRET_RESULT not in said
    assert SECRET_ADDRESS not in said
    assert_forgotten(every_log, SECRET_QUESTION, SECRET_ANSWER, SECRET_RESULT, SECRET_ADDRESS, "Rosalía", SEARCH_KEY)


def test_what_a_search_returned_goes_to_the_model_and_no_further_in_the_panel(client, owner, plans, answering, a_search, every_log):
    """The panel keeps its conversation in the browser's tab, from these frames (``done``'s ``append`` too)."""
    client.force_login(owner)

    response = client.post(
        "/api/assistant/turn",
        {"messages": [{"role": "user", "content": SECRET_QUESTION}]},
        content_type="application/json",
        HTTP_HOST="localhost:8001",
    )
    got = frames(response)

    said = json.dumps(got, ensure_ascii=False)
    assert SECRET_ANSWER in said
    assert SECRET_ADDRESS in said
    assert SECRET_RESULT not in said
    assert_forgotten(every_log, SECRET_QUESTION, SECRET_ANSWER, SECRET_RESULT, SECRET_ADDRESS, "Rosalía", SEARCH_KEY)


def test_a_turn_at_once_with_a_tool_leaves_nothing_either(internal, business, answering, fake_provider, every_log):
    fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("customer_customer_list", '{"search":"Rosalía Quintanar"}'))

    response = door(
        Client(),
        "/internal/assistant/chat",
        {"hub": business.slug, "messages": [{"role": "user", "content": SECRET_QUESTION}], "tools": [{"name": "customer_customer_list"}]},
    )

    assert response.status_code == 200
    assert_forgotten(every_log, SECRET_QUESTION, "Rosalía")


def test_the_providers_words_of_a_failure_reach_no_log(internal, business, answering, fake_provider, every_log):
    fake_provider.reply("POST", COMPLETIONS, status=400, json={"error": {"message": f"Invalid content: {SECRET_QUESTION}"}})

    got = frames(
        door(Client(), "/internal/assistant/chat/stream", {"hub": business.slug, "messages": [{"role": "user", "content": SECRET_QUESTION}]})
    )

    assert got[0]["code"] == "assistant.provider_rejected"
    assert SECRET_QUESTION not in str(got)
    assert_forgotten(every_log, SECRET_QUESTION, "Rosalía")


def test_a_turn_of_the_panels_assistant_leaves_nothing_of_what_was_said(
    client, owner, plans, answering, fake_provider, every_log
):
    """The panel's own assistant (``POST /api/assistant/turn``, PLAN-SAAS §23): the account's conversation is forgotten
    as the Hub's is, its tool's results too."""
    from hubs.tests.conftest import create_business

    create_business(owner, name="Bar Olga")
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer(SECRET_ANSWER))
    client.force_login(owner)
    call = {"call_id": "c1", "name": "hubs__business__list", "arguments": "{}"}
    asked = [
        {"role": "user", "content": SECRET_QUESTION},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": call["name"], "arguments": "{}"}}]},
    ]

    response = client.post(
        "/api/assistant/turn",
        {"messages": asked, "pending": [call]},
        content_type="application/json",
        HTTP_HOST="localhost:8001",
    )
    got = frames(response)

    assert any(frame.get("text") == SECRET_ANSWER for frame in got if isinstance(frame, dict))
    assert_forgotten(every_log, SECRET_QUESTION, SECRET_ANSWER, "Rosalía")
