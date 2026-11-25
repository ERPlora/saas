"""ASSISTANT-F12 and ASSISTANT-F17 · One line in erplora.com's log for each call of the assistant to a model: how many
tools went and the characters of their specs, of the instructions, of the conversation and of the tools' results, and
the tokens its provider counted. Only numbers: the log keeps no word of what was sent (``test_privacy.py``)."""

import json
import logging
from decimal import Decimal

import pytest
from django.test import Client

from assistant.models import AIModel, AIRoutingPolicy
from assistant.tests.conftest import openai_answer, openai_tool_call
from assistant.tests.doors import door, frames
from base.logging import GDPRSafeFormatter

COMPLETIONS = "/v1/chat/completions"
STREAM = "/internal/assistant/chat/stream"
EVENT = "assistant.turn.model_call"
QUESTION = "¿Qué día es hoy?"
HUB_TOOL = {
    "type": "function",
    "name": "inventory_product_list",
    "description": "Lista los productos del catálogo.",
    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
}

pytestmark = pytest.mark.django_db


@pytest.fixture
def every_log(caplog):
    caplog.set_level(logging.INFO)
    return caplog


def lines_of_calls(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage().startswith(f"{EVENT} ")]


def fields(record: logging.LogRecord) -> dict[str, str]:
    return dict(pair.split("=", 1) for pair in record.getMessage().split()[1:])


def sent(fake_provider) -> list[dict]:
    return [seen.body for seen in fake_provider.requests if seen.path == COMPLETIONS]


def a_day_question(business, fake_provider) -> None:
    """A turn of two calls: the model asks erplora.com's ``current_datetime`` and then answers."""
    fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("current_datetime", "{}", call_id="call_d", tokens=(1200, 7)))
    fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Hoy es lunes.", tokens=(1450, 12)))
    payload = {"hub": business.slug, "messages": [{"role": "user", "content": QUESTION}], "instructions": "Answer in Spanish.", "tools": [HUB_TOOL]}
    frames(door(Client(), STREAM, payload))


def spec_chars(body: dict) -> int:
    return sum(len(json.dumps(tool["function"], ensure_ascii=False)) for tool in body["tools"])


def results_chars(body: dict) -> int:
    return sum(len(message["content"]) for message in body["messages"] if message["role"] == "tool")


class TestEachCall:
    def test_each_call_logs_the_size_of_what_it_was_sent_as_its_provider_got_it(self, internal, business, answering, fake_provider, every_log):
        a_day_question(business, fake_provider)

        first, second = map(fields, lines_of_calls(every_log))
        bodies = sent(fake_provider)
        assert len(bodies) == 2
        for line, body in zip((first, second), bodies, strict=True):
            assert line["tools"] == str(len(body["tools"]))
            assert line["tools_chars"] == str(spec_chars(body))
            assert line["instructions_chars"] == str(len(body["messages"][0]["content"]))
            assert line["tool_results_chars"] == str(results_chars(body))
        assert first["history_chars"] == str(len(QUESTION))
        assert int(second["history_chars"]) > int(first["history_chars"])
        assert first["tool_results_chars"] == "0"
        assert int(second["tool_results_chars"]) > 0

    def test_each_call_logs_its_tokens_who_asked_and_the_model_that_answered(self, internal, business, answering, fake_provider, every_log):
        a_day_question(business, fake_provider)

        first, second = map(fields, lines_of_calls(every_log))
        tokens = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
        assert [first[name] for name in tokens] == ["1200", "7", "0", "0"]
        assert [second[name] for name in tokens] == ["1450", "12", "0", "0"]
        for line in (first, second):
            assert (line["caller"], line["provider"], line["model"]) == (f"hub:{business.pk}", "openai", str(answering.pk))

    def test_the_line_reaches_the_log_as_written(self, internal, business, answering, fake_provider, every_log):
        a_day_question(business, fake_provider)

        records = lines_of_calls(every_log)
        assert len(records) == 2
        formatter = GDPRSafeFormatter("%(message)s")
        assert [formatter.format(record) for record in records] == [record.getMessage() for record in records]


class TestACallTheFallbackAnswered:
    def test_its_line_names_the_fallback_and_its_tokens(self, internal, business, answering, fake_provider, every_log):
        backup = AIModel.objects.create(
            provider=answering.provider, model_id="gpt-backup", display_name="Backup", price_input_per_1m=Decimal("1"), price_output_per_1m=Decimal("1")
        )
        AIRoutingPolicy.objects.filter(slot=AIRoutingPolicy.SLOT).update(fallback_model=backup)
        fake_provider.reply("POST", COMPLETIONS, status=503, json={"error": {"message": "overloaded"}})

        a_day_question(business, fake_provider)

        lines = [fields(record) for record in lines_of_calls(every_log)]
        assert [(line["model"], line["input_tokens"]) for line in lines] == [(str(backup.pk), "1200"), (str(backup.pk), "1450")]


class TestACallWithoutItsUsage:
    def test_a_call_that_fails_before_its_usage_logs_no_figures(self, internal, business, answering, fake_provider, every_log):
        fake_provider.reply("POST", COMPLETIONS, status=500, json={"error": {"message": "down"}})
        payload = {"hub": business.slug, "messages": [{"role": "user", "content": QUESTION}], "instructions": "Answer in Spanish."}

        frames(door(Client(), STREAM, payload))

        assert len(sent(fake_provider)) == 1
        assert lines_of_calls(every_log) == []
