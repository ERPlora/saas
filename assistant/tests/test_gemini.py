"""The client of Google's Gemini API (``assistant.providers.gemini``, ASSISTANT-G36), against ``fake_provider``
speaking ``streamGenerateContent`` over server-sent events."""

import pytest

from assistant.providers.base import ProviderError, ToolSpec, TurnRequest
from assistant.providers.gemini import GeminiProvider, sanitize_schema

pytestmark = pytest.mark.asyncio

KEY = "gemini-test-key-0000"
STREAM = "/v1beta/models/gemini-2.5-pro:streamGenerateContent"


def client(fake) -> GeminiProvider:
    return GeminiProvider(api_key=KEY, base_url=fake.url)


def chunk(*parts, finish=None, usage=None) -> dict:
    candidate: dict = {"content": {"role": "model", "parts": list(parts)}}
    if finish:
        candidate["finishReason"] = finish
    out: dict = {"candidates": [candidate]}
    if usage:
        out["usageMetadata"] = usage
    return out


async def collect(provider, req) -> list:
    return [event async for event in provider.stream_turn(req)]


async def test_a_turn_streams_its_text_its_usage_and_its_end(fake_provider):
    fake_provider.reply(
        "POST",
        STREAM,
        sse=[
            chunk({"text": "Hola"}),
            chunk({"text": ", Ana"}, finish="STOP", usage={"promptTokenCount": 20, "candidatesTokenCount": 4, "thoughtsTokenCount": 6}),
        ],
    )

    events = await collect(
        client(fake_provider),
        TurnRequest(model_id="gemini-2.5-pro", messages=[{"role": "system", "content": "Speak Spanish."}, {"role": "user", "content": "Hi"}], system="Be brief.", temperature=0.2),
    )

    assert [(e.type, e.payload) for e in events] == [
        ("text_delta", {"text": "Hola"}),
        ("text_delta", {"text": ", Ana"}),
        ("usage", {"input_tokens": 20, "output_tokens": 10}),
        ("finish", {"reason": "stop"}),
    ]
    [sent] = fake_provider.requests
    assert sent.path == f"{STREAM}?alt=sse"
    assert sent.headers["x-goog-api-key"] == KEY
    assert sent.body["contents"] == [{"role": "user", "parts": [{"text": "Hi"}]}]
    assert sent.body["systemInstruction"] == {"parts": [{"text": "Speak Spanish.\n\nBe brief."}]}
    assert sent.body["generationConfig"] == {"maxOutputTokens": 4096, "temperature": 0.2}


async def test_a_function_call_comes_out_as_a_tool_call(fake_provider):
    fake_provider.reply(
        "POST",
        STREAM,
        sse=[chunk({"functionCall": {"name": "find_customer", "args": {"name": "Ana"}}}, finish="STOP", usage={"promptTokenCount": 30, "candidatesTokenCount": 5})],
    )
    tool = ToolSpec(
        name="find_customer",
        description="Find a customer",
        parameters={
            "type": "object",
            "title": "Find",
            "additionalProperties": False,
            "properties": {"who": {"$ref": "#/$defs/Who"}},
            "$defs": {"Who": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}}}},
        },
    )

    events = await collect(client(fake_provider), TurnRequest(model_id="gemini-2.5-pro", messages=[{"role": "user", "content": "Ana?"}], tools=[tool]))

    assert [(e.type, e.payload) for e in events] == [
        ("tool_call", {"call_id": "gemini_call_0", "name": "find_customer", "arguments": '{"name": "Ana"}'}),
        ("usage", {"input_tokens": 30, "output_tokens": 5}),
        ("finish", {"reason": "tool_use"}),
    ]
    assert fake_provider.requests[0].body["tools"] == [
        {
            "functionDeclarations": [
                {
                    "name": "find_customer",
                    "description": "Find a customer",
                    "parameters": {"type": "object", "properties": {"who": {"type": "object", "properties": {"name": {"type": "string"}}}}},
                }
            ]
        }
    ]


