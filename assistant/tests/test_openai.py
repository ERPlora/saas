"""The client of OpenAI's Chat Completions (``assistant.providers.openai``, ASSISTANT-G37), against
``fake_provider``: the real HTTP of our client, to a server on ``127.0.0.1`` that answers in OpenAI's format."""

import json

import pytest

from assistant.providers.base import ProviderError, ToolSpec, TurnRequest
from assistant.providers.openai import OpenAIProvider
from assistant.tests.fake_provider import openai_chunk

pytestmark = pytest.mark.asyncio

KEY = "sk-test-openai-0000"


def client(fake) -> OpenAIProvider:
    return OpenAIProvider(api_key=KEY, base_url=f"{fake.url}/v1")


async def collect(provider, req) -> list:
    return [event async for event in provider.stream_turn(req)]


async def test_a_turn_streams_its_text_its_usage_and_its_end(fake_provider):
    fake_provider.reply(
        "POST",
        "/v1/chat/completions",
        sse=[
            openai_chunk("Hel"),
            openai_chunk("lo", finish="stop"),
            openai_chunk(usage={"prompt_tokens": 12, "completion_tokens": 3}),
            "[DONE]",
        ],
    )

    events = await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[{"role": "user", "content": "Hi"}], system="Be brief."))

    assert [(e.type, e.payload) for e in events] == [
        ("text_delta", {"text": "Hel"}),
        ("text_delta", {"text": "lo"}),
        ("usage", {"input_tokens": 12, "output_tokens": 3}),
        ("finish", {"reason": "stop"}),
    ]
    [sent] = fake_provider.requests
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert sent.body["model"] == "gpt-4o"
    assert sent.body["messages"] == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]
    assert sent.body["stream"] is True and sent.body["stream_options"] == {"include_usage": True}
    assert sent.body["max_tokens"] == 4096 and "max_completion_tokens" not in sent.body


@pytest.mark.parametrize("model_id", ["gpt-5.5", "o3-mini", "o4-mini", "o1"])
async def test_newer_models_get_max_completion_tokens_and_no_temperature(fake_provider, model_id):
    fake_provider.reply("POST", "/v1/chat/completions", sse=[openai_chunk("ok", finish="stop"), "[DONE]"])

    await collect(client(fake_provider), TurnRequest(model_id=model_id, messages=[{"role": "user", "content": "Hi"}], temperature=0.2, max_tokens=100))

    [sent] = fake_provider.requests
    assert sent.body["max_completion_tokens"] == 100 and "max_tokens" not in sent.body
    assert "temperature" not in sent.body


async def test_an_older_model_keeps_its_temperature(fake_provider):
    fake_provider.reply("POST", "/v1/chat/completions", sse=[openai_chunk("ok", finish="stop"), "[DONE]"])

    await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[], temperature=0.2))

    assert fake_provider.requests[0].body["temperature"] == 0.2


async def test_a_tool_call_streamed_in_fragments_comes_out_whole(fake_provider):
    fake_provider.reply(
        "POST",
        "/v1/chat/completions",
        sse=[
            openai_chunk(tool_calls=[{"index": 0, "id": "call_1", "function": {"name": "find_customer", "arguments": '{"na'}}]),
            openai_chunk(tool_calls=[{"index": 0, "function": {"arguments": 'me": "Ana"}'}}], finish="tool_calls"),
            "[DONE]",
        ],
    )
    tool = ToolSpec(name="find_customer", description="Find a customer", parameters={"type": "object", "properties": {}})

    events = await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[{"role": "user", "content": "Ana?"}], tools=[tool]))

    assert [(e.type, e.payload) for e in events] == [
        ("tool_call", {"call_id": "call_1", "name": "find_customer", "arguments": '{"name": "Ana"}'}),
        ("finish", {"reason": "tool_use"}),
    ]
    sent = fake_provider.requests[0].body
    assert sent["tools"] == [
        {"type": "function", "function": {"name": "find_customer", "description": "Find a customer", "parameters": {"type": "object", "properties": {}}}}
    ]
    assert sent["parallel_tool_calls"] is False


