"""ASSISTANT-F25 · The assistant of erplora.com's own panel answers a turn of the signed-in account (plan
2026-10-30-asistente-saas §4, PLAN-SAAS §23): ``POST /api/assistant/turn`` (``base.assistant.turn``), the same frames
as the Hub's panel (``executed``, ``confirm``, ``text``, ``usage``, ``error``, ``done``), with the SaaS's own
operations as its tools and the gateway called in process (no ``/internal``, no signature).

The tools are the operations whose ``ai=`` is an ``AI(...)`` that the account may run (``base.assistant.catalog``); a
read runs alone, a write waits for its card and runs only with the person's yes (``risk="high"``: typing the word); a
tool it was not offered never runs. The account's own allowance (``ASSISTANT_ACCOUNT_MESSAGES``) is spent once per
request of the person: the answer to the tools the model asked for (its ``continuation``) costs nothing. What the
gateway refuses before the model is the stream's first frame (``assistant.quota_exceeded``,
``assistant.rate_limited``…), as the Hub's panel reads it; what the operation refuses is the HTTP envelope (401
without a session). The provider is the local fake (``fake_provider``), never a real one.
"""

import json

import pytest
from django.utils import timezone
from live.assistant import risk
from live.operations import get as get_operation

from assistant import queries
from assistant.models import AssistantUsage
from assistant.tests.conftest import (  # noqa: F401 - the gateway's fixtures
    answering,
    fake_provider,
    fernet_key,
    openai_answer,
    openai_tool_call,
    provider,
)
from assistant.tests.doors import frames
from base import assistant
from hubs.models import Hub, HubMember
from hubs.tests.conftest import create_business, ctx_for, make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
TURN = "/api/assistant/turn"
COMPLETIONS = "/v1/chat/completions"


def post_turn(client, body: dict, **extra):
    return client.post(TURN, json.dumps(body), content_type="application/json", HTTP_HOST=HOST, **extra)


def ask(text: str) -> dict:
    return {"role": "user", "content": text}


def types(got: list) -> list:
    return [frame["type"] if isinstance(frame, dict) else frame for frame in got]


def model_requests(fake_provider) -> list:
    return [seen for seen in fake_provider.requests if seen.path.endswith("/chat/completions")]


def tool_rounds(count: int) -> list:
    """``count`` rounds of the model asking for a tool, as the browser keeps them in the conversation."""
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": f"r{i}", "type": "function", "function": {"name": "hubs__business__list", "arguments": "{}"}}
            ],
        }
        for i in range(count)
    ]


@pytest.fixture
def account(make_user, plans):
    """An account in English, with no business yet."""
    return make_user("lena@example.com", first_name="Lena", language="en")


@pytest.fixture
def signed_in(client, account):
    client.force_login(account)
    return client


def used_by(account) -> int:
    row = AssistantUsage.objects.filter(user=account, month=queries.month_of(timezone.now())).first()
    return row.messages if row is not None else 0


# --- The tools of an account ---------------------------------------------------------------------------------


