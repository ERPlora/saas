"""The rows of the AI gateway (ASSISTANT-G25 provider, G26 credential, G24 model, G27 policy).

- A provider is one of the four APIs our clients speak (``kind``), with its own address only over https (the key
  travels to it); a local address is for the tests and a provider of our own on the same machine.
- A credential never shows its key: not in its name, not in its ``repr``; only the last four characters, kept
  apart in the clear as its hint, which is how the staff recognise it.
"""

import pytest
from django.core.exceptions import ValidationError

from assistant.models import AIProvider, AIProviderCredential
from assistant.tests.conftest import API_KEY

pytestmark = pytest.mark.django_db


# --- AIProvider (G25) ------------------------------------------------------------------------------------


def test_the_kinds_are_the_four_apis_the_gateway_speaks():
    assert set(AIProvider.Kind.values) == {"openai", "anthropic", "gemini", "deepseek"}


@pytest.mark.parametrize(
    "base_url",
    ["", "https://api.openai.com/v1", "https://proxy.example.com/openai", "http://127.0.0.1:8949/v1", "http://localhost:9000"],
)
def test_an_address_over_https_or_on_this_machine_is_accepted(base_url):
    AIProvider(slug="custom", name="Custom", kind="openai", base_url=base_url).full_clean()


@pytest.mark.parametrize("base_url", ["http://api.openai.com/v1", "http://10.0.0.5/v1", "ftp://example.com"])
def test_an_address_where_the_key_would_travel_in_the_clear_is_refused(base_url):
    with pytest.raises(ValidationError) as refused:
        AIProvider(slug="custom", name="Custom", kind="openai", base_url=base_url).full_clean()

    assert "base_url" in refused.value.message_dict


def test_the_default_address_comes_from_the_kind():
    assert AIProvider(kind="openai").api_base == "https://api.openai.com/v1"
    assert AIProvider(kind="anthropic").api_base == "https://api.anthropic.com"
    assert AIProvider(kind="gemini").api_base == "https://generativelanguage.googleapis.com"
    assert AIProvider(kind="deepseek").api_base == "https://api.deepseek.com"
    assert AIProvider(kind="openai", base_url="https://proxy.example.com/v1/").api_base == "https://proxy.example.com/v1"


def test_a_provider_is_named_by_its_name():
    assert str(AIProvider(slug="openai", name="OpenAI", kind="openai")) == "OpenAI"


# --- AIProviderCredential (G26) ------------------------------------------------------------------------


def test_a_credential_never_shows_its_key(provider):
    credential = AIProviderCredential.objects.create(
        provider=provider, label="default", api_key=API_KEY, key_hint=API_KEY[-4:]
    )

    for shown in (str(credential), repr(credential)):
        assert API_KEY not in shown
        assert API_KEY[:-4] not in shown
    assert str(credential) == "openai:default (…wxyz)"


def test_the_masked_key_says_whether_it_can_be_used(provider):
    credential = AIProviderCredential(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    assert credential.masked_key == "…wxyz"
    assert credential.is_readable is True

    unreadable = AIProviderCredential(provider=provider, label="default", api_key="", key_hint="wxyz")
    assert unreadable.is_readable is False


def test_two_keys_of_a_provider_cannot_share_a_label(provider):
    AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")

    with pytest.raises(ValidationError):
        AIProviderCredential(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz").validate_constraints()