@pytest.mark.parametrize(("raw", "reason"), [("length", "length"), ("content_filter", "content_filter"), ("other", "stop")])
async def test_the_end_of_the_answer_is_named_alike_for_every_provider(fake_provider, raw, reason):
    fake_provider.reply("POST", "/v1/chat/completions", sse=[openai_chunk("x", finish=raw), "[DONE]"])

    events = await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[]))

    assert events[-1].payload == {"reason": reason}


async def test_a_refused_key_is_an_error_that_another_attempt_cannot_clear(fake_provider):
    fake_provider.reply("POST", "/v1/chat/completions", status=401, json={"error": {"message": f"Incorrect API key provided: {KEY}."}})

    events = await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[]))

    assert [e.type for e in events] == ["error", "finish"]
    assert events[0].payload == {"message": "openai: Incorrect API key provided: ….", "retriable": False, "status": 401}
    assert events[1].payload == {"reason": "error"}


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_a_rate_limit_or_a_server_error_is_retriable(fake_provider, status):
    fake_provider.reply("POST", "/v1/chat/completions", status=status, json={"error": {"message": "busy"}})

    events = await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[]))

    assert events[0].payload == {"message": "openai: busy", "retriable": True, "status": status}


async def test_an_error_in_the_middle_of_the_stream_ends_the_turn(fake_provider):
    fake_provider.reply("POST", "/v1/chat/completions", sse=[openai_chunk("Hi"), {"error": {"message": "overloaded"}}])

    events = await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[]))

    assert [(e.type, e.payload) for e in events] == [
        ("text_delta", {"text": "Hi"}),
        ("error", {"message": "openai: overloaded", "retriable": True, "status": None}),
        ("finish", {"reason": "error"}),
    ]


async def test_a_provider_that_cannot_be_reached_is_a_retriable_error():
    provider = OpenAIProvider(api_key=KEY, base_url="http://127.0.0.1:9/v1")

    events = await collect(provider, TurnRequest(model_id="gpt-4o", messages=[]))

    assert events[0].type == "error" and events[0].payload["retriable"] is True
    assert "could not be reached" in events[0].payload["message"]
    assert events[-1].payload == {"reason": "error"}


async def test_its_chat_models_are_listed_without_the_others(fake_provider):
    fake_provider.reply(
        "GET",
        "/v1/models",
        json={
            "data": [
                {"id": "gpt-5.5"},
                {"id": "text-embedding-3-small"},
                {"id": "whisper-1"},
                {"id": "tts-1"},
                {"id": "dall-e-3"},
                {"id": "omni-moderation-latest"},
                {"id": "gpt-4o-realtime-preview"},
                {"id": "gpt-4o-transcribe"},
                {"id": "gpt-4o"},
            ]
        },
    )

    models = await client(fake_provider).list_models()

    assert [(m.model_id, m.display_name) for m in models] == [("gpt-4o", "gpt-4o"), ("gpt-5.5", "gpt-5.5")]
    assert fake_provider.requests[0].headers["authorization"] == f"Bearer {KEY}"


async def test_listing_with_a_refused_key_says_why(fake_provider):
    fake_provider.reply("GET", "/v1/models", status=401, json={"error": {"message": "Invalid key"}})

    with pytest.raises(ProviderError) as refused:
        await client(fake_provider).list_models()

    assert (refused.value.message, refused.value.status, refused.value.retriable) == ("openai: Invalid key", 401, False)


async def test_the_request_body_is_json(fake_provider):
    fake_provider.reply("POST", "/v1/chat/completions", sse=["[DONE]"])

    events = await collect(client(fake_provider), TurnRequest(model_id="gpt-4o", messages=[{"role": "user", "content": "ñ"}]))

    assert json.dumps(fake_provider.requests[0].body["messages"], ensure_ascii=False) == '[{"role": "user", "content": "ñ"}]'
    assert events[-1].payload == {"reason": "stop"}
