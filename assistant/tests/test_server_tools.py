"""ASSISTANT-F14 · Tell the tools erplora.com runs from the Hub's: ``current_datetime``,
``currency_rate`` and ``web_search`` are run here and their result goes back to the model, which is asked again (at
most ``MAX_ROUNDS`` times, the last one without them, so it answers); a tool of the Hub ends the turn as a
``function_call`` for the Hub to run. A tool of ours that fails gives the model an error to answer with, never a failed
turn, and never a figure. They spend no message; each provider's calls have a budget per caller, and what is asked of
the search is bounded.

An answer built on them shows where it comes from: when the model names no source, the turn writes it (the panel's
Markdown drops the address of a link to another site, so only a plain address is seen). The provider of each tool is a
real HTTP server here (``fake_provider``): our client runs its real network code, and no test reaches a real one.
"""

import json
import logging
import socket
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from asgiref.sync import async_to_sync
from django.test import Client

from assistant import server_tools, turn
from assistant.schemas import Caller
from assistant.tests.conftest import openai_answer, openai_tool_call
from assistant.tests.doors import door, frames
from assistant.tests.fake_provider import openai_chunk

COMPLETIONS = "/v1/chat/completions"
RATES = "/v1/latest"
SEARCH = "/res/v1/web/search"
USD_EUR = {"amount": 1.0, "base": "USD", "date": "2026-11-04", "rates": {"EUR": 0.88755}}
KEY = "made-up-brave-key"
#: What Brave really answers a key it does not know: a 422 (recorded from a real call).
KEY_REFUSED = {
    "error": {
        "code": "SUBSCRIPTION_TOKEN_INVALID",
        "detail": "The provided subscription token is invalid.",
        "meta": {"component": "authentication"},
        "status": 422,
    },
    "type": "ErrorResponse",
}
ARTICLE = "https://www.boe.es/buscar/doc.php?id=BOE-A-2026-1"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_real_provider(settings):
    """Whatever the environment holds: no key, and an address nobody answers at, unless a test sets its provider."""
    settings.BRAVE_SEARCH_API_KEY = ""
    settings.ASSISTANT_RATES_URL = "http://127.0.0.1:1/rates"
    settings.ASSISTANT_SEARCH_URL = "http://127.0.0.1:1/search"


@pytest.fixture
def rates(settings, fake_provider):
    settings.ASSISTANT_RATES_URL = f"{fake_provider.url}{RATES}"
    return fake_provider


@pytest.fixture
def search(settings, fake_provider):
    settings.BRAVE_SEARCH_API_KEY = KEY
    settings.ASSISTANT_SEARCH_URL = f"{fake_provider.url}{SEARCH}"
    return fake_provider


@pytest.fixture
def stalled(monkeypatch):
    """A server that takes the call and never answers: the read runs out of time."""
    monkeypatch.setattr(server_tools, "TIMEOUT", httpx.Timeout(0.2))
    with socket.create_server(("127.0.0.1", 0)) as listening:
        yield f"http://127.0.0.1:{listening.getsockname()[1]}"


@pytest.fixture
def down():
    """An address nothing listens at."""
    with socket.create_server(("127.0.0.1", 0)) as listening:
        port = listening.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def run(name: str, arguments, who: str = "hub:one") -> dict:
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return json.loads(async_to_sync(server_tools.run)(name, raw, who))


def calls(fake_provider, path: str) -> list:
    return [seen for seen in fake_provider.requests if seen.path.split("?")[0] == path]


def row(url: str = ARTICLE, title: str = "BOE", description: str = "Ley de ejemplo", page_age: str = "2026-11-01T08:00:00") -> dict:
    """A row of Brave's ``web.results``."""
    return {"type": "search_result", "title": title, "url": url, "description": description, "page_age": page_age}


def found(*rows: dict) -> dict:
    """Brave's answer to a search that found ``rows``."""
    return {"type": "search", "query": {"original": "ley"}, "web": {"type": "search", "results": list(rows)}}


def sent(seen) -> dict:
    """The parameters a request carried in its address."""
    return {name: values[0] for name, values in parse_qs(urlsplit(seen.path).query).items()}


