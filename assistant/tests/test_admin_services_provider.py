"""The warning of «AI providers» when the services' provider cannot be used.

The documentation search, the fingerprints of the indexes and the dictation all go through one provider: the one whose
identifier is ``ASSISTANT_SERVICE_PROVIDER`` («openai»), of OpenAI's API, enabled and with its key in the environment.
When it cannot be used, the list of providers says what is missing and where it is put, and says nothing when it works.
"""

import pytest

from assistant.models import AIProvider
from assistant.tests.conftest import API_KEY

pytestmark = pytest.mark.django_db

PROVIDERS = "/admin/assistant/aiprovider/"
BROKEN = "The documentation search and the dictation do not work"


@pytest.fixture
def as_ai_admin(client, ai_admin):
    client.force_login(ai_admin)
    return client


def warning(page: str) -> str:
    """The sentence of the warning, from its start to the end of its line."""
    start = page.index(BROKEN)
    return page[start : page.index("<", start)]


def test_without_the_provider_it_says_to_add_it_with_openais_api(as_ai_admin):
    AIProvider.objects.create(slug="anthropic", name="Anthropic", kind="anthropic", key_variable="ANTHROPIC_API_KEY")

    said = warning(as_ai_admin.get(PROVIDERS).content.decode())

    assert "there is no provider «openai»" in said
    assert "OpenAI&#x27;s API" in said and "OPENAI_API_KEY" in said


def test_it_names_the_provider_the_setting_names(as_ai_admin, provider, openai_key, settings):
    settings.ASSISTANT_SERVICE_PROVIDER = "services"

    assert "there is no provider «services»" in warning(as_ai_admin.get(PROVIDERS).content.decode())


def test_a_provider_of_another_api_is_told_to_speak_openais(as_ai_admin, provider, openai_key):
    provider.kind = AIProvider.Kind.ANTHROPIC
    provider.save(update_fields=["kind"])

    said = warning(as_ai_admin.get(PROVIDERS).content.decode())

    assert "the provider «openai» does not speak OpenAI&#x27;s API" in said


def test_a_provider_turned_off_is_told_to_turn_on(as_ai_admin, provider, openai_key):
    provider.is_enabled = False
    provider.save(update_fields=["is_enabled"])

    said = warning(as_ai_admin.get(PROVIDERS).content.decode())

    assert "the provider «openai» is off" in said


def test_a_provider_without_its_key_names_the_variable_of_the_secret(as_ai_admin, provider):
    said = warning(as_ai_admin.get(PROVIDERS).content.decode())

    assert "the provider «openai» has no key in the environment" in said
    assert "OPENAI_API_KEY" in said and "secret" in said


def test_the_variable_named_is_the_one_the_provider_reads(as_ai_admin, provider):
    provider.key_variable = "DASHSCOPE_API_KEY"
    provider.save(update_fields=["key_variable"])

    said = warning(as_ai_admin.get(PROVIDERS).content.decode())

    assert "DASHSCOPE_API_KEY" in said and "OPENAI_API_KEY" not in said


def test_with_the_provider_ready_nothing_is_said(as_ai_admin, provider, openai_key):
    page = as_ai_admin.get(PROVIDERS).content.decode()

    assert BROKEN not in page
    assert API_KEY not in page


def test_the_warning_never_shows_any_part_of_a_key(as_ai_admin, provider, openai_key):
    provider.is_enabled = False
    provider.save(update_fields=["is_enabled"])

    page = as_ai_admin.get(PROVIDERS).content.decode()

    assert BROKEN in page
    assert API_KEY not in page and API_KEY[-4:] not in page


def test_the_warning_is_said_once_after_an_action_of_the_list(as_ai_admin, provider):
    page = as_ai_admin.post(PROVIDERS, {"action": "delete_selected", "index": "0"}, follow=True).content.decode()

    assert page.count(BROKEN) == 1


def test_the_warning_speaks_spanish_to_a_spanish_member(client, ai_admin, provider):
    ai_admin.language = "es"
    ai_admin.save(update_fields=["language"])
    client.force_login(ai_admin)

    page = client.get(PROVIDERS, HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "La búsqueda en la documentación y el dictado no funcionan" in page
    assert "no tiene clave en el entorno" in page and "OPENAI_API_KEY" in page
