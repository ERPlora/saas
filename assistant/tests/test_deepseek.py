"""The client of DeepSeek (``assistant.providers.deepseek``, ASSISTANT-G34): OpenAI's format at DeepSeek's address,
against ``fake_provider``. DeepSeek does not take ``parallel_tool_calls`` and every model it lists is a chat model."""

import pytest

from assistant.providers.base import ToolSpec, TurnRequest
from assistant.providers.deepseek import DeepSeekProvider
from assistant.tests.fake_provider import openai_chunk

pytestmark = pytest.mark.asyncio

KEY = "sk-test-deepseek-0000"


def client(fake) -> DeepSeekProvider:
    return DeepSeekProvider(api_key=KEY, base_url=fake.url)


async def test_a_turn_goes_in_openai_format_without_parallel_tool_calls(fake_provider):
    fake_provider.reply(
        "POST",
        "/chat/completions",
        sse=[openai_chunk("Hola", finish="stop"), openai_chunk(usage={"prompt_tokens": 5, "completion_tokens": 1}), "[DONE]"],
    )
    tool = ToolSpec(name="t", description="d", parameters={"type": "object", "properties": {}})

    events = [e async for e in client(fake_provider).stream_turn(TurnRequest(model_id="deepseek-chat", messages=[{"role": "user", "content": "Hi"}], tools=[tool]))]

    assert [(e.type, e.payload) for e in events] == [
        ("text_delta", {"text": "Hola"}),
        ("usage", {"input_tokens": 5, "output_tokens": 1}),
        ("finish", {"reason": "stop"}),
    ]
    sent = fake_provider.requests[0]
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert "parallel_tool_calls" not in sent.body
    assert sent.body["tools"][0]["function"]["name"] == "t"
    assert sent.body["max_tokens"] == 4096


async def test_every_model_it_lists_is_a_chat_model(fake_provider):
    fake_provider.reply("GET", "/models", json={"data": [{"id": "deepseek-reasoner"}, {"id": "deepseek-chat"}]})

    models = await client(fake_provider).list_models()

    assert [m.model_id for m in models] == ["deepseek-chat", "deepseek-reasoner"]


async def test_a_refused_key_says_deepseek(fake_provider):
    fake_provider.reply("POST", "/chat/completions", status=401, json={"error": {"message": "Authentication Fails"}})

    events = [e async for e in client(fake_provider).stream_turn(TurnRequest(model_id="deepseek-chat", messages=[]))]

    assert events[0].payload == {"message": "deepseek: Authentication Fails", "retriable": False, "status": 401}