class TestWhichAreOurs:
    def test_without_a_search_key_the_date_and_the_rate_are_offered(self):
        assert [spec.name for spec in server_tools.specs()] == ["current_datetime", "currency_rate"]

    def test_with_a_search_key_the_search_is_offered_too(self, settings):
        settings.BRAVE_SEARCH_API_KEY = KEY

        assert [spec.name for spec in server_tools.specs()] == ["current_datetime", "currency_rate", "web_search"]

    def test_a_blank_key_offers_no_search(self, settings):
        settings.BRAVE_SEARCH_API_KEY = "   "

        assert "web_search" not in [spec.name for spec in server_tools.specs()]

    def test_a_search_asked_for_without_a_key_says_so_and_reaches_nobody(self, settings, fake_provider):
        settings.ASSISTANT_SEARCH_URL = f"{fake_provider.url}{SEARCH}"

        assert run("web_search", {"query": "ley"})["code"] == "web_search.not_configured"
        assert fake_provider.requests == []

    def test_a_tool_of_the_hub_is_not_ours(self):
        assert server_tools.is_server_tool("current_datetime") is True
        assert server_tools.is_server_tool("currency_rate") is True
        assert server_tools.is_server_tool("web_search") is True
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


class TestTheRate:
    def test_it_says_the_rate_its_date_and_where_it_comes_from(self, rates):
        rates.reply("GET", RATES, json=USD_EUR)

        result = run("currency_rate", {"from": "USD", "to": "EUR"})

        assert (result["from"], result["to"], result["rate"], result["date"]) == ("USD", "EUR", "0.88755", "2026-11-04")
        assert result["sources"] == [server_tools.RATES_SOURCE]
        [seen] = calls(rates, RATES)
        assert "base=USD" in seen.path and "symbols=EUR" in seen.path

    def test_it_converts_an_amount_to_the_cent(self, rates):
        rates.reply("GET", RATES, json=USD_EUR)

        result = run("currency_rate", {"from": "USD", "to": "EUR", "amount": 100})

        assert (result["amount"], result["converted"]) == ("100", "88.76")

    def test_without_an_amount_it_converts_one(self, rates):
        rates.reply("GET", RATES, json=USD_EUR)

        result = run("currency_rate", {"from": "USD", "to": "EUR"})

        assert (result["amount"], result["converted"]) == ("1", "0.89")

    def test_it_reads_the_codes_in_any_case(self, rates):
        rates.reply("GET", RATES, json=USD_EUR)

        assert run("currency_rate", {"from": " usd ", "to": "eur"})["rate"] == "0.88755"

    def test_a_currency_against_itself_is_one_and_asks_nobody(self, rates):
        result = run("currency_rate", {"from": "EUR", "to": "EUR", "amount": 5})

        assert (result["rate"], result["converted"]) == ("1", "5.00")
        assert "sources" not in result
        assert rates.requests == []

    @pytest.mark.parametrize("status", [404, 422])
    def test_a_currency_the_provider_does_not_know_gives_no_figure(self, rates, status):
        rates.reply("GET", RATES, status=status, json={"message": "not found"})

        result = run("currency_rate", {"from": "USD", "to": "ZZZ"})

        assert result["code"] == "currency_rate.unknown_currency"
        assert "rate" not in result and "sources" not in result

    @pytest.mark.parametrize("code", ["dollar", "US", "", None, 7, "U$D"])
    def test_what_is_no_currency_code_asks_nobody(self, rates, code):
        assert run("currency_rate", {"from": code, "to": "EUR"})["code"] == "currency_rate.unknown_currency"
        assert run("currency_rate", {"from": "EUR", "to": code})["code"] == "currency_rate.unknown_currency"
        assert rates.requests == []

    @pytest.mark.parametrize("amount", [0, -5, "abc", True, None, [], "NaN", "Infinity", 10**13])
    def test_an_amount_that_is_none_asks_nobody(self, rates, amount):
        assert run("currency_rate", {"from": "USD", "to": "EUR", "amount": amount})["code"] == "currency_rate.bad_amount"
        assert rates.requests == []

    @pytest.mark.parametrize("status", [500, 503, 301])
    def test_a_provider_that_fails_gives_no_figure(self, rates, status):
        rates.reply("GET", RATES, status=status, json={"message": "down"})

        result = run("currency_rate", {"from": "USD", "to": "EUR"})

        assert result["code"] == "currency_rate.unavailable"
        assert "rate" not in result

    def test_a_provider_that_takes_too_long_gives_no_figure(self, settings, stalled):
        settings.ASSISTANT_RATES_URL = stalled

        assert run("currency_rate", {"from": "USD", "to": "EUR"})["code"] == "currency_rate.unavailable"

    def test_a_provider_that_is_down_gives_no_figure(self, settings, down):
        settings.ASSISTANT_RATES_URL = down

        assert run("currency_rate", {"from": "USD", "to": "EUR"})["code"] == "currency_rate.unavailable"

    def test_a_server_without_its_certificates_gives_no_figure(self, rates, unreadable_ca):
        assert run("currency_rate", {"from": "USD", "to": "EUR"})["code"] == "currency_rate.unavailable"

    @pytest.mark.parametrize(
        "answer",
        [
            {"base": "USD", "date": "2026-11-04", "rates": {"GBP": 0.7}},
            {"base": "USD", "date": "2026-11-04", "rates": {"EUR": "abc"}},
            {"base": "USD", "date": "2026-11-04", "rates": {"EUR": 0}},
            {"base": "USD", "date": "2026-11-04", "rates": {"EUR": -1.2}},
            {"base": "USD", "date": "2026-11-04", "rates": {"EUR": True}},
            {"base": "USD", "date": "2026-11-04", "rates": {"EUR": None}},
            {"base": "USD", "date": "2026-11-04", "rates": []},
            {"base": "USD", "date": "2026-11-04"},
            {"base": "USD", "rates": {"EUR": 0.88}},
            {"base": "USD", "date": "yesterday", "rates": {"EUR": 0.88}},
            {"base": "GBP", "date": "2026-11-04", "rates": {"EUR": 0.88}},
            ["not", "an", "object"],
        ],
    )
    def test_an_answer_that_is_no_rate_gives_no_figure(self, rates, answer):
        rates.reply("GET", RATES, json=answer)

        result = run("currency_rate", {"from": "USD", "to": "EUR"})

        assert result["code"] == "currency_rate.bad_answer"
        assert "rate" not in result

    @pytest.mark.parametrize("body", [b"<html>not json</html>", b'{"base": "USD", "rates": {"EUR": NaN}, "date": "2026-11-04"}'])
    def test_a_body_that_cannot_be_read_gives_no_figure(self, rates, body):
        rates.reply("GET", RATES, body=body)

        result = run("currency_rate", {"from": "USD", "to": "EUR"})

        assert result["code"] == "currency_rate.bad_answer"
        assert "rate" not in result

    def test_a_caller_over_its_budget_asks_nobody_and_another_is_not_touched(self, rates, settings):
        settings.ASSISTANT_CURRENCY_RATE_RATELIMIT = "2/h"
        rates.reply("GET", RATES, always=True, json=USD_EUR)

        answers = [run("currency_rate", {"from": "USD", "to": "EUR"}, who="hub:one") for _ in range(3)]

        assert "rate" in answers[1]
        assert answers[2]["code"] == "currency_rate.budget_spent"
        assert len(calls(rates, RATES)) == 2
        assert "rate" in run("currency_rate", {"from": "USD", "to": "EUR"}, who="hub:two")


