"""ASSISTANT-F27 · The panel's assistant searches ERPlora's documentation (``assistant.docs.search``; plan
2026-10-30-asistente-saas §5): a tool of every account (``assistant.ask``), for how-to questions.

The question is embedded by the services' provider (cached a day by the hash of the question as it was asked, spaces
and case aside) and the excerpts of ``index_docs`` come back nearest first by the cosine of their fingerprints, in
the person's language; when fewer than three of them are close (a distance under ``CLOSE``), the English ones join.
At most 12, whatever is asked; each with where it comes from, to cite it. Without the provider: 409
``assistant.provider_not_configured`` (the model says the documentation is not available). The provider is the
local fake.
"""

import json

import pytest
from django.core.cache import cache
from django.utils import timezone
from live.assistant import tool_name
from live.errors import OperationError, PermissionDenied
from live.operations import AI, get

from assistant import queries
from assistant.media import EMBEDDING_MODEL
from assistant.models import EMBEDDING_DIMENSIONS, DocChunk, content_hash
from assistant.schemas import DocsSearchIn
from assistant.tests.conftest import (  # noqa: F401 - the gateway's fixtures
    answering,
    fake_provider,
    openai_answer,
    openai_tool_call,
    provider,
)
from assistant.tests.doors import frames
from base import assistant
from hubs.tests.conftest import ctx_for, make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

EMBEDDINGS = "/v1/embeddings"
COMPLETIONS = "/v1/chat/completions"


def axis(*weights: float) -> list[float]:
    """A fingerprint pointing along the first axes with ``weights`` (the rest near zero)."""
    vector = [0.0001] * EMBEDDING_DIMENSIONS
    for index, weight in enumerate(weights):
        vector[index] = weight
    return vector


#: The question points along the first axis; an excerpt along it is the same meaning (distance 0).
QUESTION = axis(1.0)
SAME = axis(1.0)
NEAR = axis(1.0, 0.5)  # distance ≈ 0.106
FAR = axis(0.0, 1.0)  # distance ≈ 1


def answer_with(vector):
    def answer(body):
        data = [{"object": "embedding", "index": index, "embedding": vector} for index in range(len(body["input"]))]
        return {"object": "list", "data": data, "model": EMBEDDING_MODEL, "usage": {"prompt_tokens": 5, "total_tokens": 5}}

    return answer


@pytest.fixture(autouse=True)
def empty_cache():
    cache.clear()


@pytest.fixture
def embedder(answering, fake_provider):
    fake_provider.reply("POST", EMBEDDINGS, always=True, answer=answer_with(QUESTION))
    return fake_provider


@pytest.fixture
def account(make_user, plans):
    return make_user("lena@example.com", first_name="Lena", language="es")


def excerpt(lang: str, text: str, embedding, *, source="help", path=None, heading="FAQ") -> DocChunk:
    path = path or f"docs/{lang}/help/05-faq.md"
    return DocChunk.objects.create(
        source=source,
        path=path,
        lang=lang,
        heading=heading,
        text=text,
        content_hash=content_hash(source, path, lang, heading, text),
        embedding=embedding,
        indexed_at=timezone.now(),
    )


def search(account, query="¿Cómo invito a alguien a mi negocio?", language="es", **extra):
    return queries.docs_search(ctx_for(account, language), DocsSearchIn(query=query, **extra)).results


def texts(results) -> list[str]:
    return [result.text for result in results]


def embedding_calls(fake_provider) -> list:
    return [seen for seen in fake_provider.requests if seen.path == EMBEDDINGS]