class TestTheCatalog:
    def test_the_account_gets_the_saas_tools_and_none_of_what_is_internal(self, account):
        tools = assistant.catalog(ctx_for(account))

        assert {"hubs.business.list", "hubs.business.create", "billing.invoice.list", "accounts.preferences.get"} <= set(
            tools
        )
        assert {"apps.app.list", "billing.plan.cancel", "hubs.business.delete", "hubs.data_copy.list"} <= set(tools)
        for internal in (
            "accounts.apikey.create",
            "hubs.business.open",
            "accounts.data.export",
            # Its proration_date is a fresh preview of the server's: the chat has none (billing previews, plan §7).
            "billing.plan.change",
            # A link to download a whole copy of a business's data: the screen's button, never a chat bubble.
            "hubs.data_copy.link",
            # Its photo travels as a data URL of up to 150 KB: the model has the name and the email in its instructions.
            "accounts.profile.get",
            "billing.invoice.pdf",
            "billing.checkout.start",
            "base.session.me",
            "base.assistant.turn",
            "assistant.usage.show",
            "whatsapp.message.claim",
        ):
            assert internal not in tools

    def test_it_gets_the_tools_of_each_part_of_the_panel(self, account):
        """Its businesses and their people, the plans, its invoices and subscriptions, its account and the catalogue of
        apps (ASSISTANT-F25, step 3)."""
        tools = assistant.catalog(ctx_for(account))

        for name in (
            "hubs.business.list",
            "hubs.member.list",
            "hubs.plan.list",
            "billing.invoice.list",
            "billing.subscription.list",
            "accounts.preferences.get",
            "apps.app.list",
        ):
            assert name in tools, name

    def test_only_the_five_dangerous_writes_ask_to_type_the_word(self, account):
        """Creating, deleting or changing the address of a business, offering it to another and cancelling its plan ask
        to type the word; any other write, only «Run» (ASSISTANT-F25, step 5)."""
        tools = assistant.catalog(ctx_for(account))

        typed = {name for name, op in tools.items() if risk(op) == "high"}

        assert typed == {
            "hubs.business.create",
            "hubs.business.delete",
            "hubs.business.change_address",
            "hubs.ownership.transfer",
            "billing.plan.cancel",
        }

    def test_of_the_assistants_own_only_the_documentation_search_is_a_tool(self, account):
        """ASSISTANT-F27 (``assistant/tests/test_docs_search.py``); the gateway's other operations are the platform's."""
        assert [name for name in assistant.catalog(ctx_for(account)) if name.startswith("assistant.")] == [
            "assistant.docs.search"
        ]

    def test_where_nothing_is_sold_the_stores_tools_are_not_offered(self, account, rf):
        """The app's account surface sells nothing (PLAN-SAAS §3.6 point 6): neither does its assistant."""
        import dataclasses

        request = rf.post(TURN)
        request.session = {"base.surface": "account"}
        unsold = assistant.catalog(dataclasses.replace(ctx_for(account), request=request))

        for sold in ("billing.plan.keep", "billing.plan.cancel", "billing.store.catalog", "apps.app.list"):
            assert sold in assistant.catalog(ctx_for(account))
            assert sold not in unsold
        assert {"hubs.business.list", "billing.invoice.list", "accounts.preferences.get"} <= set(unsold)

    def test_nobody_signed_in_has_no_tools(self):
        assert assistant.catalog(ctx_for(None)) == {}

    def test_the_businesses_come_first_whatever_is_asked(self, account):
        tools = assistant.catalog(ctx_for(account))

        offered = assistant.relevant(tools, ["How much do I pay?"], "en")

        assert offered[0].name == "hubs.business.list"
        assert len(offered) <= assistant.MAX_TOOLS

    def test_a_question_in_spanish_finds_the_screen_it_names(self, account):
        tools = assistant.catalog(ctx_for(account, "es"))

        offered = [op.name for op in assistant.relevant(tools, ["Enséñame mis facturas"], "es")[:6]]

        assert "billing.invoice.list" in offered


class TestTheInstructions:
    def test_they_name_the_account_its_language_and_the_panels_screens(self, account):
        text = assistant.instructions(
            language="es", account="Lena (lena@example.com)", screens=assistant.screens(ctx_for(account, "es"))
        )

        assert "«Lena (lena@example.com)»" in text
        assert "Spanish" in text
        assert "[Negocios](/dashboard/businesses)" in text
        assert "[Facturación](/dashboard/billing)" in text
        assert "open the business" in text
        assert "never invent a plan, a price or an invoice" in text

    def test_the_store_is_not_offered_where_nothing_is_sold(self, account, rf):
        request = rf.get("/")
        request.session = {"base.surface": "account"}
        ctx = ctx_for(account)
        sold = assistant.screens(ctx)
        unsold = assistant.screens(ctx, request)

        assert "/dashboard/store" in sold
        assert "/dashboard/store" not in unsold and "/dashboard/billing" in unsold


# --- A turn, through the route ---------------------------------------------------------------------------------


