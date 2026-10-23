"""ASSISTANT-F14 (ASSISTANT-G46) · Tell the tools erplora.com runs from the Hub's: ``current_datetime`` is run here
and its result goes back to the model, which is asked again (at most ``MAX_ROUNDS`` times, the last one without it,
so it answers); a tool of the Hub ends the turn as a ``function_call`` for the Hub to run. A tool of ours that fails
gives the model an error to answer with, never a failed turn. They spend no message.

The old product's web search (Tavily) and exchange rates (Frankfurter) wait for the ERP stage (PLAN §30): not
offered, whatever the environment holds. Cases of the old product's ``test_server_tools.py``.
"""

import json
from datetime import UTC, datetime

import pytest
from asgiref.sync import async_to_sync
from django.test import Client

from assistant import server_tools
from assistant.tests.conftest import openai_answer, openai_tool_call
from assistant.tests.doors import door, frames

COMPLETIONS = "/v1/chat/completions"

pytestmark = pytest.mark.django_db


def run(name: str, arguments) -> dict:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return json.loads(async_to_sync(server_tools.run)(name, raw))


class TestWhichAreOurs:
    def test_only_the_date_is_ours_even_with_a_search_key_in_the_environment(self, settings):
        """The web search and the exchange rate wait for the ERP stage (PLAN §30): a key left in the environment
        offers nothing."""
        settings.TAVILY_API_KEY = "tvly-test"

        assert [spec.name for spec in server_tools.specs()] == ["current_datetime"]
        assert set(server_tools.TOOLS) == {"current_datetime"}

    def test_a_tool_of_the_hub_is_not_ours(self):
        assert server_tools.is_server_tool("current_datetime") is True
        assert server_tools.is_server_tool("sale_order_list") is False

    def test_an_unknown_tool_answers_an_error_never_raises(self):
        assert "error" in run("teleport", {})


class TestTheDate:
    def test_it_says_todays_date_time_and_weekday_in_utc(self):
        result = run("current_datetime", {})

        moment = datetime.fromisoformat(result["utc"])
        assert abs((moment - datetime.now(UTC)).total_seconds()) < 5
        assert result["date"] == moment.date().isoformat()
        assert result["weekday"] == moment.strftime("%A")

    def test_it_ignores_whatever_it_is_given(self):
        assert "utc" in run("current_datetime", "not json")


class TestInTheTurn:
    def turn(self, business, tools=()):
        return {"hub": business.slug, "messages": [{"role": "user", "content": "What day is it?"}], "instructions": "Be brief.", "tools": list(tools)}

    def chat_requests(self, fake_provider):
        return [seen for seen in fake_provider.requests if seen.path.endswith("/chat/completions")]

    def test_a_tool_of_ours_is_run_here_and_the_model_answers_with_it(self, internal, business, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("current_datetime", "{}", call_id="call_d", tokens=(50, 5)))
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("It is Friday.", tokens=(80, 6)))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert [frame["type"] for frame in got if isinstance(frame, dict)] == ["text_delta", "response", "usage"]
        first, second = self.chat_requests(fake_provider)
        assert second.body["messages"][-2]["tool_calls"][0]["function"]["name"] == "current_datetime"
        assert second.body["messages"][-1]["role"] == "tool"
        assert second.body["messages"][-1]["tool_call_id"] == "call_d"
        assert "utc" in json.loads(second.body["messages"][-1]["content"])
        response = next(frame for frame in got if isinstance(frame, dict) and frame["type"] == "response")
        assert response["usage"] == {"input_tokens": 130, "output_tokens": 11}
        assert response["continuation"] is None
        assert got[-2]["used"] == 1

    def test_the_hubs_tool_still_goes_back_to_the_hub(self, internal, business, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("sale_order_list", "{}"))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business, [{"name": "sale_order_list"}])))

        assert [frame["name"] for frame in got if isinstance(frame, dict) and frame["type"] == "function_call"] == ["sale_order_list"]

    def test_a_tool_of_the_hub_named_as_one_of_ours_is_ours(self, internal, business, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business, [{"name": "current_datetime", "description": "the Hub's"}])))

        [sent] = self.chat_requests(fake_provider)
        descriptions = [tool["function"]["description"] for tool in sent.body["tools"] if tool["function"]["name"] == "current_datetime"]
        assert len(descriptions) == 1 and descriptions[0] != "the Hub's"

    def test_after_the_last_round_the_model_must_answer(self, internal, business, answering, fake_provider):
        for n in range(server_tools.MAX_ROUNDS):
            fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("current_datetime", "{}", call_id=f"call_{n}"))
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Enough."))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        sent = self.chat_requests(fake_provider)
        assert len(sent) == server_tools.MAX_ROUNDS + 1
        assert "tools" not in sent[-1].body
        assert got[0] == {"type": "text_delta", "text": "Enough."}

    def test_the_instructions_are_the_hubs_alone_even_with_a_search_key(self, internal, business, answering, fake_provider, settings):
        settings.TAVILY_API_KEY = "tvly-test"
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        [sent] = self.chat_requests(fake_provider)
        assert sent.body["messages"][0] == {"role": "system", "content": "Be brief."}
        assert [tool["function"]["name"] for tool in sent.body["tools"]] == ["current_datetime"]