class TestTheSearch:
    def test_the_nearest_excerpts_come_first_with_where_they_come_from(self, account, embedder):
        excerpt("es", "Invita desde la ficha del negocio.", NEAR, heading="Negocios > Invitar")
        excerpt("es", "Pulsa «Invitar».", SAME, source="workbook", path="hubs/WORKBOOK.md", heading="Negocios > HUBS-F05")
        excerpt("es", "Cambia la contraseña en Cuenta.", FAR)

        results = search(account)

        assert texts(results) == ["Pulsa «Invitar».", "Invita desde la ficha del negocio.", "Cambia la contraseña en Cuenta."]
        first = results[0]
        assert (first.source, first.path, first.heading, first.lang) == ("workbook", "hubs/WORKBOOK.md", "Negocios > HUBS-F05", "es")
        assert first.score == pytest.approx(1.0, abs=1e-3)
        assert results[1].score == pytest.approx(0.894, abs=1e-3)
        assert results[2].score < 0.01

    def test_the_question_is_embedded_as_asked(self, account, embedder):
        search(account, query="  ¿Cómo invito a alguien?  ")

        [call] = embedding_calls(embedder)
        assert call.body == {"model": EMBEDDING_MODEL, "input": ["¿Cómo invito a alguien?"]}

    def test_only_the_persons_language_while_enough_of_it_is_close(self, account, embedder):
        for number in range(3):
            excerpt("es", f"Respuesta {number}.", NEAR, heading=f"FAQ {number}")
        excerpt("en", "Answer.", SAME)

        results = search(account)

        assert {result.lang for result in results} == {"es"}
        assert len(results) == 3

    def test_with_fewer_than_three_close_ones_the_english_join(self, account, embedder):
        excerpt("es", "Respuesta cercana.", NEAR)
        excerpt("es", "Respuesta lejana.", FAR, heading="Otra")
        excerpt("en", "The answer.", SAME)
        excerpt("en", "Another answer.", NEAR, heading="Other")

        results = search(account)

        assert texts(results) == ["The answer.", "Respuesta cercana.", "Another answer.", "Respuesta lejana."]
        assert [result.lang for result in results] == ["en", "es", "en", "es"]

    def test_english_is_read_in_english_alone(self, account, embedder):
        excerpt("es", "Respuesta.", SAME)
        excerpt("en", "Answer.", NEAR)

        assert texts(search(account, query="How do I invite someone?", language="en")) == ["Answer."]

    def test_a_language_without_documentation_reads_english(self, account, embedder):
        excerpt("es", "Respuesta.", SAME)
        excerpt("en", "Answer.", NEAR)

        assert texts(search(account, query="Comment inviter ?", language="fr")) == ["Answer."]

    def test_eight_excerpts_unless_asked_and_never_more_than_twelve(self, account, embedder):
        for number in range(20):
            excerpt("es", f"Respuesta {number}.", NEAR, heading=f"FAQ {number}")

        assert len(search(account)) == 8
        assert len(search(account, limit=3)) == 3
        assert len(search(account, limit=50)) == 12

    def test_an_empty_index_finds_nothing(self, account, embedder):
        assert search(account) == []


class TestTheQuestionsFingerprint:
    def test_the_same_question_is_embedded_once_a_day(self, account, embedder, settings):
        excerpt("es", "Respuesta.", SAME)

        search(account, query="¿Cómo invito a alguien?")
        again = search(account, query="  ¿cómo   INVITO a alguien?")

        assert len(embedding_calls(embedder)) == 1
        assert texts(again) == ["Respuesta."]

    def test_another_question_is_embedded_again(self, account, embedder):
        search(account, query="¿Cómo invito a alguien?")
        search(account, query="¿Cuánto cuesta Starter?")

        assert len(embedding_calls(embedder)) == 2

    def test_the_wait_for_it_is_short_inside_the_read_transaction(self, account, embedder, monkeypatch):
        """Aurora ends a transaction left idle 30 s: the search waits 10 s at most, never the 60 s of the index."""
        from assistant import media

        waits = []
        embed = media.embed

        async def spy(service, texts, **options):
            waits.append(options.get("timeout"))
            return await embed(service, texts, **options)

        monkeypatch.setattr(media, "embed", spy)

        search(account)

        assert [wait.read for wait in waits] == [10.0]
        assert waits[0].connect <= 5.0

    def test_it_is_kept_for_a_day(self, account, embedder, monkeypatch):
        kept = {}
        monkeypatch.setattr(cache, "set", lambda key, value, timeout=None: kept.update({key: timeout}))

        search(account)

        assert list(kept.values()) == [60 * 60 * 24]