class TestTheSearch:
    def test_it_asks_with_the_key_for_a_bounded_list_of_plain_results(self, search):
        search.reply("GET", SEARCH, json=found(row()))

        run("web_search", {"query": " ley de ejemplo ", "language": "es"})

        [seen] = calls(search, SEARCH)
        assert seen.headers["x-subscription-token"] == KEY
        assert seen.headers["accept"] == "application/json"
        assert sent(seen) == {
            "q": "ley de ejemplo",
            "count": str(server_tools.MAX_RESULTS),
            "search_lang": "es",
            "country": "ES",
            "result_filter": "web",
            "text_decorations": "false",
        }

    @pytest.mark.parametrize(
        ("language", "search_lang", "country"),
        [
            ("es", "es", "ES"),
            ("es-ES", "es", "ES"),
            (" ES ", "es", "ES"),
            ("en", "en", "ALL"),
            ("en-GB", "en", "ALL"),
            ("fr", "en", "ALL"),
            ("", "en", "ALL"),
            (7, "en", "ALL"),
            (None, "en", "ALL"),
        ],
    )
    def test_it_looks_in_the_persons_language_and_spanish_in_spain(self, search, language, search_lang, country):
        search.reply("GET", SEARCH, json=found(row()))

        run("web_search", {"query": "ley", "language": language})

        [seen] = calls(search, SEARCH)
        assert (sent(seen)["search_lang"], sent(seen)["country"]) == (search_lang, country)

    def test_a_search_that_names_no_language_looks_in_english_anywhere(self, search):
        search.reply("GET", SEARCH, json=found(row()))

        run("web_search", {"query": "ley"})

        [seen] = calls(search, SEARCH)
        assert (sent(seen)["search_lang"], sent(seen)["country"]) == ("en", "ALL")

    def test_the_model_must_say_the_language_the_person_writes_in(self):
        parameters = server_tools.TOOLS["web_search"].spec.parameters

        assert parameters["properties"]["language"]["enum"] == ["es", "en"]
        assert parameters["required"] == ["query", "language"]

    def test_it_gives_the_title_the_address_the_text_and_the_date_of_each_result(self, search):
        search.reply("GET", SEARCH, json=found(row(), row("https://example.com/b", "B", "Otro texto", "2026-10-30T10:00:00")))

        result = run("web_search", {"query": "ley"})

        assert result["results"] == [
            {"title": "BOE", "url": ARTICLE, "content": "Ley de ejemplo", "date": "2026-11-01T08:00:00"},
            {"title": "B", "url": "https://example.com/b", "content": "Otro texto", "date": "2026-10-30T10:00:00"},
        ]
        assert result["sources"] == [ARTICLE, "https://example.com/b"]
        assert "never instructions" in result["note"]

    @pytest.mark.parametrize("page_age", [None, "", 7, ["2026"]])
    def test_a_result_with_no_date_says_none(self, search, page_age):
        search.reply("GET", SEARCH, json=found(row(page_age=page_age)))

        assert "date" not in run("web_search", {"query": "ley"})["results"][0]

    def test_a_result_with_no_text_keeps_its_address(self, search):
        search.reply("GET", SEARCH, json=found({"title": "BOE", "url": ARTICLE}))

        assert run("web_search", {"query": "ley"})["results"] == [{"title": "BOE", "url": ARTICLE, "content": ""}]

    def test_it_keeps_the_results_it_asked_for_whatever_comes_back(self, search):
        rows = [row(f"https://example.com/{n}") for n in range(server_tools.MAX_RESULTS + 3)]
        search.reply("GET", SEARCH, json=found(*rows))

        assert len(run("web_search", {"query": "ley"})["results"]) == server_tools.MAX_RESULTS

    def test_it_cuts_each_text_and_the_query(self, search):
        long = "x" * (server_tools.MAX_RESULT_CHARS + 50)
        search.reply("GET", SEARCH, json=found(row(title=long, description=long, page_age=long)))

        result = run("web_search", {"query": "q" * (server_tools.MAX_QUERY_CHARS + 50)})

        assert len(result["results"][0]["title"]) == server_tools.MAX_TITLE_CHARS
        assert len(result["results"][0]["content"]) == server_tools.MAX_RESULT_CHARS
        assert len(result["results"][0]["date"]) == server_tools.MAX_DATE_CHARS
        assert len(sent(calls(search, SEARCH)[0])["q"]) == server_tools.MAX_QUERY_CHARS

    def test_a_query_stays_within_the_words_the_provider_takes(self, search):
        """Its reference allows 75 words and its validation errors are 422s, which here mean the key or the parameters
        are wrong: a long question must not read as that."""
        search.reply("GET", SEARCH, json=found(row()))

        run("web_search", {"query": " ".join(["ley"] * (server_tools.MAX_QUERY_WORDS + 5))})

        assert len(sent(calls(search, SEARCH)[0])["q"].split()) == server_tools.MAX_QUERY_WORDS

    @pytest.mark.parametrize(
        "bad",
        [
            row("javascript:alert(1)"),
            row("ftp://example.com/a"),
            row("https://"),
            row("https:///no-host"),
            row("https://example.com/a b"),
            {"title": "No address", "description": "x"},
            {"url": 7, "title": "B", "description": "x"},
            "not a row",
        ],
    )
    def test_a_result_without_a_web_address_is_left_out(self, search, bad):
        search.reply("GET", SEARCH, json=found(bad, row("https://example.com/good")))

        result = run("web_search", {"query": "ley"})

        assert [item["url"] for item in result["results"]] == ["https://example.com/good"]
        assert result["sources"] == ["https://example.com/good"]

    @pytest.mark.parametrize("query", ["", "   ", None, 7, ["ley"]])
    def test_a_search_for_nothing_asks_nobody(self, search, query):
        assert run("web_search", {"query": query})["code"] == "web_search.empty_query"
        assert search.requests == []

    @pytest.mark.parametrize(
        "answer",
        [
            found(),
            {"type": "search", "query": {"original": "ley"}, "web": None},
            {"type": "search", "query": {"original": "ley"}},
        ],
    )
    def test_nothing_found_is_said_and_gives_no_source(self, search, answer):
        """The reference has ``web`` nullable: a search with no pages may leave it out."""
        search.reply("GET", SEARCH, json=answer)

        result = run("web_search", {"query": "ley"})

        assert result["code"] == "web_search.no_results"
        assert "sources" not in result

    @pytest.mark.parametrize("status", [400, 401, 402, 403, 422, 429, 500, 503])
    def test_a_provider_that_refuses_or_fails_is_said(self, search, status):
        search.reply("GET", SEARCH, status=status, json={"error": {"code": "X", "detail": "words of the provider"}})

        result = run("web_search", {"query": "ley"})

        assert result["code"] == "web_search.unavailable"
        assert "words of the provider" not in json.dumps(result)

    def test_a_provider_that_takes_too_long_is_said(self, search, settings, stalled):
        settings.ASSISTANT_SEARCH_URL = stalled

        assert run("web_search", {"query": "ley"})["code"] == "web_search.unavailable"

    def test_a_provider_that_is_down_is_said(self, search, settings, down):
        settings.ASSISTANT_SEARCH_URL = down

        assert run("web_search", {"query": "ley"})["code"] == "web_search.unavailable"

    @pytest.mark.parametrize(
        "reply",
        [
            {"body": b"<html>not json</html>"},
            {"json": ["not", "an", "object"]},
            {"json": {"answer": "no results here"}},
            {"json": {"type": "other", "web": {"results": [row()]}}},
            {"json": {"type": "search", "web": "not an object"}},
            {"json": {"type": "search", "web": {}}},
            {"json": {"type": "search", "web": {"results": "not a list"}}},
            {"json": found(row("javascript:alert(1)"))},
        ],
    )
    def test_an_answer_that_is_no_list_of_results_is_said(self, search, reply):
        search.reply("GET", SEARCH, **reply)

        result = run("web_search", {"query": "ley"})

        assert result["code"] == "web_search.bad_answer"
        assert "sources" not in result

    @pytest.mark.parametrize(
        ("status", "level"),
        [(401, logging.ERROR), (402, logging.ERROR), (403, logging.ERROR), (422, logging.ERROR), (429, logging.WARNING), (503, logging.WARNING)],
    )
    def test_a_key_that_is_refused_is_an_error_in_the_log_and_nothing_of_the_search_is(self, search, caplog, status, level):
        caplog.set_level(logging.DEBUG)
        search.reply("GET", SEARCH, status=status, json={"error": {"detail": "words of the provider"}})

        run("web_search", {"query": "Rosalía Quintanar"})

        [line] = [record for record in caplog.records if record.name == "assistant.server_tools"]
        assert line.levelno == level
        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert str(status) in line.getMessage()
        for secret in ("Rosalía", KEY, "words of the provider"):
            assert secret not in logged

    def test_a_key_brave_does_not_know_is_an_error_in_the_log(self, search, caplog):
        caplog.set_level(logging.DEBUG)
        search.reply("GET", SEARCH, status=422, json=KEY_REFUSED)

        result = run("web_search", {"query": "ley"})

        assert result["code"] == "web_search.unavailable"
        [line] = [record for record in caplog.records if record.name == "assistant.server_tools"]
        assert line.levelno == logging.ERROR
        assert "SUBSCRIPTION_TOKEN_INVALID" not in line.getMessage()

    def test_a_caller_over_its_budget_asks_nobody_and_another_is_not_touched(self, search, settings):
        settings.ASSISTANT_WEB_SEARCH_RATELIMIT = "1/d"
        search.reply("GET", SEARCH, always=True, json=found(row()))

        assert "results" in run("web_search", {"query": "ley"}, who="hub:one")
        assert run("web_search", {"query": "ley"}, who="hub:one")["code"] == "web_search.budget_spent"
        assert len(calls(search, SEARCH)) == 1
        assert "results" in run("web_search", {"query": "ley"}, who="hub:two")

    def test_a_tool_that_breaks_gives_an_error_never_raises(self, search, monkeypatch):
        def broken(*args, **kwargs):
            raise RuntimeError("the cache is down")

        monkeypatch.setattr(server_tools, "over_budget", broken)

        assert "error" in run("web_search", {"query": "ley"})