async def test_the_conversation_is_translated_to_gemini_contents(fake_provider):
    fake_provider.reply("POST", STREAM, sse=[chunk({"text": "ok"}, finish="STOP")])
    conversation = [
        {"role": "user", "content": [{"type": "text", "text": "Look"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/"}}]},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_7", "type": "function", "function": {"name": "find_customer", "arguments": '{"name": "Ana"}'}}]},
        {"role": "tool", "tool_call_id": "call_7", "content": '{"found": true}'},
        {"role": "tool", "tool_call_id": "call_x", "name": "other_tool", "content": "plain text"},
    ]

    await collect(client(fake_provider), TurnRequest(model_id="gemini-2.5-pro", messages=conversation))

    assert fake_provider.requests[0].body["contents"] == [
        {"role": "user", "parts": [{"text": "Look"}, {"inlineData": {"mimeType": "image/jpeg", "data": "/9j/"}}]},
        {"role": "model", "parts": [{"functionCall": {"name": "find_customer", "args": {"name": "Ana"}}}]},
        {
            "role": "user",
            "parts": [
                {"functionResponse": {"name": "find_customer", "response": {"found": True}}},
                {"functionResponse": {"name": "other_tool", "response": {"result": "plain text"}}},
            ],
        },
    ]


@pytest.mark.parametrize(("raw", "reason"), [("MAX_TOKENS", "length"), ("SAFETY", "content_filter"), ("RECITATION", "content_filter"), ("STOP", "stop")])
async def test_the_end_of_the_answer_is_named_alike(fake_provider, raw, reason):
    fake_provider.reply("POST", STREAM, sse=[chunk({"text": "x"}, finish=raw)])

    events = await collect(client(fake_provider), TurnRequest(model_id="gemini-2.5-pro", messages=[]))

    assert events[-1].payload == {"reason": reason}


async def test_a_refused_key_is_not_retriable(fake_provider):
    fake_provider.reply("POST", STREAM, status=400, json={"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}})

    events = await collect(client(fake_provider), TurnRequest(model_id="gemini-2.5-pro", messages=[]))

    assert events[0].payload == {"message": "gemini: API key not valid.", "retriable": False, "status": 400}


async def test_an_error_in_the_stream_ends_the_turn(fake_provider):
    fake_provider.reply("POST", STREAM, sse=[{"error": {"code": 503, "message": "The model is overloaded."}}])

    events = await collect(client(fake_provider), TurnRequest(model_id="gemini-2.5-pro", messages=[]))

    assert [(e.type, e.payload) for e in events] == [
        ("error", {"message": "gemini: The model is overloaded.", "retriable": True, "status": 503}),
        ("finish", {"reason": "error"}),
    ]


async def test_its_chat_models_are_listed_page_by_page(fake_provider):
    fake_provider.reply(
        "GET",
        "/v1beta/models",
        json={
            "models": [
                {"name": "models/gemini-2.5-pro", "displayName": "Gemini 2.5 Pro", "inputTokenLimit": 1048576, "supportedGenerationMethods": ["generateContent", "countTokens"]},
                {"name": "models/text-embedding-004", "displayName": "Embedding", "supportedGenerationMethods": ["embedContent"]},
            ],
            "nextPageToken": "page-2",
        },
    )
    fake_provider.reply(
        "GET",
        "/v1beta/models",
        json={"models": [{"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash", "inputTokenLimit": 1048576, "supportedGenerationMethods": ["generateContent"]}]},
    )

    models = await client(fake_provider).list_models()

    assert [(m.model_id, m.display_name, m.context_window) for m in models] == [
        ("gemini-2.5-flash", "Gemini 2.5 Flash", 1048576),
        ("gemini-2.5-pro", "Gemini 2.5 Pro", 1048576),
    ]
    first, second = fake_provider.requests
    assert first.path == "/v1beta/models?pageSize=1000"
    assert second.path == "/v1beta/models?pageSize=1000&pageToken=page-2"
    assert first.headers["x-goog-api-key"] == KEY


async def test_listing_with_a_refused_key_says_why(fake_provider):
    fake_provider.reply("GET", "/v1beta/models", status=400, json={"error": {"message": "API key not valid."}})

    with pytest.raises(ProviderError) as refused:
        await client(fake_provider).list_models()

    assert refused.value.message == "gemini: API key not valid."


async def test_a_schema_keeps_only_what_gemini_reads():
    assert sanitize_schema({"$schema": "x", "type": "object", "properties": {"a": {"$ref": "#/definitions/A"}}, "definitions": {"A": {"type": "string", "title": "A"}}}) == {
        "type": "object",
        "properties": {"a": {"type": "string"}},
    }
    assert sanitize_schema({"items": [{"$ref": "#/$defs/Missing"}]}) == {"items": [{"$ref": "#/$defs/Missing"}]}