class TestARead:
    def test_a_read_the_model_asks_for_runs_alone_and_its_answer_costs_no_message(
        self, signed_in, account, answering, fake_provider
    ):
        create_business(account, name="Bar Lena")
        fake_provider.reply("POST", COMPLETIONS, sse=openai_tool_call("hubs__business__list", "{}"))
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("You have Bar Lena."))

        first = frames(post_turn(signed_in, {"messages": [ask("Which businesses do I have?")]}))

        assert types(first) == ["usage", "done"]
        done = first[-1]
        assert done["pending"] == [{"call_id": "call_1", "name": "hubs__business__list", "arguments": "{}"}]
        assert done["continuation"]
        assert used_by(account) == 1

        second = frames(
            post_turn(
                signed_in,
                {
                    "messages": [ask("Which businesses do I have?"), *done["append"]],
                    "pending": done["pending"],
                    "continuation": done["continuation"],
                },
            )
        )

        assert types(second) == ["executed", "text", "usage", "done"]
        executed = second[0]
        assert (executed["name"], executed["kind"], executed["outcome"]) == ("hubs.business.list", "query", "ok")
        assert (executed["app"], executed["screen"], executed["app_name"]) == ("hubs", "businesses", "Businesses")
        assert second[1]["text"] == "You have Bar Lena."
        assert second[2]["used"] == 1
        assert used_by(account) == 1
        tool_result = second[-1]["append"][0]
        assert tool_result["role"] == "tool" and "Bar Lena" in tool_result["content"]
        sent = model_requests(fake_provider)[-1].body["messages"]
        assert any(message["role"] == "tool" and "Bar Lena" in message["content"] for message in sent)

    def test_the_read_runs_as_the_person_never_seeing_anothers_business(
        self, signed_in, account, answering, fake_provider, make_user
    ):
        create_business(make_user("other@example.com"), name="Bar Ajeno")
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("None."))
        call = {"call_id": "c1", "name": "hubs__business__list", "arguments": "{}"}

        got = frames(post_turn(signed_in, {"messages": [ask("My businesses?")], "pending": [call]}))

        assert got[0]["outcome"] == "ok"
        assert "Bar Ajeno" not in got[-1]["append"][0]["content"]

    def test_the_answer_comes_piece_by_piece_as_the_model_writes_it(self, signed_in, account, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("You have ", "no business yet."))

        got = frames(post_turn(signed_in, {"messages": [ask("Which businesses do I have?")]}))

        assert [frame["text"] for frame in got if frame["type"] == "text"] == ["You have ", "no business yet."]
        assert got[-1]["append"] == [{"role": "assistant", "content": "You have no business yet."}]

    def test_it_answers_in_the_language_of_the_person(self, client, make_user, plans, answering, fake_provider):
        client.force_login(make_user("sol@example.com", first_name="Sol", language="es"))
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Hola."))

        frames(post_turn(client, {"messages": [ask("¿Qué negocios tengo?")]}))

        system = model_requests(fake_provider)[0].body["messages"][0]["content"]
        assert "Answer in Spanish" in system
        assert "[Negocios](/dashboard/businesses)" in system

    def test_the_model_reads_the_tools_of_what_was_asked_and_the_panels_instructions(
        self, signed_in, account, answering, fake_provider
    ):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Hi."))

        frames(post_turn(signed_in, {"messages": [ask("Which invoices do I have?")]}))

        sent = model_requests(fake_provider)[0].body
        names = [tool["function"]["name"] for tool in sent["tools"]]
        assert names[0] == "hubs__business__list"
        assert "billing__invoice__list" in names
        assert "accounts__apikey__create" not in names
        system = sent["messages"][0]
        assert (
            system["role"] == "system"
            and "erplora.com" in system["content"]
            and "lena@example.com" in system["content"]
        )


