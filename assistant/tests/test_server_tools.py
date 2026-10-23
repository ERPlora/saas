"""ASSISTANT-F14 (ASSISTANT-G46) · Tell the tools erplora.com runs from the Hub's: ``current_datetime`` (always),
``currency_rate`` (the ECB's reference rates, through Frankfurter, no key) and ``web_search`` (Tavily, offered only
with its key) are run here and their result goes back to the model, which is asked again (at most ``MAX_ROUNDS``
times, the last one without them, so it answers); a tool of the Hub ends the turn as a ``function_call`` for the Hub
to run. A tool of ours that fails gives the model an error to answer with, never a failed turn. They spend no message.

Cases of the old product's ``test_server_tools.py``, ``test_currency_provider.py``, ``test_websearch_provider.py``
and ``test_orchestrator_web_search.py``; Frankfurter and Tavily are the local fake (``fake_provider``) too.
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


@pytest.fixture
def frankfurter(fake_provider, settings):
    settings.ASSISTANT_CURRENCY_URL = f"{fake_provider.url}/frankfurter"
    return fake_provider


@pytest.fixture
def tavily(fake_provider, settings):
    settings.ASSISTANT_WEB_SEARCH_URL = f"{fake_provider.url}/tavily"
    settings.TAVILY_API_KEY = "tvly-test-0000000000000000"
    return fake_provider


class TestWhichAreOurs:
    def test_the_date_and_the_exchange_rate_are_always_offered_the_search_only_with_its_key(self, settings):
        settings.TAVILY_API_KEY = ""
        assert {spec.name for spec in server_tools.specs()} == {"current_datetime", "currency_rate"}

        settings.TAVILY_API_KEY = "tvly-test"
        assert {spec.name for spec in server_tools.specs()} == {"current_datetime", "currency_rate", "web_search"}

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


class TestTheExchangeRate:
    def test_it_converts_with_the_ecbs_rate_and_its_date(self, frankfurter):
        frankfurter.reply("GET", "/frankfurter/latest", json={"amount": 1.0, "base": "EUR", "date": "2026-10-22", "rates": {"USD": 1.0812}})

        result = run("currency_rate", {"from": "eur", "to": "usd", "amount": 25})

        assert result == {"from": "EUR", "to": "USD", "rate": 1.0812, "amount": 25, "converted": 27.03, "date": "2026-10-22", "source": "ECB"}
        [asked] = frankfurter.requests
        assert asked.path == "/frankfurter/latest?from=EUR&to=USD"

    def test_the_amount_is_one_when_not_given(self, frankfurter):
        frankfurter.reply("GET", "/frankfurter/latest", json={"amount": 1.0, "base": "EUR", "date": "2026-10-22", "rates": {"GBP": 0.86}})

        assert run("currency_rate", {"from": "EUR", "to": "GBP"})["converted"] == 0.86

    def test_the_same_currency_is_one_without_asking(self, frankfurter):
        assert run("currency_rate", {"from": "EUR", "to": "EUR", "amount": 3})["converted"] == 3
        assert frankfurter.requests == []

    @pytest.mark.parametrize("arguments", [{"from": "EUR"}, {"from": "EURO", "to": "USD"}, {"from": "E1R", "to": "USD"}, "not json"])
    def test_wrong_currencies_are_an_error_without_asking(self, frankfurter, arguments):
        assert "error" in run("currency_rate", arguments)
        assert frankfurter.requests == []

    def test_a_rate_is_asked_once_an_hour(self, frankfurter):
        frankfurter.reply("GET", "/frankfurter/latest", json={"amount": 1.0, "base": "EUR", "date": "2026-10-22", "rates": {"USD": 1.1}})

        run("currency_rate", {"from": "EUR", "to": "USD", "amount": 1})
        second = run("currency_rate", {"from": "EUR", "to": "USD", "amount": 10})

        assert second["converted"] == 11.0
        assert len(frankfurter.requests) == 1

    def test_frankfurter_down_is_an_error_for_the_model(self, frankfurter):
        frankfurter.reply("GET", "/frankfurter/latest", status=502, json={"message": "bad gateway"})

        assert "error" in run("currency_rate", {"from": "EUR", "to": "USD"})


class TestTheWebSearch:
    def test_it_gives_the_model_the_results_to_cite(self, tavily):
        tavily.reply(
            "POST",
            "/tavily/search",
            json={"results": [{"title": "IVA en España", "url": "https://agenciatributaria.es/iva", "content": "El tipo general es del 21 %.", "published_date": "2026-01-01"}]},
        )

        result = run("web_search", {"query": "tipo general IVA España"})

        assert result == {
            "query": "tipo general IVA España",
            "results": [{"title": "IVA en España", "url": "https://agenciatributaria.es/iva", "content": "El tipo general es del 21 %.", "published_date": "2026-01-01"}],
        }
        [asked] = tavily.requests
        assert asked.body == {"query": "tipo general IVA España", "max_results": 5}
        assert asked.headers["authorization"] == "Bearer tvly-test-0000000000000000"
        assert "tvly" not in asked.path

    def test_an_empty_query_does_not_ask(self, tavily):
        assert "error" in run("web_search", {"query": "  "})
        assert tavily.requests == []

    def test_without_its_key_it_says_so(self, settings):
        settings.TAVILY_API_KEY = ""

        assert "error" in run("web_search", {"query": "x"})

    def test_tavily_refusing_is_an_error_for_the_model_without_the_key(self, tavily):
        tavily.reply("POST", "/tavily/search", status=401, json={"detail": {"error": "Unauthorized: tvly-test-0000000000000000"}})

        result = run("web_search", {"query": "x"})

        assert "error" in result
        assert "tvly-test" not in json.dumps(result)

    def test_no_results_is_an_empty_list(self, tavily):
        tavily.reply("POST", "/tavily/search", json={"results": []})

        assert run("web_search", {"query": "x"})["results"] == []


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

    def test_with_the_search_offered_the_instructions_ask_to_cite(self, internal, business, answering, fake_provider, settings):
        settings.TAVILY_API_KEY = "tvly-test"
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        [sent] = self.chat_requests(fake_provider)
        system = sent.body["messages"][0]["content"]
        assert system.startswith("Be brief.")
        assert server_tools.WEB_SEARCH_RULE in system
