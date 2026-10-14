"""GET /api/me: base.session.me over HTTP, open to anonymous visitors."""

import pytest
from django.urls import resolve

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def test_me_is_bound_to_session_me():
    from base.api import router

    [(path, view)] = router.path_operations.items()
    [route] = view.operations
    assert (path, route.methods, route.operation_id) == (
        "/me",
        ["GET"],
        "base.session.me",
    )
    assert route.auth_param is None  # an anonymous visitor gets user: null, not a 401
    assert resolve("/api/me").url_name


def test_anonymous(client):
    response = client.get("/api/me", HTTP_HOST=HOST)

    assert response.status_code == 200
    body = response.json()
    assert (body["user"], body["scope"]) == (None, {"kind": "user", "key": "anonymous"})
    assert body["menu"] == []


def test_signed_in(client, ana):
    client.force_login(ana)

    body = client.get("/api/me", HTTP_HOST=HOST).json()

    assert body["user"] == {"id": str(ana.pk), "label": "Ana García", "email": "ana@example.com"}
    assert body["scope"] == {"kind": "user", "key": str(ana.pk)}


def test_signed_in_gets_the_panels_menu_in_its_language(client, ana):
    client.force_login(ana)

    body = client.get("/api/me", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").json()

    [section] = body["menu"]
    assert [(i["path"], i["label"], i["icon"], i["webOnly"]) for i in section["items"]] == [
        ("/businesses", "Negocios", "lucide:store", False),
        ("/store", "Tienda", "lucide:shopping-bag", True),
        ("/billing", "Facturación", "lucide:receipt", False),
        ("/account", "Cuenta", "lucide:circle-user", False),
    ]


def test_language_follows_the_request(client):
    body = client.get("/api/me", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").json()

    assert body["language"] == "es"
