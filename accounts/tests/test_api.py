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

    [(path, view)] = router.path_operations.items()
    [route] = view.operations
    assert (path, route.methods, route.operation_id) == ("/accounts/hubs", ["GET"], "accounts.hub.list")
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
