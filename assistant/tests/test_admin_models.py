"""Choosing a provider's models in the admin (ASSISTANT-G24, G14): «Choose models from the provider» asks the
provider's API (here ``fake_provider``, a real HTTP server on ``127.0.0.1``) for its chat models; the staff tick the
ones to keep and the provider's page lists them, with their prices to correct by hand."""

import pytest
from django.contrib.messages import get_messages

from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy
from assistant.tests.conftest import API_KEY, grant

pytestmark = pytest.mark.django_db


@pytest.fixture
def listed_provider(fake_provider):
    """An OpenAI-compatible provider at the fake server, with a key, whose API lists two chat models and one that is not."""
    provider = AIProvider.objects.create(slug="local", name="Local", kind="openai", base_url=f"{fake_provider.url}/v1")
    AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    fake_provider.reply(
        "GET",
        "/v1/models",
        always=True,
        json={"data": [{"id": "gpt-e2e-large"}, {"id": "gpt-e2e-mini"}, {"id": "text-embedding-e2e"}]},
    )
    return provider


def choose_url(provider) -> str:
    return f"/admin/assistant/aiprovider/{provider.pk}/models/"


@pytest.fixture
def as_ai_admin(client, ai_admin):
    client.force_login(ai_admin)
    return client


def test_the_page_lists_the_chat_models_of_the_provider_and_ticks_the_ones_it_has(as_ai_admin, listed_provider, fake_provider):
    AIModel.objects.create(provider=listed_provider, model_id="gpt-e2e-mini", display_name="Mini")

    response = as_ai_admin.get(choose_url(listed_provider))

    page = response.content.decode()
    assert response.status_code == 200
    assert 'value="gpt-e2e-large"' in page and 'value="gpt-e2e-mini"' in page
    assert "text-embedding-e2e" not in page
    assert 'value="gpt-e2e-mini" checked' in page
    assert 'value="gpt-e2e-large" checked' not in page
    assert fake_provider.requests[0].headers["authorization"] == f"Bearer {API_KEY}"
    assert API_KEY not in page


def test_saving_the_choice_keeps_exactly_the_ticked_models(as_ai_admin, listed_provider):
    AIModel.objects.create(provider=listed_provider, model_id="gpt-old", display_name="Old")

    response = as_ai_admin.post(
        choose_url(listed_provider),
        {
            "listed": ["gpt-e2e-large", "gpt-e2e-mini"],
            "name:gpt-e2e-large": "gpt-e2e-large",
            "context:gpt-e2e-large": "0",
            "name:gpt-e2e-mini": "gpt-e2e-mini",
            "context:gpt-e2e-mini": "0",
            "models": ["gpt-e2e-large"],
        },
    )

    assert response.status_code == 302
    assert response["Location"] == f"/admin/assistant/aiprovider/{listed_provider.pk}/change/"
    assert list(AIModel.objects.filter(provider=listed_provider).values_list("model_id", flat=True)) == ["gpt-e2e-large"]
    [message] = [str(m) for m in get_messages(response.wsgi_request)]
    assert message == "Local: 1 new, 0 kept, 1 removed, 0 in use by the policy."


def test_a_model_the_policy_uses_is_kept_and_said_so(as_ai_admin, listed_provider):
    used = AIModel.objects.create(provider=listed_provider, model_id="gpt-old", display_name="Old")
    policy = AIRoutingPolicy.solo()
    policy.active_model = used
    policy.save()

    response = as_ai_admin.post(choose_url(listed_provider), {"listed": [], "models": []})

    assert AIModel.objects.filter(pk=used.pk).exists()
    assert [str(m) for m in get_messages(response.wsgi_request)] == ["Local: 0 new, 0 kept, 0 removed, 1 in use by the policy."]


def test_a_provider_without_a_key_says_to_add_one(as_ai_admin, fake_provider):
    provider = AIProvider.objects.create(slug="nokey", name="No key", kind="openai", base_url=f"{fake_provider.url}/v1")

    page = as_ai_admin.get(choose_url(provider)).content.decode()

    assert "This provider has no active key: add one on its page and try again." in page
    assert fake_provider.requests == []


def test_a_refused_key_shows_the_reason_of_the_provider(as_ai_admin, fake_provider):
    provider = AIProvider.objects.create(slug="refused", name="Refused", kind="openai", base_url=f"{fake_provider.url}/v2")
    AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    fake_provider.reply("GET", "/v2/models", status=401, json={"error": {"message": "Invalid key"}})

    page = as_ai_admin.get(choose_url(provider)).content.decode()

    assert "The provider did not give its models: openai: Invalid key" in page


def test_the_page_of_the_provider_offers_to_choose_its_models_and_lists_them(as_ai_admin, listed_provider):
    AIModel.objects.create(provider=listed_provider, model_id="gpt-e2e-mini", display_name="Mini")

    page = as_ai_admin.get(f"/admin/assistant/aiprovider/{listed_provider.pk}/change/").content.decode()

    assert choose_url(listed_provider) in page
    assert "Choose models from the provider" in page
    assert 'value="gpt-e2e-mini"' in page


def test_the_models_have_their_own_list(as_ai_admin, listed_provider):
    AIModel.objects.create(provider=listed_provider, model_id="gpt-e2e-mini", display_name="Mini")

    page = as_ai_admin.get("/admin/assistant/aimodel/").content.decode()

    assert "Mini" in page and "gpt-e2e-mini" in page


def test_without_a_session_the_page_asks_to_sign_in(client, listed_provider):
    response = client.get(choose_url(listed_provider))

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


@pytest.mark.parametrize("held", [(), ("view_aiprovider",), ("view_aiprovider", "add_aimodel")])
def test_a_member_of_the_staff_without_the_permissions_is_refused(client, make_user, listed_provider, fake_provider, held):
    member = grant(make_user("member@erplora.com", is_staff=True), *held)
    client.force_login(member)

    assert client.get(choose_url(listed_provider)).status_code == 403
    assert client.post(choose_url(listed_provider), {"listed": ["gpt-e2e-large"], "models": ["gpt-e2e-large"]}).status_code == 403
    assert not AIModel.objects.exists()
    assert fake_provider.requests == []


def test_an_account_that_is_not_staff_never_enters(client, make_user, listed_provider):
    customer = grant(make_user("customer@example.com"), "view_aiprovider", "add_aimodel", "delete_aimodel")
    client.force_login(customer)

    response = client.get(choose_url(listed_provider))

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


def test_a_provider_that_lists_no_chat_model_says_so(as_ai_admin, fake_provider):
    provider = AIProvider.objects.create(slug="empty", name="Empty", kind="openai", base_url=f"{fake_provider.url}/v3")
    AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    fake_provider.reply("GET", "/v3/models", json={"data": [{"id": "text-embedding-3-small"}]})

    page = as_ai_admin.get(choose_url(provider)).content.decode()

    assert "The provider listed no chat models." in page
    assert 'name="models"' not in page


def test_an_unknown_provider_is_a_404(as_ai_admin):
    assert as_ai_admin.get("/admin/assistant/aiprovider/0190b3a0-0000-7000-8000-000000000000/models/").status_code == 404


def test_an_address_that_names_no_provider_is_a_404(as_ai_admin):
    assert as_ai_admin.get("/admin/assistant/aiprovider/not-an-id/models/").status_code == 404
    assert as_ai_admin.post("/admin/assistant/aiprovider/not-an-id/models/", {"listed": [], "models": []}).status_code == 404