class TestWhatASearchMayCarry:
    """Brave's privacy notice leaves the queries out of its data processing addendum: what leaves is what is looked for."""

    def test_the_rules_keep_the_person_and_the_business_out_of_the_query(self, settings):
        settings.BRAVE_SEARCH_API_KEY = KEY

        rules = server_tools.rules()

        assert "A query carries only what is being looked for" in rules
        assert "no personal data and nothing of the business or its customers" in rules

    def test_the_tool_says_the_same_to_the_model(self):
        description = server_tools.TOOLS["web_search"].spec.description

        assert "A query carries only what is being looked for" in description
        assert "no personal data and nothing of the business or its customers" in description

    def test_without_the_search_the_rules_say_nothing_of_it(self):
        assert "A query carries" not in server_tools.rules()


class TestItsSettings:
    def test_the_key_and_the_address_are_braves(self):
        from config import settings as project

        assert isinstance(project.BRAVE_SEARCH_API_KEY, str)
        assert project.ASSISTANT_SEARCH_URL == "https://api.search.brave.com/res/v1/web/search"


class TestTheSourceLine:
    def test_an_answer_that_names_no_source_gets_its_address(self):
        assert server_tools.source_line("La ley cambió.", [ARTICLE]) == f"\n\n{ARTICLE}"

    def test_an_answer_that_writes_the_address_needs_nothing(self):
        assert server_tools.source_line(f"La ley cambió ({ARTICLE}).", [ARTICLE]) == ""

    def test_an_answer_that_names_its_site_needs_nothing(self):
        assert server_tools.source_line("Lo dice boe.es, hoy.", [ARTICLE]) == ""

    def test_it_finds_the_site_in_any_case(self):
        assert server_tools.source_line("Según BOE.es, hoy.", [ARTICLE]) == ""

    def test_a_link_shows_its_label_alone_so_its_address_does_not_count(self):
        """The panel's Markdown drops the address of a link to another site (``parseMarkdown``)."""
        assert server_tools.source_line(f"Lo dice [la ley]({ARTICLE}).", [ARTICLE]) == f"\n\n{ARTICLE}"

    def test_a_link_labelled_with_its_site_counts(self):
        assert server_tools.source_line(f"Lo dice [boe.es]({ARTICLE}).", [ARTICLE]) == ""

    def test_no_answer_or_no_source_writes_nothing(self):
        assert server_tools.source_line("", [ARTICLE]) == ""
        assert server_tools.source_line("   ", [ARTICLE]) == ""
        assert server_tools.source_line("La ley cambió.", []) == ""

    def test_it_shows_a_few_each_once(self):
        sources = [f"https://example.com/{n}" for n in range(server_tools.MAX_SOURCES_SHOWN + 2)]

        line = server_tools.source_line("Texto.", [sources[0], *sources])

        assert line.split() == sources[: server_tools.MAX_SOURCES_SHOWN]


