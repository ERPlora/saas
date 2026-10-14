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
