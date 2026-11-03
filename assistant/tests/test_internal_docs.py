"""ASSISTANT-F28 · The Hub's assistant searches ERPlora's documentation through erplora.com: the Hub keeps no index of
its own, so it sends the person's question to ``POST /internal/assistant/docs/search`` (signed as every ``/internal``
call, the business or the demo in ``hub``) and gets the cited excerpts of the same index the panel's assistant reads
(``assistant.DocChunk``: the public help, the user part of every Hub app's WORKBOOK, the SaaS's WORKBOOKs and the
plans).

erplora.com computes the question's fingerprint with the services' provider (``queries.prepare_questions``, kept a
day) and runs the very search of ``assistant.docs.search``: nearest first, in the ``language`` asked, with the English
excerpts when fewer than three of those are close; at most 12. Its own budget per business
(``ASSISTANT_DOCS_RATELIMIT``). Without the provider: 409 ``assistant.provider_not_configured``; the provider down:
503 ``assistant.provider_unavailable``; an empty index: no excerpt. The provider is the local fake.
"""

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from assistant.media import EMBEDDING_MODEL
from assistant.models import EMBEDDING_DIMENSIONS, DocChunk, content_hash
from assistant.tests.doors import door, error_code

DOCS = "/internal/assistant/docs/search"
EMBEDDINGS = "/v1/embeddings"
QUESTION_TEXT = "¿Cómo abro la caja?"

pytestmark = pytest.mark.django_db


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
def client():
    return Client()


@pytest.fixture
def embedder(answering, fake_provider):
    fake_provider.reply("POST", EMBEDDINGS, always=True, answer=answer_with(QUESTION))
    return fake_provider


def excerpt(lang: str, text: str, embedding, *, source="app_doc", path=None, heading="Caja > Abrir") -> DocChunk:
    path = path or "app_doc:cash"
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


def ask(client, hub, query=QUESTION_TEXT, language="es", **extra):
    return door(client, DOCS, {"hub": hub, "query": query, "language": language, **extra})


def texts(response) -> list[str]:
    return [result["text"] for result in response.json()["results"]]


def embedding_calls(fake_provider) -> list:
    return [seen for seen in fake_provider.requests if seen.path == EMBEDDINGS]


class TestTheSearch:
    def test_a_signed_call_gets_the_nearest_excerpts_with_where_they_come_from(self, client, internal, business, embedder):
        excerpt("es", "Abre la caja desde Caja > Abrir con el efectivo inicial.", SAME)
        excerpt("es", "Cierra la caja al final del día.", NEAR, heading="Caja > Cerrar")
        excerpt("es", "Los clientes se crean desde Clientes.", FAR, path="app_doc:customer", heading="Clientes")

        response = ask(client, business.slug)

        assert response.status_code == 200
        first, second, third = response.json()["results"]
        assert first == {
            "source": "app_doc",
            "path": "app_doc:cash",
            "heading": "Caja > Abrir",
            "text": "Abre la caja desde Caja > Abrir con el efectivo inicial.",
            "score": 1.0,
            "lang": "es",
        }
        assert (second["heading"], third["heading"]) == ("Caja > Cerrar", "Clientes")
        assert first["score"] > second["score"] > third["score"]
        [asked] = embedding_calls(embedder)
        assert asked.body == {"model": EMBEDDING_MODEL, "input": [QUESTION_TEXT]}

    def test_only_the_language_asked_comes_back_when_enough_of_it_is_close(self, client, internal, business, embedder):
        for number in range(3):
            excerpt("en", f"Open the register, step {number}.", SAME, heading=f"Cash > Open {number}")
        excerpt("es", "Abre la caja desde Caja > Abrir.", SAME)

        response = ask(client, business.slug, query="How do I open the register?", language="en")

        assert response.status_code == 200
        assert {result["lang"] for result in response.json()["results"]} == {"en"}
        assert "Abre la caja desde Caja > Abrir." not in texts(response)

    def test_with_few_close_spanish_ones_the_english_ones_join_after_them(self, client, internal, business, embedder):
        excerpt("es", "Abre la caja desde Caja > Abrir.", SAME)
        excerpt("en", "Open the register from Cash > Open.", SAME)
        excerpt("en", "Unrelated English page.", FAR, path="app_doc:customer", heading="Customers")

        response = ask(client, business.slug, language="es")

        assert texts(response)[:2] == ["Abre la caja desde Caja > Abrir.", "Open the register from Cash > Open."]

    def test_at_most_twelve_excerpts_whatever_is_asked(self, client, internal, business, embedder):
        for number in range(14):
            excerpt("es", f"Paso {number} de la caja.", SAME, heading=f"Caja > Paso {number:02d}")

        assert len(ask(client, business.slug, limit=50).json()["results"]) == 12
        assert len(ask(client, business.slug, limit=2).json()["results"]) == 2

    def test_the_question_is_embedded_once_and_kept_a_day(self, client, internal, business, embedder):
        excerpt("es", "Abre la caja desde Caja > Abrir.", SAME)

        ask(client, business.slug)
        ask(client, business.slug, query="  ¿cómo ABRO la caja?  ")

        assert len(embedding_calls(embedder)) == 1

    def test_an_empty_index_answers_no_excerpt(self, client, internal, business, embedder):
        response = ask(client, business.slug)

        assert (response.status_code, response.json()) == (200, {"results": []})

    def test_a_demo_searches_the_same_documentation(self, client, internal, embedder):
        excerpt("es", "Abre la caja desde Caja > Abrir.", SAME)

        response = ask(client, "demo-1a2b3c4d")

        assert response.status_code == 200
        assert texts(response) == ["Abre la caja desde Caja > Abrir."]


