"""The admin of the AI gateway (``erplora.com/admin``), as ERPlora's staff use it.

This file: the providers and their keys (ASSISTANT-G15, G16, G59; old SAAS_ASSISTANT-F22). A provider's page has its
keys inline; a key is typed once in a field that never shows it again (the old page painted it whole, F22's gap),
and the list says, for each provider, the end of its active key or why it has none. Saving a key goes through
``assistant.credential.save|delete``. Only staff with the model permissions enter (each refused path has its test).
"""

import pytest
from django.contrib.messages import get_messages
from django.db import connection
from live.models import OutboxEvent

from assistant.models import AIProvider, AIProviderCredential
from assistant.tests.conftest import API_KEY, OTHER_FERNET_KEY, grant

pytestmark = pytest.mark.django_db

PROVIDERS = "/admin/assistant/aiprovider/"
NEW_KEY = "sk-test-1111111111111111111111111111abcd"


@pytest.fixture
def as_ai_admin(client, ai_admin):
    client.force_login(ai_admin)
    return client


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def credential_form(prefix: str = "credentials", rows: list[dict] | None = None, initial: int = 0) -> dict:
    """The inline formset of the keys, as the browser posts it."""
    rows = rows or []
    data = {
        f"{prefix}-TOTAL_FORMS": str(len(rows)),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for index, row in enumerate(rows):
        for name, value in row.items():
            data[f"{prefix}-{index}-{name}"] = value
    return data


def models_form() -> dict:
    return {
        "models-TOTAL_FORMS": "0",
        "models-INITIAL_FORMS": "0",
        "models-MIN_NUM_FORMS": "0",
        "models-MAX_NUM_FORMS": "1000",
    }


def provider_form(**fields) -> dict:
    data = {"slug": "openai", "name": "OpenAI", "kind": "openai", "base_url": "", "is_enabled": "on", "notes": ""}
    data.update(fields)
    return data


def raw_tokens() -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT api_key FROM assistant_aiprovidercredential")
        return [row[0] for row in cursor.fetchall()]


# --- Who enters --------------------------------------------------------------------------------------------


def test_without_a_session_the_providers_ask_to_sign_in(client):
    response = client.get(PROVIDERS)

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


def test_a_member_of_the_staff_without_the_permission_is_refused(client, plain_staff, provider):
    client.force_login(plain_staff)

    assert client.get(PROVIDERS).status_code == 403
    assert client.get(f"{PROVIDERS}{provider.pk}/change/").status_code == 403
    assert client.get(f"{PROVIDERS}add/").status_code == 403


def test_an_account_that_is_not_staff_never_enters(client, make_user):
    customer = grant(make_user("customer@example.com"), "view_aiprovider")
    client.force_login(customer)

    response = client.get(PROVIDERS)

    assert response.status_code == 302
    assert "/admin/login/" in response["Location"]


# --- The list ----------------------------------------------------------------------------------------------


def test_the_list_says_the_state_of_each_provider_key(as_ai_admin, provider, settings):
    anthropic = AIProvider.objects.create(slug="anthropic", name="Anthropic", kind="anthropic")
    gemini = AIProvider.objects.create(slug="gemini", name="Google Gemini", kind="gemini")
    AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    AIProviderCredential.objects.create(provider=gemini, label="default", api_key=NEW_KEY, key_hint="abcd")
    settings.FERNET_KEY_PREVIOUS = settings.FERNET_KEY
    settings.FERNET_KEY = OTHER_FERNET_KEY
    AIProviderCredential.objects.create(provider=anthropic, label="default", api_key=NEW_KEY, key_hint="abcd")
    settings.FERNET_KEY_PREVIOUS = ""  # the OpenAI and Gemini keys no longer open

    page = as_ai_admin.get(PROVIDERS).content.decode()

    assert "OpenAI" in page and "Anthropic" in page and "Google Gemini" in page
    assert "Unreadable: type the key again" in page
    assert "…abcd" in page
    assert API_KEY not in page and NEW_KEY not in page


def test_a_provider_without_a_key_says_so(as_ai_admin, provider):
    assert "No key" in as_ai_admin.get(PROVIDERS).content.decode()


# --- A provider and its keys -------------------------------------------------------------------------------


def test_adding_a_provider_with_its_key_keeps_the_key_encrypted(as_ai_admin, ai_admin):
    response = as_ai_admin.post(
        f"{PROVIDERS}add/",
        {
            **provider_form(),
            **credential_form(rows=[{"label": "default", "new_key": API_KEY, "is_active": "on"}]),
            **models_form(),
        },
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    provider = AIProvider.objects.get(slug="openai")
    credential = provider.credentials.get()
    assert credential.api_key == API_KEY and credential.key_hint == "wxyz"
    assert credential.created_by == ai_admin
    assert all(API_KEY not in token for token in raw_tokens())
    assert OutboxEvent.objects.filter(name="assistant.credential.saved").count() == 1


def test_the_page_of_a_provider_never_shows_its_key(as_ai_admin, provider):
    credential = AIProviderCredential.objects.create(
        provider=provider, label="default", api_key=API_KEY, key_hint="wxyz"
    )

    page = as_ai_admin.get(f"{PROVIDERS}{provider.pk}/change/").content.decode()

    assert API_KEY not in page
    assert raw_tokens()[0] not in page
    assert "…wxyz" in page
    assert credential.label in page


def test_a_new_key_row_without_a_key_is_refused(as_ai_admin):
    """A row the person filled in (a label) without the key; an untouched extra row is ignored, as in any admin."""
    response = as_ai_admin.post(
        f"{PROVIDERS}add/",
        {**provider_form(), **credential_form(rows=[{"label": "main", "new_key": "", "is_active": "on"}]), **models_form()},
    )

    assert response.status_code == 200
    assert "Type the provider&#x27;s key." in response.content.decode()
    assert not AIProvider.objects.exists()


def test_saving_without_typing_a_key_keeps_it(as_ai_admin, provider):
    credential = AIProviderCredential.objects.create(
        provider=provider, label="default", api_key=API_KEY, key_hint="wxyz"
    )

    response = as_ai_admin.post(
        f"{PROVIDERS}{provider.pk}/change/",
        {
            **provider_form(name="OpenAI (EU)"),
            **credential_form(
                rows=[{"id": str(credential.pk), "provider": str(provider.pk), "label": "default", "new_key": "", "is_active": ""}],
                initial=1,
            ),
            **models_form(),
        },
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    credential.refresh_from_db()
    assert (credential.api_key, credential.is_active, credential.rotated_at) == (API_KEY, False, None)


def test_typing_another_key_rotates_it(as_ai_admin, provider):
    credential = AIProviderCredential.objects.create(
        provider=provider, label="default", api_key=API_KEY, key_hint="wxyz"
    )

    response = as_ai_admin.post(
        f"{PROVIDERS}{provider.pk}/change/",
        {
            **provider_form(),
            **credential_form(
                rows=[{"id": str(credential.pk), "provider": str(provider.pk), "label": "default", "new_key": NEW_KEY, "is_active": "on"}],
                initial=1,
            ),
            **models_form(),
        },
    )

    assert response.status_code == 302
    credential.refresh_from_db()
    assert credential.api_key == NEW_KEY and credential.key_hint == "abcd"
    assert credential.rotated_at is not None


def test_deleting_a_key_forgets_it(as_ai_admin, provider):
    credential = AIProviderCredential.objects.create(
        provider=provider, label="default", api_key=API_KEY, key_hint="wxyz"
    )

    response = as_ai_admin.post(
        f"{PROVIDERS}{provider.pk}/change/",
        {
            **provider_form(),
            **credential_form(
                rows=[{"id": str(credential.pk), "provider": str(provider.pk), "label": "default", "new_key": "", "is_active": "on", "DELETE": "on"}],
                initial=1,
            ),
            **models_form(),
        },
    )

    assert response.status_code == 302
    assert not AIProviderCredential.objects.exists()
    assert OutboxEvent.objects.filter(name="assistant.credential.deleted").count() == 1


def test_an_address_where_the_key_would_travel_in_the_clear_is_refused(as_ai_admin):
    response = as_ai_admin.post(
        f"{PROVIDERS}add/",
        {**provider_form(base_url="http://api.example.com/v1"), **credential_form(), **models_form()},
    )

    assert response.status_code == 200
    assert "Use an https address: the provider&#x27;s key travels to it." in response.content.decode()
    assert not AIProvider.objects.exists()


def test_without_the_key_of_the_credentials_a_key_is_refused_on_the_page(as_ai_admin, settings):
    settings.FERNET_KEY = ""

    response = as_ai_admin.post(
        f"{PROVIDERS}add/",
        {**provider_form(), **credential_form(rows=[{"label": "default", "new_key": API_KEY, "is_active": "on"}]), **models_form()},
    )

    assert response.status_code == 200
    assert "The key of the credentials is not configured" in response.content.decode()
    assert not AIProviderCredential.objects.exists()


def test_a_member_who_may_only_look_sees_no_key_field(client, make_user, provider):
    viewer = grant(
        make_user("viewer@erplora.com", is_staff=True), "view_aiprovider", "view_aiprovidercredential", "view_aimodel"
    )
    AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    client.force_login(viewer)

    page = client.get(f"{PROVIDERS}{provider.pk}/change/").content.decode()

    assert 'name="credentials-0-new_key"' not in page
    assert "…wxyz" in page and API_KEY not in page


def test_the_admin_speaks_spanish_to_a_spanish_member(client, ai_admin, provider):
    ai_admin.language = "es"
    ai_admin.save(update_fields=["language"])
    client.force_login(ai_admin)

    page = client.get(PROVIDERS, HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Proveedores de IA" in page
    assert "Sin clave" in page
