"""ASSISTANT-F03 and ASSISTANT-F24 · The provider's cache of what a request repeats: each call of a request sends the
model what the previous one sent, unchanged and in the same order (the tools, then the instructions, then the
conversation), so the provider reads it from its cache instead of processing it again; and the month's row of the
business counts every input token, of which those read from the cache and those written to it, with their own prices.

Anthropic (the provider of the model that answers) caches what a request marks: the end of the tools, the end of the
instructions and the conversation up to its last message. Its usage counts apart what it read from the cache, what it
wrote to it and the rest. The provider is the local fake (``fake_provider``), never a real one.
"""

import json
import logging
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from assistant import queries
from assistant.models import AIModel, AIProvider, AIRoutingPolicy, AssistantUsage
from assistant.tests.doors import door, frames
from assistant.tests.test_call_log import fields, lines_of_calls

MESSAGES = "/v1/messages"
STREAM = "/internal/assistant/chat/stream"
HAIKU = "claude-haiku-5-5"
EPHEMERAL = {"type": "ephemeral"}
TOOLS = [
    {"type": "function", "name": "inventory_product_list", "description": "List the products.", "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}},
    {"type": "function", "name": "sale_order_list", "description": "List the open orders.", "parameters": {"type": "object", "properties": {}}},
]

pytestmark = pytest.mark.django_db


@pytest.fixture
def haiku(fake_provider, settings):
    """Claude Haiku 5.5 answers, at Anthropic on the fake provider with its key and its prices of the cache."""
    settings.ANTHROPIC_API_KEY = "sk-ant-test-0000"
    anthropic = AIProvider.objects.create(
        slug="anthropic", name="Anthropic", kind=AIProvider.Kind.ANTHROPIC, key_variable="ANTHROPIC_API_KEY", base_url=fake_provider.url
    )
    model = AIModel.objects.create(
        provider=anthropic,
        model_id=HAIKU,
        display_name="Claude Haiku 5.5",
        price_input_per_1m=Decimal("0.10"),
        price_output_per_1m=Decimal("0.50"),
        price_cache_read_per_1m=Decimal("0.01"),
        price_cache_write_per_1m=Decimal("0.125"),
    )
    policy = AIRoutingPolicy.solo()
    policy.active_model = model
    policy.save()
    return model


def usage(fresh: int = 0, read: int = 0, written: int = 0) -> dict:
    return {"input_tokens": fresh, "cache_read_input_tokens": read, "cache_creation_input_tokens": written, "output_tokens": 1}


def answer(text: str, *, tokens: dict | None = None, output: int = 5) -> list:
    """Anthropic's streamed events of a text answer."""
    return [
        ("message_start", {"type": "message_start", "message": {"usage": tokens or usage(fresh=100)}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": output}}),
        ("message_stop", {"type": "message_stop"}),
    ]


def tool_call(name: str, call_id: str, *, tokens: dict | None = None, output: int = 5) -> list:
    """Anthropic's streamed events of an answer that asks for the tool ``name``."""
    return [
        ("message_start", {"type": "message_start", "message": {"usage": tokens or usage(fresh=100)}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": call_id, "name": name, "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": "{}"}}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": output}}),
        ("message_stop", {"type": "message_stop"}),
    ]


def sent(fake_provider) -> list[dict]:
    return [seen.body for seen in fake_provider.requests if seen.path == MESSAGES]


def turn(business, *messages, **extra) -> dict:
    return {"hub": business.slug, "messages": list(messages), "instructions": "Answer in Spanish.", "tools": TOOLS, **extra}


def ask(question: str) -> dict:
    return {"role": "user", "content": question}


def response_of(got: list) -> dict:
    return next(frame for frame in got if isinstance(frame, dict) and frame["type"] == "response")


def starts_alike(first: dict, second: dict) -> None:
    """``second`` sends what ``first`` sent before its conversation byte for byte, and ``first``'s conversation as the
    start of its own."""
    assert json.dumps(second["tools"]) == json.dumps(first["tools"])
    assert json.dumps(second["system"]) == json.dumps(first["system"])
    assert json.dumps(second["messages"][: len(first["messages"])]) == json.dumps(first["messages"])
    assert len(second["messages"]) > len(first["messages"])


class TestWhatACallMarks:
    def test_the_end_of_the_tools_the_instructions_and_the_conversation_are_cached(self, internal, business, haiku, fake_provider):
        fake_provider.reply("POST", MESSAGES, sse=answer("Tienes 12 productos."))

        frames(door(Client(), STREAM, turn(business, ask("¿Cuántos productos tengo?"))))

        [body] = sent(fake_provider)
        names = [tool["name"] for tool in body["tools"]]
        assert names[:2] == ["inventory_product_list", "sale_order_list"]
        assert [tool.get("cache_control") for tool in body["tools"]] == [None] * (len(names) - 1) + [EPHEMERAL]
        [instructions] = body["system"]
        assert instructions["text"].startswith("Answer in Spanish.")
        assert instructions["cache_control"] == EPHEMERAL
        assert body["cache_control"] == EPHEMERAL
        assert "cache_control" not in json.dumps(body["messages"])


class TestARequestOfSeveralCalls:
    def test_the_hubs_second_round_starts_with_what_the_first_sent(self, internal, business, haiku, fake_provider):
        question = ask("¿Cuántos pedidos abiertos hay?")
        fake_provider.reply("POST", MESSAGES, sse=tool_call("sale_order_list", "toolu_1"))
        token = response_of(frames(door(Client(), STREAM, turn(business, question))))["continuation"]
        asked = {"role": "assistant", "content": "", "tool_calls": [{"id": "toolu_1", "type": "function", "function": {"name": "sale_order_list", "arguments": "{}"}}]}
        result = {"role": "tool", "tool_call_id": "toolu_1", "content": '{"orders": 2}'}
        fake_provider.reply("POST", MESSAGES, sse=answer("Hay 2 pedidos abiertos."))

        frames(door(Client(), STREAM, turn(business, question, asked, result, continuation=token)))

        first, second = sent(fake_provider)
        starts_alike(first, second)

    def test_a_round_of_erplora_coms_own_tools_starts_with_what_the_call_before_sent(self, internal, business, haiku, fake_provider):
        fake_provider.reply("POST", MESSAGES, sse=tool_call("current_datetime", "toolu_d"))
        fake_provider.reply("POST", MESSAGES, sse=answer("Es lunes."))

        frames(door(Client(), STREAM, turn(business, ask("¿Qué día es hoy?"))))

        first, second = sent(fake_provider)
        starts_alike(first, second)


class TestWhatTheMonthCounts:
    def test_the_row_keeps_every_input_token_those_of_the_cache_apart_and_their_cost(self, internal, business, haiku, fake_provider):
        fake_provider.reply("POST", MESSAGES, sse=tool_call("current_datetime", "toolu_d", tokens=usage(fresh=100, written=3000), output=20))
        fake_provider.reply("POST", MESSAGES, sse=answer("Es lunes.", tokens=usage(fresh=120, read=3000, written=200), output=10))

        got = frames(door(Client(), STREAM, turn(business, ask("¿Qué día es hoy?"))))

        row = AssistantUsage.objects.get(hub=business, month=queries.usage.month_of(timezone.now()), model=HAIKU)
        assert (row.messages, row.tokens_input, row.tokens_output) == (1, 6420, 30)
        assert (row.tokens_cache_read, row.tokens_cache_write) == (3000, 3200)
        # 220 fresh at 0.10, 3000 read at 0.01, 3200 written at 0.125 and 30 out at 0.50, per million.
        assert row.cost_usd == Decimal("0.000467")
        assert response_of(got)["usage"] == {"input_tokens": 6420, "output_tokens": 30}


class TestWhatEachCallLogs:
    def test_each_calls_line_says_what_the_cache_read_and_wrote(self, internal, business, haiku, fake_provider, caplog):
        caplog.set_level(logging.INFO)
        fake_provider.reply("POST", MESSAGES, sse=tool_call("current_datetime", "toolu_d", tokens=usage(fresh=40, written=2500)))
        fake_provider.reply("POST", MESSAGES, sse=answer("Es lunes.", tokens=usage(fresh=60, read=2500, written=150)))

        frames(door(Client(), STREAM, turn(business, ask("¿Qué día es hoy?"))))

        tokens = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "provider")
        assert [[line[name] for name in tokens] for line in map(fields, lines_of_calls(caplog))] == [
            ["2540", "0", "2500", "anthropic"],
            ["2710", "2500", "150", "anthropic"],
        ]