class TestTheDoor:
    def test_an_unsigned_call_is_refused_before_the_provider(self, client, internal, business, embedder):
        response = door(client, DOCS, {"hub": business.slug, "query": QUESTION_TEXT, "language": "es"}, signed=False)

        assert (response.status_code, error_code(response)) == (401, "unauthorized")
        assert embedding_calls(embedder) == []

    def test_a_call_signed_with_another_secret_is_refused(self, client, internal, business, embedder):
        payload = {"hub": business.slug, "query": QUESTION_TEXT, "language": "es"}

        response = door(client, DOCS, payload, secret="somebody-else")

        assert (response.status_code, error_code(response)) == (401, "unauthorized")
        assert embedding_calls(embedder) == []

    def test_a_business_the_saas_does_not_know_is_refused(self, client, internal, business, embedder):
        response = ask(client, "nobody-here")

        assert (response.status_code, error_code(response)) == (404, "hub_unknown")
        assert embedding_calls(embedder) == []

    @pytest.mark.parametrize(
        "body",
        [
            {"query": "", "language": "es"},
            {"query": "x" * 501, "language": "es"},
            {"query": "   ", "language": "es"},
            {"query": QUESTION_TEXT, "language": "fr"},
            {"query": QUESTION_TEXT},
            {"query": QUESTION_TEXT, "language": "es", "limit": 0},
        ],
    )
    def test_a_body_out_of_the_contract_is_refused(self, client, internal, business, embedder, body):
        response = door(client, DOCS, {"hub": business.slug, **body})

        assert (response.status_code, error_code(response)) == (422, "invalid_payload")
        assert embedding_calls(embedder) == []

    def test_the_searches_have_their_own_budget(self, client, internal, business, embedder, settings):
        """The same rate as the turn's, so only the budget's own name keeps them apart."""
        settings.ASSISTANT_DOCS_RATELIMIT = settings.ASSISTANT_TURN_RATELIMIT = "1/h"
        assert ask(client, business.slug).status_code == 200

        refused = ask(client, business.slug)

        assert (refused.status_code, error_code(refused)) == (429, "rate_limited")
        assert door(client, "/internal/assistant/usage", {"hub": business.slug}).status_code == 200

    def test_the_budget_is_six_hundred_an_hour_by_default(self):
        from django.conf import settings

        assert settings.ASSISTANT_DOCS_RATELIMIT == "600/h"


class TestWithoutTheProvider:
    def test_without_the_services_provider_it_is_409(self, client, internal, business, answering, fake_provider, settings):
        settings.ASSISTANT_SERVICE_PROVIDER = "nobody"
        excerpt("es", "Abre la caja desde Caja > Abrir.", SAME)

        response = ask(client, business.slug)

        assert (response.status_code, error_code(response)) == (409, "assistant.provider_not_configured")

    def test_the_provider_down_is_503_and_nothing_is_kept(self, client, internal, business, answering, fake_provider):
        fake_provider.reply("POST", EMBEDDINGS, status=503, json={"error": {"message": "down"}}, always=True)
        excerpt("es", "Abre la caja desde Caja > Abrir.", SAME)

        response = ask(client, business.slug)

        assert (response.status_code, error_code(response)) == (503, "assistant.provider_unavailable")
        fake_provider.reply("POST", EMBEDDINGS, always=True, answer=answer_with(QUESTION))
        assert ask(client, business.slug).status_code == 200

    def test_the_refusal_speaks_the_language_asked(self, client, internal, business, answering, fake_provider, settings):
        settings.ASSISTANT_SERVICE_PROVIDER = "nobody"

        spanish = ask(client, business.slug, language="es").json()["error"]["message"]
        english = ask(client, business.slug, language="en").json()["error"]["message"]

        assert spanish != english
        assert english.startswith("ERPlora's documentation cannot be searched now")
