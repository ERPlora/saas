"""FLOW-F39 (the Hub's ``apps/flow/WORKBOOK.md``; old SAAS_ASSISTANT-F04) · ASSISTANT-F13: an automation's «Ask the
assistant» step, asked by the Hub's worker with nobody in front, is a turn of the door that answers at once
(``POST /internal/assistant/chat``): no door of its own, no field that tells it from a chat. So it spends the same
monthly messages as the chat — its first turn one, the turns that answer its tools with their ``continuation`` none —,
says whether a failure is worth trying again (``retriable``), is refused to a business that does not work, and keeps
nothing of what was said (``test_privacy.py``: ``test_a_turn_at_once_with_a_tool_leaves_nothing_either``). Its
signature is every door's (``test_internal_caller.py``, ``DOORS``)."""

import pytest
from django.test import Client
from django.utils import timezone

from assistant import queries
from assistant.models import AssistantUsage
from assistant.tests.conftest import openai_answer, openai_tool_call
from assistant.tests.doors import door, error_code
from hubs.models import Hub

JSON = "/internal/assistant/chat"
COMPLETIONS = "/v1/chat/completions"
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