class TestWhoseBudget:
    def test_each_business_and_account_has_its_own(self):
        one, other = "0190a3b4-0000-7000-8000-000000000001", "0190a3b4-0000-7000-8000-000000000002"

        assert turn.tool_budget(Caller(hub_id=one)) != turn.tool_budget(Caller(hub_id=other))
        assert turn.tool_budget(Caller(user_id=one)) != turn.tool_budget(Caller(user_id=other))
        assert turn.tool_budget(Caller(hub_id=one)) != turn.tool_budget(Caller(user_id=one))

    def test_every_demo_shares_one_since_anybody_can_open_another(self):
        assert turn.tool_budget(Caller(demo="demo-a")) == turn.tool_budget(Caller(demo="demo-b"))


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
        second = self.chat_requests(fake_provider)[1]
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

    def test_the_model_is_asked_again_five_times_at_most(self, internal, business, answering, fake_provider):
        """The number the manual gives (ASSISTANT-F14, step 4): the test above follows the constant, this one pins it."""
        for n in range(7):
            fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("current_datetime", "{}", call_id=f"call_{n}"))

        frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert len(self.chat_requests(fake_provider)) == 1 + 5

    def test_without_a_search_key_the_model_hears_of_the_rate_alone(self, internal, business, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        [sent] = self.chat_requests(fake_provider)
        system = sent.body["messages"][0]
        assert system == {"role": "system", "content": f"Be brief.\n\n{server_tools.rules()}"}
        assert "`currency_rate`" in system["content"]
        assert "web_search" not in system["content"]
        assert "as plain text" in system["content"]
        assert "give no figure" in system["content"]
        assert [tool["function"]["name"] for tool in sent.body["tools"]] == ["current_datetime", "currency_rate"]

    def test_with_a_search_key_the_model_hears_of_the_search_too(self, internal, business, answering, fake_provider, settings):
        settings.BRAVE_SEARCH_API_KEY = KEY
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        [sent] = self.chat_requests(fake_provider)
        assert sent.body["messages"][0]["content"].startswith("Be brief.")
        assert "`web_search`" in sent.body["messages"][0]["content"]
        assert [tool["function"]["name"] for tool in sent.body["tools"]] == ["current_datetime", "currency_rate", "web_search"]

    def test_the_rules_of_our_tools_do_not_replace_empty_instructions(self, internal, business, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", {**self.turn(business), "instructions": ""}))

        [sent] = self.chat_requests(fake_provider)
        assert "`currency_rate`" in sent.body["messages"][0]["content"]

    def rate_turn(self, fake_provider, answer: str, tokens=(80, 6)):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("currency_rate", '{"from": "USD", "to": "EUR"}', call_id="call_r", tokens=(50, 5)))
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer(answer, tokens=tokens))

    def test_a_rate_goes_to_the_model_the_hub_sees_no_call_and_the_source_is_written(self, internal, business, answering, rates):
        rates.reply("GET", RATES, json=USD_EUR)
        self.rate_turn(rates, "1 USD is 0.89 EUR.")

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert [frame["type"] for frame in got if isinstance(frame, dict)] == ["text_delta", "text_delta", "response", "usage"]
        said = [frame["text"] for frame in got if isinstance(frame, dict) and frame["type"] == "text_delta"]
        assert said == ["1 USD is 0.89 EUR.", f"\n\n{server_tools.RATES_SOURCE}"]
        assert "0.88755" not in json.dumps([frame for frame in got if isinstance(frame, dict)])
        _first, second = self.chat_requests(rates)
        assert json.loads(second.body["messages"][-1]["content"])["rate"] == "0.88755"

    def test_the_turn_at_once_says_the_source_too(self, internal, business, answering, rates):
        rates.reply("GET", RATES, json=USD_EUR)
        self.rate_turn(rates, "1 USD is 0.89 EUR.")

        answer = door(Client(), "/internal/assistant/chat", self.turn(business))

        assert answer.status_code == 200
        assert server_tools.RATES_SOURCE in json.dumps(answer.json()["output"])

    def test_a_rate_the_model_gives_with_its_source_gets_no_second_line(self, internal, business, answering, rates):
        rates.reply("GET", RATES, json=USD_EUR)
        self.rate_turn(rates, f"1 USD is 0.89 EUR ({server_tools.RATES_SOURCE}, 2026-11-04).")

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert len([frame for frame in got if isinstance(frame, dict) and frame["type"] == "text_delta"]) == 1

    def test_a_provider_that_fails_leaves_the_model_to_say_so_with_no_source_and_the_turn_answers(self, internal, business, answering, rates):
        rates.reply("GET", RATES, status=503, json={"message": "down"})
        self.rate_turn(rates, "I cannot get that rate now.")

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert [frame["type"] for frame in got if isinstance(frame, dict)] == ["text_delta", "response", "usage"]
        _first, second = self.chat_requests(rates)
        told = json.loads(second.body["messages"][-1]["content"])
        assert told["code"] == "currency_rate.unavailable" and "rate" not in told

    def test_a_search_goes_to_the_model_and_its_source_is_written(self, internal, business, answering, search):
        search.reply("GET", SEARCH, json=found(row()))
        search.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", '{"query": "ley"}', call_id="call_s"))
        search.reply("POST", COMPLETIONS, sse=openai_answer("La ley cambió."))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert got[0] == {"type": "web"}
        assert got[2] == {"type": "text_delta", "text": f"\n\n{ARTICLE}"}
        _first, second = self.chat_requests(search)
        assert json.loads(second.body["messages"][-1]["content"])["results"][0]["url"] == ARTICLE

    def test_a_turn_that_brought_pages_from_the_web_says_so_for_its_report(self, internal, business, answering, search):
        """The caller keeps the mark with the answer and sends it back with a report of it (saas#287)."""
        search.reply("GET", SEARCH, json=found(row()))
        search.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", '{"query": "ley"}', call_id="call_s"))
        search.reply("POST", COMPLETIONS, sse=openai_answer(f"La ley cambió: {ARTICLE}"))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert [frame["type"] for frame in got if isinstance(frame, dict)] == ["web", "text_delta", "response", "usage"]

    def test_the_mark_comes_as_the_pages_do_so_a_turn_that_fails_later_still_has_it(self, internal, business, answering, search):
        search.reply("GET", SEARCH, json=found(row()))
        search.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", '{"query": "ley"}', call_id="call_s"))
        search.reply("POST", COMPLETIONS, status=400, json={"error": {"message": "no"}})

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert [frame["type"] for frame in got if isinstance(frame, dict)] == ["web", "error", "usage"]

    @pytest.mark.parametrize("brave", [found(), None], ids=["no_pages", "no_search"])
    def test_a_turn_that_brought_nothing_from_the_web_says_so_too(self, internal, business, answering, search, rates, brave):
        if brave is None:
            rates.reply("GET", RATES, json=USD_EUR)
            self.rate_turn(rates, "1 USD is 0.89 EUR.")
        else:
            search.reply("GET", SEARCH, json=brave)
            search.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", '{"query": "ley"}', call_id="call_s"))
            search.reply("POST", COMPLETIONS, sse=openai_answer("No encontré nada."))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert "web" not in [frame["type"] for frame in got if isinstance(frame, dict)]

    def test_the_sources_of_every_round_count(self, internal, business, answering, search, settings):
        settings.ASSISTANT_RATES_URL = f"{search.url}{RATES}"
        search.reply("GET", RATES, json=USD_EUR)
        search.reply("GET", SEARCH, json=found(row()))
        search.reply("POST", COMPLETIONS, sse=openai_tool_call("currency_rate", '{"from": "USD", "to": "EUR"}', call_id="call_r"))
        search.reply("POST", COMPLETIONS, sse=openai_tool_call("web_search", '{"query": "ley"}', call_id="call_s"))
        search.reply("POST", COMPLETIONS, sse=openai_answer("Listo."))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        assert got[2]["text"].split() == [server_tools.RATES_SOURCE, ARTICLE]

    def test_an_answer_with_a_tool_of_the_hub_keeps_its_source(self, internal, business, answering, rates):
        rates.reply("GET", RATES, json=USD_EUR)
        rates.reply("POST", COMPLETIONS, sse=openai_tool_call("currency_rate", '{"from": "USD", "to": "EUR"}', call_id="call_r"))
        rates.reply("POST", COMPLETIONS, sse=[openai_chunk("1 USD is 0.89 EUR."), *openai_tool_call("sale_order_list", "{}", call_id="call_h")])

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business, [{"name": "sale_order_list"}])))

        types = [frame["type"] for frame in got if isinstance(frame, dict)]
        assert types[:3] == ["text_delta", "text_delta", "function_call"]
        assert got[1]["text"] == f"\n\n{server_tools.RATES_SOURCE}"

    def test_a_turn_that_only_calls_a_tool_of_the_hub_writes_no_source(self, internal, business, answering, rates):
        rates.reply("GET", RATES, json=USD_EUR)
        rates.reply("POST", COMPLETIONS, sse=openai_tool_call("currency_rate", '{"from": "USD", "to": "EUR"}', call_id="call_r"))
        rates.reply("POST", COMPLETIONS, sse=openai_tool_call("sale_order_list", "{}", call_id="call_h"))

        got = frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business, [{"name": "sale_order_list"}])))

        assert "text_delta" not in [frame["type"] for frame in got if isinstance(frame, dict)]

    def test_a_tool_of_ours_spends_the_callers_budget(self, internal, business, answering, rates, settings):
        settings.ASSISTANT_CURRENCY_RATE_RATELIMIT = "1/h"
        rates.reply("GET", RATES, always=True, json=USD_EUR)
        rates.reply("POST", COMPLETIONS, sse=openai_tool_call("currency_rate", '{"from": "USD", "to": "EUR"}', call_id="call_1"))
        rates.reply("POST", COMPLETIONS, sse=openai_tool_call("currency_rate", '{"from": "USD", "to": "EUR"}', call_id="call_2"))
        rates.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", self.turn(business)))

        last = self.chat_requests(rates)[-1]
        assert json.loads(last.body["messages"][-1]["content"])["code"] == "currency_rate.budget_spent"
        assert len(calls(rates, RATES)) == 1
