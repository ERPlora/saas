"""The SaaS's API at /api/: routes bound to operations, OpenAPI, session auth with CSRF, one error envelope.

This module is also the URLconf of its own tests that need a probe API (``ROOT_URLCONF = __name__``
via the ``probe_urls`` fixture).
"""

import json

import pytest
from django.apps import apps
from django.middleware.csrf import _get_new_csrf_string
from django.test import Client
from django.urls import path
from live.meta import LiveAppConfig
from live.ninja import ensure_api_parity, mount_app_routers, operation_ids
from live.operations import registry
from ninja import Router

from accounts.api import router as accounts_router
from base.api import router as base_router
from config.api import api, build_api

HOST = "localhost:8001"

probe_router = Router()


@probe_router.post("/echo")
def echo(request):
    return {"user": request.user.get_username()}


probe_api = build_api(urls_namespace="config-test-probe")
probe_api.add_router("", probe_router)
urlpatterns = [path("probe/", probe_api.urls)]


@pytest.fixture
def probe_urls(settings):
    settings.ROOT_URLCONF = __name__


def test_every_route_is_bound_to_its_operation():
    assert ensure_api_parity(api) == []
    assert {"base.session.me", "accounts.hub.list"} <= operation_ids(api)


# --- Mounting the routers of the apps (as hub-next does) -----------------------------------------
# mount_app_routers itself lives in live.ninja and is tested there (packages/live/tests/test_ninja.py).


def test_accounts_is_an_app_whose_router_the_api_mounts():
    assert isinstance(apps.get_app_config("accounts"), LiveAppConfig)


def test_live_mount_app_routers_mounts_base_and_accounts():
    """Platform LiveAppConfigs (round 15, PLAN §20) with an api.py, mounted in INSTALLED_APPS order."""
    assert mount_app_routers(build_api(urls_namespace="config-test-mount")) == [
        "base",
        "accounts",
        # The app catalog (round 16, PLAN §21): before hubs, which reads it.
        "apps",
        "hubs",
        # The EU VAT engine (lot L2-A): POST /api/billing/vat-check, GET /api/billing/tax-preview.
        "billing",
        # The signed authorisation of a business (plan 2026-10-15): GET /api/fiscal/representation.
        "fiscal",
        # The public web: GET /api/v1/app/release/ (public.app.release).
        "public",
    ]


def test_base_and_accounts_routes_are_mounted_exactly_once():
    """By the loop alone: an extra ``add_router`` of base would mount it twice (ninja's ConfigError)."""
    routers = [router for _, router in api._routers]
    routes = [str(pattern.pattern) for pattern in api.urls[0]]

    assert (routers.count(base_router), routers.count(accounts_router)) == (1, 1)
    assert (routes.count("me"), routes.count("accounts/hubs")) == (1, 1)


@pytest.mark.django_db
def test_openapi_is_served_with_operation_names_as_ids(client):
    response = client.get("/api/openapi.json", HTTP_HOST=HOST)

    assert response.status_code == 200
    schema = response.json()
    assert (schema["info"]["title"], schema["info"]["version"]) == (
        "ERPlora Cloud API",
        "1",
    )
    assert schema["paths"]["/api/me"]["get"]["operationId"] == "base.session.me"
    assert (
        schema["paths"]["/api/accounts/hubs"]["get"]["operationId"]
        == "accounts.hub.list"
    )
    ids = [
        op["operationId"]
        for methods in schema["paths"].values()
        for op in methods.values()
    ]
    assert ids and all(op_id in registry for op_id in ids)


class _Pairs(list):
    """An object of the document as the ordered pairs it was written with (``object_pairs_hook``)."""


def _repeated_keys(node, where="$") -> list[str]:
    if isinstance(node, _Pairs):
        keys = [key for key, _ in node]
        found = [f"{where}.{key}" for key in dict.fromkeys(keys) if keys.count(key) > 1]
        return found + [repeated for key, value in node for repeated in _repeated_keys(value, f"{where}.{key}")]
    if isinstance(node, list):
        return [repeated for index, item in enumerate(node) for repeated in _repeated_keys(item, f"{where}[{index}]")]
    return []


@pytest.mark.django_db
def test_no_object_of_the_openapi_document_repeats_a_key(client):
    """ninja keys a response by the int ``200`` and an ``openapi_extra`` written with the text ``"200"`` adds a
    second one: a valid Python dict, a JSON object with the key twice that a strict reader (Postman, a code
    generator) refuses or reads as the last one only. The whole document, at every level."""
    body = client.get("/api/openapi.json", HTTP_HOST=HOST).content

    assert _repeated_keys(json.loads(body, object_pairs_hook=_Pairs)) == []


@pytest.mark.django_db
def test_the_docs_page_carries_the_nonce(client, django_user_model):
    """ninja's own page has scripts without the CSP nonce (blank under 'strict-dynamic'): ``/api/docs`` is ours
    (``accounts.api_docs``, ACCOUNTS-F34), every script with the response's nonce."""
    client.force_login(django_user_model.objects.create_user(email="docs@example.com", password="x"))

    response = client.get("/api/docs", HTTP_HOST=HOST)

    nonce = response.headers["Content-Security-Policy"].split("'nonce-")[1].split("'")[0]
    assert response.status_code == 200
    assert response.content.decode().count(f'<script nonce="{nonce}"') == 2


@pytest.mark.django_db
def test_anonymous_write_is_the_401_envelope(probe_urls, client):
    response = client.post("/probe/echo", HTTP_HOST=HOST)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_a_session_write_needs_the_csrf_token(probe_urls, ana):
    client = Client(enforce_csrf_checks=True)
    client.force_login(ana)
    token = _get_new_csrf_string()
    client.cookies["csrftoken"] = token

    without = client.post("/probe/echo", HTTP_HOST=HOST)
    with_token = client.post("/probe/echo", HTTP_HOST=HOST, HTTP_X_CSRFTOKEN=token)

    assert without.status_code == 403
    assert (with_token.status_code, with_token.json()) == (
        200,
        {"user": "ana@example.com"},
    )
