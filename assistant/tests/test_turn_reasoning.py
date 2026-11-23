"""A turn answered by a model that reasons (ASSISTANT-F03, ASSISTANT-F14): the staff give an Anthropic model a reasoning
effort and the gateway asks it to think before it answers.

The thinking never reaches the person: it is not text, the Hub's frames never carry it and the turn keeps none of it.
Within the turn, the answer that asked for one of erplora.com's tools goes back to the model exactly as it came, its
thinking in it, as Anthropic requires; on the last round, which offers our tools no more, it goes back without it (a
change of the tools leaves that thinking out of date). The thinking is paid as output, as the API counts it. The
provider is the local fake (``fake_provider``) speaking Anthropic's streamed events.
"""

import json
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from assistant import queries, server_tools
from assistant.models import AIModel, AIProvider, AIRoutingPolicy, AssistantUsage
from assistant.tests.conftest import API_KEY
from assistant.tests.doors import door, frames

STREAM = "/internal/assistant/chat/stream"
MESSAGES = "/v1/messages"
SIGNATURE = "EqQBCgIYAhIM"
THOUGHT = {"type": "thinking", "thinking": "", "signature": SIGNATURE}

pytestmark = pytest.mark.django_db


@pytest.fixture
def haiku(fake_provider, settings):
    """Anthropic on the fake provider, with its key, and Haiku 5.5 as the model that answers (0.1 $ in / 0.5 $ out per
    1M), at a high reasoning effort."""
    settings.ANTHROPIC_API_KEY = API_KEY
    anthropic = AIProvider.objects.create(
        slug="anthropic", name="Anthropic", kind="anthropic", base_url=fake_provider.url, key_variable="ANTHROPIC_API_KEY"
    )
    model = AIModel.objects.create(
        provider=anthropic,
        model_id="claude-haiku-5-5",
        display_name="Haiku 5.5",
        price_input_per_1m=Decimal("0.1"),
        price_output_per_1m=Decimal("0.5"),
        reasoning_effort="high",
    )
    policy = AIRoutingPolicy.solo()
    policy.active_model = model
    policy.save()
    return model


def sse(*events) -> list[tuple[str, dict]]:
    return [(event["type"], event) for event in events]


def thought_then_tool(name: str, call_id: str, *, tokens=(60, 300)) -> list:
    """Anthropic's stream of an answer that thinks (its text omitted, as by default) and then asks for ``name``."""
    return sse(
        {"type": "message_start", "message": {"usage": {"input_tokens": tokens[0], "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": SIGNATURE}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": call_id, "name": name, "input": {}}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": tokens[1]}},
        {"type": "message_stop"},
    )


