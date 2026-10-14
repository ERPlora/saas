"""``GET /api/apps``, ``/api/apps/get``, ``/api/apps/doc`` and ``/api/apps/sitemap``: the public
catalog (spec §5.1 and §8.2).

The routes the panel's SPA uses (block 5), each bound to its operation, with the input in the query
string as demo's; open to an anonymous visitor (``auth=None``), in the request's language.
"""

from datetime import UTC, datetime

import pytest
from live.ninja import ensure_api_parity, operation_ids

from apps.tests.factories import make_app, make_doc
from config.api import api

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def test_the_routes_are_bound_to_their_operations():
    assert ensure_api_parity(api) == []
    assert {
        "apps.app.list",
        "apps.app.get",
        "apps.app.doc",
        "apps.app.sitemap",
    } <= operation_ids(api)


def test_the_openapi_names_them_by_their_operations(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]

    assert paths["/api/apps"]["get"]["operationId"] == "apps.app.list"
    assert paths["/api/apps/get"]["get"]["operationId"] == "apps.app.get"
    assert paths["/api/apps/doc"]["get"]["operationId"] == "apps.app.doc"
    assert paths["/api/apps/sitemap"]["get"]["operationId"] == "apps.app.sitemap"


def test_an_anonymous_visitor_reads_the_sitemap_entries(client):
    invoice = make_app("invoice")
    make_doc(invoice, "es", updated_at=datetime(2026, 10, 1, 9, 30, tzinfo=UTC))
    make_app("inventory")

    response = client.get("/api/apps/sitemap", HTTP_HOST=HOST)

    assert response.status_code == 200
    entries = response.json()["apps"]
    assert [entry["id"] for entry in entries] == ["inventory", "invoice"]
    assert (entries[0]["has_docs"], entries[0]["updated_at"]) == (False, None)
    assert entries[1]["has_docs"] is True
    assert datetime.fromisoformat(entries[1]["updated_at"]) == datetime(
        2026, 10, 1, 9, 30, tzinfo=UTC
    )


@pytest.fixture
def invoice():
    app = make_app("invoice", name_en="Invoices", name_es="Facturas", category="sales")
    make_doc(app, "es", markdown="# Facturas\n")
    return app


def test_an_anonymous_visitor_lists_the_apps(client, invoice):
    response = client.get(
        "/api/apps", {"category": "sales", "premium": "0"}, HTTP_HOST=HOST
    )

    assert response.status_code == 200
    assert [app["id"] for app in response.json()["apps"]] == ["invoice"]


def test_an_anonymous_visitor_reads_an_app_and_its_documentation(client, invoice):
    app = client.get("/api/apps/get", {"id": "invoice"}, HTTP_HOST=HOST)
    doc = client.get("/api/apps/doc", {"id": "invoice"}, HTTP_HOST=HOST)

    assert (app.status_code, app.json()["has_docs"]) == (200, True)
    assert (doc.status_code, doc.json()["lang"], doc.json()["fallback"]) == (
        200,
        "es",
        True,
    )
    assert "Facturas" in doc.json()["html"]


def test_the_request_language_picks_the_texts(client, invoice):
    response = client.get("/api/apps", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

    assert response.json()["apps"][0]["name"] == "Facturas"


def test_an_unknown_app_is_the_404_envelope(client, invoice):
    response = client.get("/api/apps/get", {"id": "nope"}, HTTP_HOST=HOST)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "apps.app_not_found"


def test_a_filter_that_is_not_understood_is_not_a_422(client, invoice):
    response = client.get(
        "/api/apps", {"category": "marketing", "premium": "maybe"}, HTTP_HOST=HOST
    )

    assert response.status_code == 200
    assert [app["id"] for app in response.json()["apps"]] == ["invoice"]


@pytest.mark.parametrize(
    "params", [{"q": "\x00"}, {"vertical": "\x00"}, {"q": "Invo\x00ices"}]
)
def test_a_nul_in_a_filter_is_not_a_500(client, invoice, params):
    """``/api/apps?q=%00``: psycopg refuses a NUL in a parameter (``DataError``); it is dropped."""
    response = client.get("/api/apps", params, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert [app["id"] for app in response.json()["apps"]] == ["invoice"]
