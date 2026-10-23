"""The factory of clients (``assistant.providers.factory``, ASSISTANT-G35): the API of a provider picks its client;
an unknown API or a missing key is a provider that cannot answer, never a crash."""

import pytest

from assistant.providers.anthropic import AnthropicProvider
from assistant.providers.base import ProviderUnavailable
from assistant.providers.deepseek import DeepSeekProvider
from assistant.providers.factory import CLIENTS, get_provider
from assistant.providers.gemini import GeminiProvider
from assistant.providers.openai import OpenAIProvider


@pytest.mark.parametrize(
    ("kind", "client"),
    [("openai", OpenAIProvider), ("anthropic", AnthropicProvider), ("gemini", GeminiProvider), ("deepseek", DeepSeekProvider)],
)
def test_each_api_gets_its_client(kind, client):
    provider = get_provider(kind=kind, api_key="k", base_url="https://example.com/")

    assert type(provider) is client
    assert provider.base_url == "https://example.com"


def test_the_clients_are_the_four_apis_of_a_provider():
    from assistant.models import AIProvider

    assert set(CLIENTS) == set(AIProvider.Kind.values)


def test_an_unknown_api_cannot_answer():
    with pytest.raises(ProviderUnavailable):
        get_provider(kind="mystery", api_key="k", base_url="https://example.com")


def test_a_provider_without_a_key_cannot_answer():
    with pytest.raises(ProviderUnavailable):
        get_provider(kind="openai", api_key="", base_url="https://example.com")


def test_a_client_never_shows_its_key():
    provider = get_provider(kind="openai", api_key="sk-secret-key", base_url="https://example.com")

    assert "sk-secret-key" not in repr(provider)