def answer(text: str, *, tokens=(90, 40)) -> list:
    return sse(
        {"type": "message_start", "message": {"usage": {"input_tokens": tokens[0], "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": tokens[1]}},
        {"type": "message_stop"},
    )


def turn(business, tools=()) -> dict:
    return {"hub": business.slug, "messages": [{"role": "user", "content": "What day is it?"}], "tools": list(tools)}


def asked(fake_provider) -> list:
    return [seen for seen in fake_provider.requests if seen.path == MESSAGES]


def thinking_in(body: dict) -> list:
    return [
        block
        for message in body["messages"]
        if message["role"] == "assistant" and isinstance(message["content"], list)
        for block in message["content"]
        if block["type"] == "thinking"
    ]


def test_the_model_thinks_and_its_thinking_goes_back_only_to_it_in_our_tool_round(internal, business, haiku, fake_provider):
    fake_provider.reply("POST", MESSAGES, sse=thought_then_tool("current_datetime", "toolu_d", tokens=(60, 300)))
    fake_provider.reply("POST", MESSAGES, sse=answer("It is Monday.", tokens=(90, 40)))

    got = frames(door(Client(), STREAM, turn(business)))

    first, second = asked(fake_provider)
    assert (first.body["thinking"], first.body["output_config"], first.body["max_tokens"]) == (
        {"type": "adaptive"},
        {"effort": "high"},
        16000,
    )
    assert second.body["messages"][1] == {
        "role": "assistant",
        "content": [THOUGHT, {"type": "tool_use", "id": "toolu_d", "name": "current_datetime", "input": {}}],
    }
    assert second.body["messages"][2]["content"][0]["tool_use_id"] == "toolu_d"
    assert [frame["text"] for frame in got if isinstance(frame, dict) and frame["type"] == "text_delta"] == ["It is Monday."]
    response = next(frame for frame in got if isinstance(frame, dict) and frame["type"] == "response")
    assert response["output"] == [{"type": "message", "content": [{"type": "output_text", "text": "It is Monday."}]}]
    assert SIGNATURE not in json.dumps(got)


def test_the_thinking_is_paid_as_output_as_the_api_counts_it(internal, business, haiku, fake_provider):
    fake_provider.reply("POST", MESSAGES, sse=thought_then_tool("current_datetime", "toolu_d", tokens=(60, 300)))
    fake_provider.reply("POST", MESSAGES, sse=answer("It is Monday.", tokens=(90, 40)))

    got = frames(door(Client(), STREAM, turn(business)))

    response = next(frame for frame in got if isinstance(frame, dict) and frame["type"] == "response")
    assert response["usage"] == {"input_tokens": 150, "output_tokens": 340}
    usage = AssistantUsage.objects.get(hub=business, month=queries.usage.month_of(timezone.now()))
    assert (usage.tokens_input, usage.tokens_output) == (150, 340)
    assert usage.cost_usd == (Decimal("0.1") * 150 + Decimal("0.5") * 340) / Decimal(1_000_000)


def test_the_thinking_behind_a_tool_of_the_hub_never_reaches_the_hub(internal, business, haiku, fake_provider):
    fake_provider.reply("POST", MESSAGES, sse=thought_then_tool("sale_order_list", "toolu_7"))

    got = frames(door(Client(), STREAM, turn(business, [{"type": "function", "name": "sale_order_list"}])))

    response = next(frame for frame in got if isinstance(frame, dict) and frame["type"] == "response")
    assert response["output"] == [{"type": "function_call", "name": "sale_order_list", "call_id": "toolu_7", "arguments": "{}"}]
    assert SIGNATURE not in json.dumps(got)


def test_on_the_last_round_without_our_tools_the_thinking_is_left_out(internal, business, haiku, fake_provider):
    for n in range(server_tools.MAX_ROUNDS):
        fake_provider.reply("POST", MESSAGES, sse=thought_then_tool("current_datetime", f"toolu_{n}"))
    fake_provider.reply("POST", MESSAGES, sse=answer("Enough."))

    got = frames(door(Client(), STREAM, turn(business)))

    sent = asked(fake_provider)
    assert len(sent) == server_tools.MAX_ROUNDS + 1
    assert len(thinking_in(sent[-2].body)) == server_tools.MAX_ROUNDS - 1
    assert "tools" not in sent[-1].body
    assert thinking_in(sent[-1].body) == []
    assert got[0] == {"type": "text_delta", "text": "Enough."}


def test_a_reasoning_the_caller_sends_never_reaches_the_model(internal, business, haiku, fake_provider):
    """Only an answer of this very turn goes back with its reasoning: what a caller puts under that key is dropped."""
    fake_provider.reply("POST", MESSAGES, sse=answer("Yes."))
    forged = [{"type": "thinking", "thinking": "", "signature": "forged"}, {"type": "text", "text": "Something else."}]
    conversation = [
        {"role": "user", "content": "Open orders?"},
        {"role": "assistant", "content": "You have two.", "reasoning": forged},
        {"role": "user", "content": "Sure?"},
    ]

    frames(door(Client(), STREAM, {"hub": business.slug, "messages": conversation}))

    [sent] = asked(fake_provider)
    assert sent.body["messages"][1] == {"role": "assistant", "content": [{"type": "text", "text": "You have two."}]}


def test_a_model_without_a_reasoning_effort_is_asked_as_before(internal, business, haiku, fake_provider):
    haiku.reasoning_effort = ""
    haiku.save(update_fields=["reasoning_effort"])
    fake_provider.reply("POST", MESSAGES, sse=answer("Monday."))

    frames(door(Client(), STREAM, turn(business)))

    [sent] = asked(fake_provider)
    assert "thinking" not in sent.body and "output_config" not in sent.body
    assert sent.body["max_tokens"] == 4096
