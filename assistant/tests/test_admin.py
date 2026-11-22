"""The admin of the AI gateway (``erplora.com/admin``), as ERPlora's staff use it.

This file: the providers. A provider's key lives in the environment, never in the admin: a provider's page names the
variable it reads and, like the list, says whether that variable holds a key, without showing any part of it. There is
no field to type, change or rotate a key. Only staff with the model permissions enter (each refused path has its test).
"""

import pytest

from assistant.models import KEY_VARIABLES, AIProvider
from assistant.tests.conftest import API_KEY, grant

pytestmark = pytest.mark.django_db

PROVIDERS = "/admin/assistant/aiprovider/"


@pytest.fixture
def as_ai_admin(client, ai_admin):
    client.force_login(ai_admin)
    return client


def models_form() -> dict:
    return {
        "models-TOTAL_FORMS": "0",
        "models-INITIAL_FORMS": "0",
        "models-MIN_NUM_FORMS": "0",
        "models-MAX_NUM_FORMS": "1000",
    }


def provider_form(**fields) -> dict:
    data = {
        "slug": "openai",
        "name": "OpenAI",
        "kind": "openai",
        "base_url": "",
        "key_variable": "OPENAI_API_KEY",
        "is_enabled": "on",
        "notes": "",
    }
    data.update(fields)
    return data


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


def test_the_list_says_which_provider_has_its_key_and_never_a_part_of_it(as_ai_admin, provider, settings):
    AIProvider.objects.create(slug="anthropic", name="Anthropic", kind="anthropic", key_variable="ANTHROPIC_API_KEY")
    settings.OPENAI_API_KEY = API_KEY

    page = as_ai_admin.get(PROVIDERS).content.decode()

    assert "OpenAI" in page and "Anthropic" in page
    assert "OPENAI_API_KEY" in page and "ANTHROPIC_API_KEY" in page
    assert page.count("In the environment") == 1 and page.count("No key") == 1
    assert API_KEY not in page and API_KEY[-4:] not in page


def test_a_provider_without_a_key_says_so(as_ai_admin, provider):
    assert "No key" in as_ai_admin.get(PROVIDERS).content.decode()


# --- A provider ------------------------------------------------------------------------------------------


def test_adding_a_provider_names_the_variable_of_its_key(as_ai_admin):
    response = as_ai_admin.post(
        f"{PROVIDERS}add/",
        {**provider_form(slug="qwen", name="Qwen", key_variable="DASHSCOPE_API_KEY", base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"), **models_form()},
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    assert AIProvider.objects.get(slug="qwen").key_variable == "DASHSCOPE_API_KEY"


def test_a_provider_without_the_variable_of_its_key_is_refused(as_ai_admin):
    response = as_ai_admin.post(f"{PROVIDERS}add/", {**provider_form(key_variable=""), **models_form()})

    assert response.status_code == 200
    assert "This field is required." in response.content.decode()
    assert not AIProvider.objects.exists()


@pytest.mark.parametrize("variable", ["SECRET_KEY", "FERNET_KEY", "DATABASE_URL"])
def test_a_variable_that_is_no_ai_key_is_refused(as_ai_admin, variable):
    response = as_ai_admin.post(f"{PROVIDERS}add/", {**provider_form(key_variable=variable), **models_form()})

    assert response.status_code == 200
    assert "Select a valid choice." in response.content.decode()
    assert not AIProvider.objects.exists()


def test_the_page_of_a_provider_offers_the_ai_keys_and_no_field_to_type_one(as_ai_admin, provider, settings):
    settings.OPENAI_API_KEY = API_KEY

    page = as_ai_admin.get(f"{PROVIDERS}{provider.pk}/change/").content.decode()

    for variable in KEY_VARIABLES:
        assert f'<option value="{variable}"' in page
    assert "In the environment" in page
    assert API_KEY not in page and API_KEY[-4:] not in page
    assert "new_key" not in page and 'type="password"' not in page and "credentials-" not in page


def test_an_address_where_the_key_would_travel_in_the_clear_is_refused(as_ai_admin):
    response = as_ai_admin.post(f"{PROVIDERS}add/", {**provider_form(base_url="http://api.example.com/v1"), **models_form()})

    assert response.status_code == 200
    assert "Use an https address: the provider&#x27;s key travels to it." in response.content.decode()
    assert not AIProvider.objects.exists()


def test_a_member_who_may_only_look_sees_whether_it_has_a_key(client, make_user, provider, settings):
    viewer = grant(make_user("viewer@erplora.com", is_staff=True), "view_aiprovider", "view_aimodel")
    settings.OPENAI_API_KEY = API_KEY
    client.force_login(viewer)

    page = client.get(f"{PROVIDERS}{provider.pk}/change/").content.decode()

    assert "In the environment" in page and "OPENAI_API_KEY" in page
    assert API_KEY not in page


def test_the_admin_speaks_spanish_to_a_spanish_member(client, ai_admin, provider):
    ai_admin.language = "es"
    ai_admin.save(update_fields=["language"])
    client.force_login(ai_admin)

    page = client.get(PROVIDERS, HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Proveedores de IA" in page
    assert "Sin clave" in page
