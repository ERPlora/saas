"""The routes of billing: each one calls exactly one operation, and the OpenAPI lists them."""

import pytest
from live.ninja import ensure_api_parity

from config.api import api

HOST = "localhost:8001"


def test_the_routes_are_bound_to_their_operations():
    from billing.api import router

    routes = {
        path: sorted(
            (method, operation.operation_id)
            for operation in view.operations
            for method in operation.methods
        )
        for path, view in router.path_operations.items()
    }

    assert routes == {
        "/billing/vat-check": [("POST", "billing.vat_check.run")],
        "/billing/tax-preview": [("GET", "billing.tax.preview")],
        "/billing/promo-check": [("GET", "billing.promo.check")],
        "/billing/checkout/start": [("POST", "billing.checkout.start")],
        "/billing/checkout/confirm": [("POST", "billing.checkout.confirm")],
        "/billing/plan/change": [("POST", "billing.plan.change")],
        "/billing/plan/cancel": [("POST", "billing.plan.cancel")],
        "/billing/plan/keep": [("POST", "billing.plan.keep")],
        "/billing/module/cancel": [("POST", "billing.module.cancel")],
        "/billing/module/keep": [("POST", "billing.module.keep")],
        "/billing/portal": [("POST", "billing.portal.open")],
        "/billing/store": [("GET", "billing.store.catalog")],
        "/billing/invoices": [("GET", "billing.invoice.list")],
        "/billing/invoices/detail": [("GET", "billing.invoice.get")],
        "/billing/invoices/pdf": [("GET", "billing.invoice.pdf")],
        "/billing/invoices/csv": [("GET", "billing.invoice.csv")],
        "/billing/invoices/pay": [("POST", "billing.invoice.pay")],
        "/billing/subscriptions": [("GET", "billing.subscription.list")],
        "/billing/payment-method": [("GET", "billing.payment_method.get")],
    }


def test_the_api_keeps_its_parity():
    assert ensure_api_parity(api) == []


@pytest.mark.django_db
def test_openapi_lists_the_vat_check_and_the_preview(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]

    assert (
        paths["/api/billing/vat-check"]["post"]["operationId"]
        == "billing.vat_check.run"
    )
    assert (
        paths["/api/billing/tax-preview"]["get"]["operationId"] == "billing.tax.preview"
    )


STRIPE_ROUTES = {
    "/api/billing/promo-check": ("get", "billing.promo.check"),
    "/api/billing/checkout/start": ("post", "billing.checkout.start"),
    "/api/billing/checkout/confirm": ("post", "billing.checkout.confirm"),
    "/api/billing/plan/change": ("post", "billing.plan.change"),
    "/api/billing/plan/cancel": ("post", "billing.plan.cancel"),
    "/api/billing/plan/keep": ("post", "billing.plan.keep"),
    "/api/billing/module/cancel": ("post", "billing.module.cancel"),
    "/api/billing/module/keep": ("post", "billing.module.keep"),
    "/api/billing/portal": ("post", "billing.portal.open"),
}


@pytest.mark.django_db
def test_openapi_lists_what_buys_changes_and_cancels(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]

    assert {path: (method, paths[path][method]["operationId"]) for path, (method, _) in STRIPE_ROUTES.items()} == (
        STRIPE_ROUTES
    )


@pytest.mark.django_db
@pytest.mark.parametrize("path", [path for path, (method, _) in STRIPE_ROUTES.items() if method == "post"])
def test_a_visitor_buys_nothing(client, path):
    response = client.post(path, {}, content_type="application/json", HTTP_HOST=HOST)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.django_db
def test_the_panel_starts_a_checkout_with_its_session(owner, shop, stripe_double, issuer_identity):
    from django.test import Client

    client = Client()
    client.force_login(owner)

    response = client.post(
        "/api/billing/checkout/start",
        {"hub_id": str(shop.id), "plan": "starter"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )

    assert response.status_code == 200, response.content
    assert response.json()["flow"] == "checkout"
    assert response.json()["publishable_key"] == "pk_test_double"


@pytest.mark.django_db
def test_a_refusal_is_the_error_envelope(owner, shop, stripe_double):
    from django.test import Client

    shop.billing_profile.billing_postal_code = ""
    shop.billing_profile.save()
    client = Client()
    client.force_login(owner)

    response = client.post(
        "/api/billing/checkout/start",
        {"hub_id": str(shop.id), "plan": "starter"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "billing.billing_location_required"


#: The Billing section (lot L3-C).
BILLING_SECTION_ROUTES = {
    "/api/billing/invoices": ("get", "billing.invoice.list"),
    "/api/billing/invoices/detail": ("get", "billing.invoice.get"),
    "/api/billing/invoices/pdf": ("get", "billing.invoice.pdf"),
    "/api/billing/invoices/csv": ("get", "billing.invoice.csv"),
    "/api/billing/invoices/pay": ("post", "billing.invoice.pay"),
    "/api/billing/subscriptions": ("get", "billing.subscription.list"),
    "/api/billing/payment-method": ("get", "billing.payment_method.get"),
}


@pytest.mark.django_db
def test_openapi_lists_the_billing_section(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]

    assert {path: (method, paths[path][method]["operationId"]) for path, (method, _) in BILLING_SECTION_ROUTES.items()} == (
        BILLING_SECTION_ROUTES
    )
    assert "application/pdf" in paths["/api/billing/invoices/pdf"]["get"]["responses"]["200"]["content"]
    assert "text/csv" in paths["/api/billing/invoices/csv"]["get"]["responses"]["200"]["content"]


@pytest.mark.django_db
@pytest.mark.parametrize("path", [path for path, (method, _) in BILLING_SECTION_ROUTES.items() if method == "get"])
def test_a_visitor_reads_no_billing(client, path):
    response = client.get(path, HTTP_HOST=HOST)

    assert response.status_code == 401


@pytest.mark.django_db
def test_the_csv_route_answers_the_file(owner, shop):
    from django.test import Client

    client = Client()
    client.force_login(owner)

    response = client.get("/api/billing/invoices/csv", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"].startswith('attachment; filename="erplora-invoices-')
    assert response.content.startswith("\ufeff".encode())

