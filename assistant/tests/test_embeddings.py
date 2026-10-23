"""ASSISTANT-F20 (ASSISTANT-G54, G09, G30) · Compute the fingerprints of some texts for the Hub's index: the Hub
never runs a model, so it sends ``texts`` (1 to 256) to ``POST /internal/assistant/embeddings`` and gets a vector per
text, in the same order. erplora.com uses the key of the services' provider (``ASSISTANT_SERVICE_PROVIDER``, of
OpenAI's API) and always its model (``EMBEDDING_MODEL``): the Hub no longer chooses it (the old product let the
caller pick any model, of very different price, SAAS_ASSISTANT-F17 «parcial»). It does not look at the allowance
(indexing is not a message) and adds the tokens and their cost to the business's month. Cases of the old
``test_embeddings_endpoint.py``; OpenAI is the local fake.
"""

from decimal import Decimal

import pytest
from django.test import Client

from assistant import queries
from assistant.media import EMBEDDING_MODEL
from assistant.models import AssistantUsage
from assistant.tests.conftest import API_KEY
from assistant.tests.doors import door, error_code

EMBEDDINGS = "/internal/assistant/embeddings"

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


def vectors_answer(*vectors, tokens: int = 12) -> dict:
    data = [{"object": "embedding", "index": index, "embedding": vector} for index, vector in enumerate(vectors)]
    return {"object": "list", "data": list(reversed(data)), "model": EMBEDDING_MODEL, "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}


def test_each_text_gets_its_vector_in_order(client, internal, business, answering, fake_provider):
    fake_provider.reply("POST", "/v1/embeddings", json=vectors_answer([0.1, 0.2], [0.3, 0.4]))

    response = door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["Ventas del día", "Citas de mañana"]})

    assert response.status_code == 200
    assert response.json() == {"embeddings": [[0.1, 0.2], [0.3, 0.4]], "model": EMBEDDING_MODEL}
    [asked] = fake_provider.requests
    assert asked.body == {"model": EMBEDDING_MODEL, "input": ["Ventas del día", "Citas de mañana"]}
    assert asked.headers["authorization"] == f"Bearer {API_KEY}"


def test_the_hub_cannot_choose_another_model(client, internal, business, answering, fake_provider):
    fake_provider.reply("POST", "/v1/embeddings", json=vectors_answer([0.1]))

    door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"], "model": "text-embedding-3-large"})

    assert fake_provider.requests[0].body["model"] == EMBEDDING_MODEL


def test_the_tokens_and_their_cost_go_to_the_businesss_month(client, internal, business, answering, fake_provider):
    fake_provider.reply("POST", "/v1/embeddings", json=vectors_answer([0.1], tokens=500_000))

    door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]})

    row = AssistantUsage.objects.get(hub=business)
    assert (row.messages, row.tokens_embedding, row.cost_usd) == (0, 500_000, Decimal("0.01"))


def test_a_business_with_its_messages_spent_still_indexes(client, internal, business, answering, fake_provider):
    from django.utils import timezone

    AssistantUsage.objects.create(hub=business, month=queries.month_of(timezone.now()), messages=30)
    fake_provider.reply("POST", "/v1/embeddings", json=vectors_answer([0.1]))

    assert door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]}).status_code == 200


@pytest.mark.parametrize("texts", [[], ["x"] * 257, [1, 2], "not a list", [""]])
def test_texts_that_are_not_1_to_256_strings_are_refused(client, internal, business, answering, fake_provider, texts):
    response = door(client, EMBEDDINGS, {"hub": business.slug, "texts": texts})

    assert (response.status_code, error_code(response)) == (422, "invalid_payload")
    assert fake_provider.requests == []


def test_without_the_services_provider_it_is_503(client, internal, business, answering, fake_provider, settings):
    settings.ASSISTANT_SERVICE_PROVIDER = "nobody"

    response = door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]})

    assert (response.status_code, error_code(response)) == (503, "assistant.provider_not_configured")


def test_a_provider_turned_off_or_without_a_key_is_503(client, internal, business, answering, fake_provider):
    from assistant.models import AIProviderCredential

    AIProviderCredential.objects.all().delete()

    response = door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]})

    assert (response.status_code, error_code(response)) == (503, "assistant.provider_not_configured")


def test_a_provider_of_another_api_cannot_compute_them(client, internal, business, answering, fake_provider):
    answering.provider.kind = "anthropic"
    answering.provider.save(update_fields=["kind"])

    response = door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]})

    assert (response.status_code, error_code(response)) == (503, "assistant.provider_not_configured")


@pytest.mark.parametrize(("status", "code", "retriable"), [(400, "assistant.provider_rejected", False), (503, "assistant.provider_unavailable", True)])
def test_a_failure_of_the_provider_is_a_502_with_its_code_never_the_key(client, internal, business, answering, fake_provider, status, code, retriable):
    fake_provider.reply("POST", "/v1/embeddings", status=status, json={"error": {"message": f"bad key {API_KEY}"}})

    response = door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]})

    assert response.status_code == 502
    assert (error_code(response), response.json()["error"]["retriable"]) == (code, retriable)
    assert API_KEY not in response.content.decode()


def test_the_embeddings_have_their_own_budget(client, internal, business, answering, fake_provider, settings):
    settings.ASSISTANT_EMBED_RATELIMIT = "1/h"
    fake_provider.reply("POST", "/v1/embeddings", json=vectors_answer([0.1]), always=True)
    door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]})

    assert error_code(door(client, EMBEDDINGS, {"hub": business.slug, "texts": ["x"]})) == "rate_limited"
    assert door(client, "/internal/assistant/usage", {"hub": business.slug}).status_code == 200