class TestWhatItRefuses:
    def test_without_the_services_provider_a_409(self, account, provider):
        with pytest.raises(OperationError) as refused:
            search(account)

        assert (refused.value.status, refused.value.code) == (409, "assistant.provider_not_configured")
        assert "documentación" in refused.value.message

    def test_a_provider_that_fails_says_the_documentation_cannot_be_read_now(self, account, answering, fake_provider):
        fake_provider.reply("POST", EMBEDDINGS, always=True, status=503, json={"error": {"message": "down"}})

        with pytest.raises(OperationError) as failed:
            search(account)

        assert (failed.value.status, failed.value.code) == (503, "assistant.provider_unavailable")

    def test_without_the_permission_to_ask_nothing(self, account, embedder):
        from dataclasses import replace

        with pytest.raises(PermissionDenied):
            queries.docs_search(replace(ctx_for(account), permissions=frozenset()), DocsSearchIn(query="x"))

    @pytest.mark.parametrize("query", ["", "   ", "x" * 501])
    def test_a_question_that_is_empty_or_too_long_is_refused(self, query):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DocsSearchIn(query=query)


class TestTheTool:
    def test_it_is_a_tool_of_the_assistant_with_its_description(self):
        op = get("assistant.docs.search")

        assert isinstance(op.ai_spec(), AI)
        assert op.ai_spec().description.startswith("Searches ERPlora's help, the documentation of its apps and the plans")
        assert (op.kind, op.permission) == ("query", "assistant.ask")

    @pytest.mark.parametrize(
        "language, asked",
        [
            # A how-to question shares no word with the tool's own: without being always at hand, it would be left out.
            ("es", "¿Cómo invito a alguien a mi negocio?"),
            ("en", "change my billing address and cancel my plan and see the invoices of my businesses"),
        ],
    )
    def test_every_account_is_offered_it_whatever_it_asks(self, account, language, asked):
        tools = assistant.catalog(ctx_for(account, language))
        offered = [op.name for op in assistant.relevant(tools, [asked], language)]

        assert "assistant.docs.search" in tools
        assert offered[:2] == ["hubs.business.list", "assistant.docs.search"]

    def test_the_instructions_name_it_as_the_gateway_calls_it(self, account):
        text = assistant.instructions(language="en", account="Lena", screens={}, docs=True)

        assert f"`{tool_name('assistant.docs.search')}`" in text
        assert tool_name("assistant.docs.search") == "assistant__docs__search"

    def test_the_model_reads_the_excerpts_through_the_panels_turn(self, client, account, embedder):
        excerpt("es", "Invita desde la ficha del negocio.", SAME, heading="Negocios > Invitar")
        embedder.reply("POST", COMPLETIONS, sse=openai_tool_call("assistant__docs__search", '{"query": "¿Cómo invito?"}'))
        embedder.reply("POST", COMPLETIONS, sse=openai_answer("Desde la ficha del negocio."))
        client.force_login(account)
        question = {"role": "user", "content": "¿Cómo invito a alguien?"}

        first = frames(post_turn(client, {"messages": [question]}))
        done = first[-1]
        model_asked = [seen.body for seen in embedder.requests if seen.path == COMPLETIONS][0]
        second = frames(
            post_turn(
                client,
                {"messages": [question, *done["append"]], "pending": done["pending"], "continuation": done["continuation"]},
            )
        )

        assert "assistant__docs__search" in [tool["function"]["name"] for tool in model_asked["tools"]]
        assert "`assistant__docs__search`" in model_asked["messages"][0]["content"]
        executed = second[0]
        assert (executed["type"], executed["name"], executed["outcome"]) == ("executed", "assistant.docs.search", "ok")
        # Done on no screen of the panel: its receipt names the help, never «Cuenta».
        assert (executed["screen"], executed["app_name"]) == ("", "Ayuda")
        answered = [seen.body for seen in embedder.requests if seen.path == COMPLETIONS][1]["messages"]
        assert any(message["role"] == "tool" and "Invita desde la ficha del negocio." in message["content"] for message in answered)


def post_turn(client, body: dict):
    return client.post("/api/assistant/turn", json.dumps(body), content_type="application/json", HTTP_HOST="localhost:8001")
