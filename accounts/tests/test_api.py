"""GET /api/accounts/hubs: accounts.hub.list over HTTP, the hubs the launcher (/launch) lists."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve

from accounts.models import HubMembership

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
HUBS = "/api/accounts/hubs"


def test_hub_list_is_bound_to_get_api_accounts_hubs():
    from accounts.api import router

    # The router holds the Account page's routes too (L3-A): this one is found by its path.
    [route] = router.path_operations["/accounts/hubs"].operations
    assert (route.methods, route.operation_id) == (["GET"], "accounts.hub.list")
    assert resolve(HUBS).url_name


def test_an_anonymous_visitor_gets_the_401_envelope(client):
    response = client.get(HUBS, HTTP_HOST=HOST)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_the_owner_sees_their_hubs_and_only_theirs(client, ana):
    HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)
    HubMembership.objects.create(user=ana, hub_slug="b", role=HubMembership.Role.OWNER)
    bo = get_user_model().objects.create_user(email="bo@example.com", password="x")
    HubMembership.objects.create(user=bo, hub_slug="c", role=HubMembership.Role.OWNER)
    client.force_login(ana)

    response = client.get(HUBS, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.json() == {
        "hubs": [
            {"slug": "a", "host": "a.localhost:8000", "url": "http://a.localhost:8000/auth/login?next=/"},
            {"slug": "b", "host": "b.localhost:8000", "url": "http://b.localhost:8000/auth/login?next=/"},
        ]
    }


def test_an_account_without_hubs_gets_an_empty_list(client, ana):
    client.force_login(ana)

    assert client.get(HUBS, HTTP_HOST=HOST).json() == {"hubs": []}


# The routes of the Account page (plan 2026-10-13, L3-A), as the OpenAPI publishes them (and Postman reads them).
CUENTA = {
    ("get", "/api/accounts/profile"): "accounts.profile.get",
    ("post", "/api/accounts/profile"): "accounts.profile.update",
    ("post", "/api/accounts/profile/delete"): "accounts.profile.delete",
    ("get", "/api/accounts/export"): "accounts.data.export",
    ("post", "/api/accounts/email/change"): "accounts.email.change",
    ("post", "/api/accounts/email/verify"): "accounts.email.verify",
    ("post", "/api/accounts/photo"): "accounts.photo.upload",
    ("post", "/api/accounts/photo/remove"): "accounts.photo.remove",
    ("get", "/api/accounts/preferences"): "accounts.preferences.get",
    ("post", "/api/accounts/preferences"): "accounts.preferences.update",
    ("get", "/api/accounts/sessions"): "accounts.session.list",
    ("post", "/api/accounts/sessions/close"): "accounts.session.close",
    ("post", "/api/accounts/sessions/close_others"): "accounts.session.close_others",
    ("get", "/api/accounts/browser-trust"): "accounts.browser_trust.get",
    ("post", "/api/accounts/browser-trust/revoke"): "accounts.browser_trust.revoke",
    ("get", "/api/accounts/api-keys"): "accounts.apikey.list",
    ("post", "/api/accounts/api-keys"): "accounts.apikey.create",
    ("post", "/api/accounts/api-keys/revoke"): "accounts.apikey.revoke",
}


def test_the_openapi_lists_every_route_of_cuenta(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]

    published = {
        (method, path): operation["operationId"]
        for path, methods in paths.items()
        for method, operation in methods.items()
        if path.startswith("/api/accounts/") and path != HUBS
    }
    assert published == CUENTA


def test_the_new_key_answers_201(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]

    assert set(paths["/api/accounts/api-keys"]["post"]["responses"]) >= {"201"}
