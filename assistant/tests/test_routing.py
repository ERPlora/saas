"""The turn through its route (``assistant.routing.stream``, ASSISTANT-G45; the old product kept a fallback model it
never used, SAAS_ASSISTANT-F05): the model that answers is called first; if its provider fails before answering
anything, the fallback model answers; once text has come, a failure ends the turn (the person already saw it).

Both providers are ``FakeProvider`` servers on ``127.0.0.1``: the clients run their real HTTP."""

from decimal import Decimal

import pytest

from assistant.providers.base import TurnRequest
from assistant.routing import stream
from assistant.schemas import RouteCandidate
from assistant.tests.fake_provider import FakeProvider, openai_chunk

pytestmark = pytest.mark.asyncio


@pytest.fixture
def second_provider():
    server = FakeProvider()
    server.start()
    yield server
    server.stop()


def candidate(server, model_id: str, display_name: str) -> RouteCandidate:
    return RouteCandidate(
        model="0190b3a0-0000-7000-8000-00000000000" + str(len(model_id) % 10),
        model_id=model_id,
        display_name=display_name,
        provider="Local",
        kind="openai",
        base_url=f"{server.url}/v1",
        api_key="sk-test-route-0000",
        price_input_per_1m=Decimal("1"),
        price_output_per_1m=Decimal("2"),
        supports_tools=True,
        supports_vision=False,
    )


def answer(text: str) -> list:
    return [openai_chunk(text, finish="stop"), openai_chunk(usage={"prompt_tokens": 3, "completion_tokens": 2}), "[DONE]"]


def request_for(route: RouteCandidate) -> TurnRequest:
    return TurnRequest(model_id=route.model_id, messages=[{"role": "user", "content": "Hi"}])


async def run(candidates) -> list[tuple[str, dict]]:
    return [(event.type, event.payload) async for event in stream(candidates, request_for)]


async def test_the_model_that_answers_is_used_when_it_works(fake_provider, second_provider):
    fake_provider.reply("POST", "/v1/chat/completions", sse=answer("Hola"))

    events = await run([candidate(fake_provider, "first", "First"), candidate(second_provider, "second-model", "Second")])

    assert events[0] == ("model", {"model": events[0][1]["model"], "model_id": "first", "display_name": "First", "provider": "Local"})
    assert events[1:] == [
        ("text_delta", {"text": "Hola"}),
        ("usage", {"input_tokens": 3, "output_tokens": 2}),
        ("finish", {"reason": "stop"}),
    ]
    assert second_provider.requests == []


@pytest.mark.parametrize("status", [503, 429, 401])
async def test_a_provider_that_fails_before_answering_passes_the_turn_to_the_fallback(fake_provider, second_provider, status):
    fake_provider.reply("POST", "/v1/chat/completions", status=status, json={"error": {"message": "nope"}})
    second_provider.reply("POST", "/v1/chat/completions", sse=answer("Hola"))

    events = await run([candidate(fake_provider, "first", "First"), candidate(second_provider, "second-model", "Second")])

    kinds = [kind for kind, _ in events]
    assert kinds == ["model", "fallback", "model", "text_delta", "usage", "finish"]
    assert events[1][1] == {"from": "First", "to": "Second", "reason": "openai: nope", "status": status}
    assert events[2][1]["model_id"] == "second-model"
    assert events[-1] == ("finish", {"reason": "stop"})


async def test_a_failure_after_the_first_text_ends_the_turn_without_fallback(fake_provider, second_provider):
    fake_provider.reply("POST", "/v1/chat/completions", sse=[openai_chunk("Hol"), {"error": {"message": "overloaded"}}])
    second_provider.reply("POST", "/v1/chat/completions", sse=answer("Hola"))

    events = await run([candidate(fake_provider, "first", "First"), candidate(second_provider, "second-model", "Second")])

    assert [kind for kind, _ in events] == ["model", "text_delta", "error", "finish"]
    assert events[-1] == ("finish", {"reason": "error"})
    assert second_provider.requests == []


async def test_when_every_provider_fails_the_last_failure_ends_the_turn(fake_provider, second_provider):
    fake_provider.reply("POST", "/v1/chat/completions", status=503, json={"error": {"message": "first down"}})
    second_provider.reply("POST", "/v1/chat/completions", status=500, json={"error": {"message": "second down"}})

    events = await run([candidate(fake_provider, "first", "First"), candidate(second_provider, "second-model", "Second")])

    assert [kind for kind, _ in events] == ["model", "fallback", "model", "error", "finish"]
    assert events[3][1]["message"] == "openai: second down"


async def test_without_any_route_the_turn_ends_as_an_error():
    events = await run([])

    assert events == [("error", {"message": "No model can answer.", "retriable": False, "status": None}), ("finish", {"reason": "error"})]