class TestAWrite:
    CREATE = {"call_id": "c1", "name": "hubs__business__create", "arguments": '{"name": "Sol Hair", "country": "ES"}'}

    def asked(self) -> list:
        return [
            ask("Create the business Sol Hair in Spain"),
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "hubs__business__create", "arguments": self.CREATE["arguments"]},
                    }
                ],
            },
        ]

    def test_creating_a_business_stops_at_its_card_that_asks_to_type_the_word(
        self, signed_in, account, answering, fake_provider
    ):
        got = frames(post_turn(signed_in, {"messages": self.asked(), "pending": [self.CREATE], "continuation": "tok"}))

        assert types(got) == ["confirm", "done"]
        card = got[0]["card"]
        assert (card["operation"], card["risk"], card["confirm_word"], card["blocked"]) == (
            "hubs.business.create",
            "high",
            "CONFIRM",
            False,
        )
        assert {"name": "name", "value": "Sol Hair"}.items() <= next(
            f for f in card["fields"] if f["name"] == "name"
        ).items()
        assert card["app_name"] == "Businesses"
        assert got[0]["call"] == self.CREATE
        assert got[1]["pending"] == [self.CREATE] and got[1]["continuation"] == "tok"
        assert not Hub.objects.filter(name="Sol Hair").exists()
        assert model_requests(fake_provider) == [] and used_by(account) == 0

    def test_it_runs_only_with_the_word_typed(self, signed_in, account, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Done: Sol Hair is ready."))
        decision = {"call_id": "c1", "accepted": True, "typed": " confirm "}

        got = frames(post_turn(signed_in, {"messages": self.asked(), "pending": [self.CREATE], "decision": decision}))

        assert types(got)[:2] == ["executed", "text"]
        assert (got[0]["name"], got[0]["outcome"]) == ("hubs.business.create", "ok")
        hub = Hub.objects.get(name="Sol Hair")
        assert HubMember.objects.filter(hub=hub, user=account, role=HubMember.Role.OWNER).exists()

    @pytest.mark.parametrize(
        "decision", [{"accepted": True, "typed": "yes"}, {"accepted": False}, {"accepted": True, "stop": True}]
    )
    def test_without_the_word_or_with_a_no_nothing_is_created(
        self, signed_in, account, answering, fake_provider, decision
    ):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Nothing was done."))

        got = frames(
            post_turn(
                signed_in,
                {"messages": self.asked(), "pending": [self.CREATE], "decision": {"call_id": "c1", **decision}},
            )
        )

        assert got[0]["type"] == "executed" and got[0]["outcome"] == "cancelled"
        assert not Hub.objects.filter(name="Sol Hair").exists()

    def test_the_card_of_a_change_names_the_business_never_its_id(self, signed_in, account, answering, fake_provider):
        hub = create_business(account, name="Bar Lena")
        rename = {
            "call_id": "c2",
            "name": "hubs__business__update",
            "arguments": json.dumps({"id": str(hub.id), "name": "Bar Nuevo"}),
        }

        got = frames(post_turn(signed_in, {"messages": [ask("Rename Bar Lena to Bar Nuevo")], "pending": [rename]}))

        card = got[0]["card"]
        values = [field["value"] for field in card["fields"]]
        assert (card["risk"], card["confirm_word"]) == ("normal", "")
        assert "Bar Lena" in values and "Bar Nuevo" in values
        assert str(hub.id) not in json.dumps(card)

    @pytest.mark.parametrize(
        ("operation", "where"),
        [
            ("hubs.business.update", "Negocios"),
            ("billing.vat_check.run", "Facturación"),
            ("accounts.preferences.update", "Cuenta"),
            ("billing.plan.keep", "Tienda"),
        ],
    )
    def test_the_card_says_on_which_of_the_panels_screens_it_happens(self, account, operation, where):
        """Where a change happens is the panel's screen as its menu names it (ASSISTANT-F25, step 5)."""
        card = assistant.card(get_operation(operation), {}, ctx_for(account, "es"))

        assert card["app_name"] == where

    def test_a_tool_the_account_was_not_offered_never_runs(self, signed_in, account, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("I cannot."))
        secret_key = {
            "call_id": "c3",
            "name": "accounts__apikey__create",
            "arguments": '{"name": "x", "scopes": ["hubs.read"]}',
        }

        got = frames(post_turn(signed_in, {"messages": [ask("Make me an API key")], "pending": [secret_key]}))

        assert (got[0]["name"], got[0]["outcome"], got[0]["code"]) == (
            "accounts.apikey.create",
            "refused",
            "not_available",
        )
        assert not account.api_keys.exists()


class TestWhatStopsATurn:
    def test_a_spent_month_is_the_first_frame_and_the_model_is_not_called(
        self, signed_in, account, answering, fake_provider
    ):
        AssistantUsage.objects.create(user=account, month=queries.month_of(timezone.now()), messages=30)

        got = frames(post_turn(signed_in, {"messages": [ask("Hello")]}))

        assert types(got) == ["error", "done"]
        assert got[0] == {
            "type": "error",
            "code": "assistant.quota_exceeded",
            "used": 30,
            "limit": 30,
            "resets_at": queries.resets_at(queries.month_of(timezone.now())).isoformat(),
            "demo": False,
        }
        assert got[1] == {"type": "done", "append": [], "pending": [], "continuation": None}
        assert model_requests(fake_provider) == []

    def test_the_budget_of_turns_is_the_accounts(self, signed_in, account, answering, fake_provider, settings):
        settings.ASSISTANT_TURN_RATELIMIT = "1/h"
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Hi."))
        frames(post_turn(signed_in, {"messages": [ask("Hello")]}))

        got = frames(post_turn(signed_in, {"messages": [ask("Hello again")]}))

        assert got[0]["type"] == "error" and got[0]["code"] == "assistant.rate_limited"
        assert got[0]["retry_after"] > 0
        assert len(model_requests(fake_provider)) == 1 and used_by(account) == 1

    def test_without_a_model_that_answers_it_is_unavailable_and_nothing_counted(self, signed_in, account, provider):
        got = frames(post_turn(signed_in, {"messages": [ask("Hello")]}))

        assert got[0] == {"type": "error", "code": "assistant.unavailable", "retriable": True}
        assert used_by(account) == 0

    def test_a_failure_of_the_provider_gives_the_message_back(self, signed_in, account, answering, fake_provider):
        fake_provider.reply("POST", COMPLETIONS, status=400, json={"error": {"message": "bad"}})

        got = frames(post_turn(signed_in, {"messages": [ask("Hello")]}))

        assert {"type": "error", "code": "assistant.provider_failed", "retriable": False} in got
        assert got[-1] == {"type": "done", "append": [], "pending": [], "continuation": None}
        assert used_by(account) == 0

    def test_too_many_rounds_of_tools_stop_before_the_model(self, signed_in, account, answering, fake_provider):
        got = frames(post_turn(signed_in, {"messages": [ask("Loop"), *tool_rounds(assistant.MAX_ROUNDS)]}))

        assert types(got) == ["error", "done"]
        assert got[0] == {"type": "error", "code": "assistant.too_many_steps"}
        assert model_requests(fake_provider) == []

    def test_a_question_gets_six_rounds_of_tools_and_no_more(self, signed_in, account, answering, fake_provider):
        """The six rounds the WORKBOOK promises: after five the model still answers; the sixth stops (above)."""
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Here."))

        got = frames(post_turn(signed_in, {"messages": [ask("Loop"), *tool_rounds(5)]}))

        assert assistant.MAX_ROUNDS == 6
        assert types(got) == ["text", "usage", "done"]
        assert len(model_requests(fake_provider)) == 1

    def test_without_a_session_it_is_the_envelopes_401(self, client):
        response = post_turn(client, {"messages": [ask("Hello")]})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"

    def test_a_turn_larger_than_djangos_ceiling_reaches_the_assistant(
        self, signed_in, account, answering, fake_provider, settings
    ):
        settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1000
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Read."))

        response = post_turn(signed_in, {"messages": [ask("x" * 5000)]})

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/event-stream")
        assert types(frames(response)) == ["text", "usage", "done"]
