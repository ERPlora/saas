"""The client of Anthropic's Messages API (``assistant.providers.anthropic``, ASSISTANT-G32), against
``fake_provider`` speaking Anthropic's streamed events."""

import pytest

from assistant.providers.anthropic import AnthropicProvider
from assistant.providers.base import ProviderError, ToolSpec, TurnRequest

pytestmark = pytest.mark.asyncio

KEY = "sk-ant-test-0000"


def client(fake) -> AnthropicProvider:
    return AnthropicProvider(api_key=KEY, base_url=fake.url)


def stream(*events) -> list[tuple[str, dict]]:
    return [(event["type"], event) for event in events]


async def collect(provider, req) -> list:
    return [event async for event in provider.stream_turn(req)]


async def test_a_turn_streams_its_text_its_usage_and_its_end(fake_provider):
    fake_provider.reply(
        "POST",
        "/v1/messages",
        sse=stream(
            {"type": "message_start", "message": {"usage": {"input_tokens": 25, "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "ping"},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hola"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": ", Ana"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 9}},
            {"type": "message_stop"},
        ),
    )

    events = await collect(
        client(fake_provider),
        TurnRequest(
            model_id="claude-sonnet-4-6",
            messages=[{"role": "system", "content": "Speak Spanish."}, {"role": "user", "content": "Hi"}],
            system="Be brief.",
            temperature=0.3,
        ),
    )

    assert [(e.type, e.payload) for e in events] == [
        ("text_delta", {"text": "Hola"}),
        ("text_delta", {"text": ", Ana"}),
        ("usage", {"input_tokens": 25, "output_tokens": 9}),
        ("finish", {"reason": "stop"}),
    ]
    [sent] = fake_provider.requests
    assert sent.headers["x-api-key"] == KEY
    assert sent.headers["anthropic-version"] == "2023-06-01"
    assert sent.body["model"] == "claude-sonnet-4-6"
    assert sent.body["system"] == "Speak Spanish.\n\nBe brief."
    assert sent.body["messages"] == [{"role": "user", "content": "Hi"}]
    assert (sent.body["max_tokens"], sent.body["stream"], sent.body["temperature"]) == (4096, True, 0.3)


async def test_tools_go_as_input_schema_one_per_answer_and_a_tool_call_comes_out_whole(fake_provider):
    fake_provider.reply(
        "POST",
        "/v1/messages",
        sse=stream(
            {"type": "message_start", "message": {"usage": {"input_tokens": 40, "output_tokens": 0}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "find_customer", "input": {}}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"name": '}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '"Ana"}'}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 12}},
            {"type": "message_stop"},
        ),
    )
    tool = ToolSpec(name="find_customer", description="Find a customer", parameters={"type": "object", "properties": {"name": {"type": "string"}}})

    events = await collect(client(fake_provider), TurnRequest(model_id="claude-sonnet-4-6", messages=[{"role": "user", "content": "Ana?"}], tools=[tool]))

    assert [(e.type, e.payload) for e in events] == [
        ("tool_call", {"call_id": "toolu_1", "name": "find_customer", "arguments": '{"name": "Ana"}'}),
        ("usage", {"input_tokens": 40, "output_tokens": 12}),
        ("finish", {"reason": "tool_use"}),
    ]
    sent = fake_provider.requests[0].body
    assert sent["tools"] == [{"name": "find_customer", "description": "Find a customer", "input_schema": tool.parameters}]
    assert sent["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}


async def test_the_conversation_is_translated_to_anthropic_blocks(fake_provider):
    fake_provider.reply("POST", "/v1/messages", sse=stream({"type": "message_stop"}))
    conversation = [
        {"role": "user", "content": [{"type": "text", "text": "Look"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBOR"}}]},
        {"role": "assistant", "content": "Let me check.", "tool_calls": [{"id": "toolu_1", "type": "function", "function": {"name": "find_customer", "arguments": '{"name": "Ana"}'}}]},
        {"role": "tool", "tool_call_id": "toolu_1", "content": '{"found": true}'},
        {"role": "user", "content": "And now?"},
    ]

    await collect(client(fake_provider), TurnRequest(model_id="claude-sonnet-4-6", messages=conversation))

    assert fake_provider.requests[0].body["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Look"}, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBOR"}}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Let me check."}, {"type": "tool_use", "id": "toolu_1", "name": "find_customer", "input": {"name": "Ana"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"found": true}'}, {"type": "text", "text": "And now?"}]},
    ]


@pytest.mark.parametrize(("raw", "reason"), [("max_tokens", "length"), ("stop_sequence", "stop"), ("refusal", "content_filter"), ("end_turn", "stop")])
async def test_the_end_of_the_answer_is_named_alike(fake_provider, raw, reason):
    fake_provider.reply("POST", "/v1/messages", sse=stream({"type": "message_delta", "delta": {"stop_reason": raw}, "usage": {"output_tokens": 1}}, {"type": "message_stop"}))

    events = await collect(client(fake_provider), TurnRequest(model_id="m", messages=[]))

    assert events[-1].payload == {"reason": reason}


async def test_an_overloaded_event_in_the_stream_is_a_retriable_error(fake_provider):
    fake_provider.reply(
        "POST",
        "/v1/messages",
        sse=stream({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}),
    )

    events = await collect(client(fake_provider), TurnRequest(model_id="m", messages=[]))

    assert [(e.type, e.payload) for e in events] == [
        ("error", {"message": "anthropic: Overloaded", "retriable": True, "status": None}),
        ("finish", {"reason": "error"}),
    ]


async def test_a_refused_key_is_not_retriable(fake_provider):
    fake_provider.reply("POST", "/v1/messages", status=401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})

    events = await collect(client(fake_provider), TurnRequest(model_id="m", messages=[]))

    assert events[0].payload == {"message": "anthropic: invalid x-api-key", "retriable": False, "status": 401}


async def test_its_models_are_listed_page_by_page(fake_provider):
    fake_provider.reply(
        "GET",
        "/v1/models",
        json={"data": [{"type": "model", "id": "claude-opus-4-7", "display_name": "Claude Opus 4.7"}], "has_more": True, "last_id": "claude-opus-4-7"},
    )
    fake_provider.reply(
        "GET",
        "/v1/models",
        json={"data": [{"type": "model", "id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5"}], "has_more": False, "last_id": "claude-haiku-4-5"},
    )

    models = await client(fake_provider).list_models()

    assert [(m.model_id, m.display_name) for m in models] == [("claude-haiku-4-5", "Claude Haiku 4.5"), ("claude-opus-4-7", "Claude Opus 4.7")]
    first, second = fake_provider.requests
    assert first.path == "/v1/models?limit=1000"
    assert second.path == "/v1/models?limit=1000&after_id=claude-opus-4-7"
    assert first.headers["x-api-key"] == KEY


async def test_listing_with_a_refused_key_says_why(fake_provider):
    fake_provider.reply("GET", "/v1/models", status=401, json={"type": "error", "error": {"message": "invalid x-api-key"}})

    with pytest.raises(ProviderError) as refused:
        await client(fake_provider).list_models()

    assert refused.value.message == "anthropic: invalid x-api-key"
