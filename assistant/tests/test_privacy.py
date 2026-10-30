"""ASSISTANT-F17 (ASSISTANT-G49) · Do not keep the conversation: erplora.com uses it for the call and forgets it.

No table, log, audit entry nor event of the outbox keeps what a person wrote or what the model answered: only
numbers (messages, tokens, cost). The old product kept the first 50 characters of a dictation in its log and the
provider's error words could carry them (SAAS_ASSISTANT-F09, «parcial»): here the provider's words of a failure never
reach a log either. Checked by dumping the whole database and reading every log record of every logger.
"""

import io
import logging

import pytest
from django.core.management import call_command
from django.test import Client

from assistant.tests.conftest import openai_answer, openai_tool_call
from assistant.tests.doors import door, frames

SECRET_QUESTION = "Mi cliente Rosalía Quintanar debe 400 euros"
SECRET_ANSWER = "Apunta la deuda de Rosalía Quintanar"
INSTRUCTIONS = "Negocio Bar Manolo, cajera Iratxe Bengoetxea"
COMPLETIONS = "/v1/chat/completions"

pytestmark = pytest.mark.django_db


def everything_kept() -> str:
    out = io.StringIO()
    call_command("dumpdata", stdout=out)
    return out.getvalue()


@pytest.fixture
def every_log(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


def assert_forgotten(every_log, *phrases):
    kept = everything_kept()
    logged = "\n".join(record.getMessage() for record in every_log.records)
    for phrase in phrases:
        assert phrase not in kept
        assert phrase not in logged


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
