"""The reads of the AI gateway (``assistant.queries``).

This file starts with the connection of a provider (``assistant.provider.connection``, ASSISTANT-G24): its API, its
address and its usable key (the most recent active one that opens), for the listing of its models. The key travels
as a secret: the output's ``repr`` and dump never show it.
"""

import pytest
from live.errors import OperationError, PermissionDenied

from assistant import queries
from assistant.models import AIModel, AIProviderCredential
from assistant.schemas import ProviderRef
from assistant.tests.conftest import API_KEY, OTHER_FERNET_KEY, grant, staff_ctx

pytestmark = pytest.mark.django_db

NEWER_KEY = "sk-test-2222222222222222222222222222newr"


def connection(user, provider):
    return queries.provider_connection(staff_ctx(user), ProviderRef(id=provider.pk))


def test_the_connection_has_the_api_the_address_and_the_newest_active_key(ai_admin, provider):
    AIProviderCredential.objects.create(provider=provider, label="old", api_key=API_KEY, key_hint="wxyz")
    AIProviderCredential.objects.create(provider=provider, label="new", api_key=NEWER_KEY, key_hint="newr")
    AIProviderCredential.objects.create(provider=provider, label="off", api_key="sk-off", key_hint="-off", is_active=False)
    AIModel.objects.create(provider=provider, model_id="gpt-4o", display_name="gpt-4o")

    out = connection(ai_admin, provider)

    assert (out.kind, out.base_url, out.name) == ("openai", "https://api.openai.com/v1", "OpenAI")
    assert out.api_key.get_secret_value() == NEWER_KEY
    assert out.existing == ["gpt-4o"]
    assert NEWER_KEY not in repr(out) and NEWER_KEY not in out.model_dump_json()


def test_an_unreadable_key_is_skipped_for_one_that_opens(ai_admin, provider, settings):
    AIProviderCredential.objects.create(provider=provider, label="readable", api_key=API_KEY, key_hint="wxyz")
    settings.FERNET_KEY_PREVIOUS = settings.FERNET_KEY
    settings.FERNET_KEY = OTHER_FERNET_KEY
    AIProviderCredential.objects.create(provider=provider, label="unreadable", api_key=NEWER_KEY, key_hint="newr")
    settings.FERNET_KEY = settings.FERNET_KEY_PREVIOUS
    settings.FERNET_KEY_PREVIOUS = ""

    assert connection(ai_admin, provider).api_key.get_secret_value() == API_KEY


def test_a_provider_without_a_usable_key_says_so(ai_admin, provider):
    AIProviderCredential.objects.create(provider=provider, label="off", api_key=API_KEY, key_hint="wxyz", is_active=False)

    with pytest.raises(OperationError) as refused:
        connection(ai_admin, provider)

    assert (refused.value.status, refused.value.code) == (409, "assistant.no_key")


def test_reading_a_connection_needs_to_see_providers(make_user, provider):
    member = grant(make_user("member@erplora.com", is_staff=True), "view_aimodel")

    with pytest.raises(PermissionDenied):
        connection(member, provider)
