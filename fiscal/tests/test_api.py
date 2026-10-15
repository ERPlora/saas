"""``GET /api/fiscal/representation``: the authorisation of a business on its page (plan 2026-10-15, the panel's
card), bound to ``fiscal.representation.status`` with the single error envelope (PLAN §14.1): 401 without an
account, 404 for a business one has no access to, 403 below admin. The Hub's upload and the staff's decisions
have no route here: ``/internal`` (signed) and the admin."""

import pytest
from live.ninja import ensure_api_parity

from config.api import api
from fiscal.tests.conftest import make_grant

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
PATH = "/api/fiscal/representation"


def get(client, hub_id):
    return client.get(PATH, {"id": str(hub_id)}, HTTP_HOST=HOST)


def error(response):
    return response.status_code, response.json()["error"]["code"]


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_openapi_lists_only_the_state_of_fiscal(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]
    operations = {op["operationId"] for methods in paths.values() for op in methods.values()}

    assert {name for name in operations if name.startswith("fiscal.")} == {"fiscal.representation.status"}


def test_the_owner_reads_the_state(client, business, owner):
    make_grant(business)
    client.force_login(owner)

    response = get(client, business.id)

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["version"], body["documents"]["signed_model"]) == ("submitted", 1, True)


def test_a_business_that_never_sent_one_reads_none(client, business, owner):
    client.force_login(owner)

    assert get(client, business.id).json()["status"] == "none"


@pytest.mark.parametrize(("role", "expected"), [("admin", 200), ("manager", 403), ("employee", 403), ("stranger", 404)])
def test_only_the_owner_and_the_admins_read_it(client, business, team, role, expected):
    client.force_login(team[role])

    response = get(client, business.id)

    assert response.status_code == expected


def test_without_an_account_it_is_401(client, business):
    assert error(get(client, business.id)) == (401, "unauthorized")


def test_without_an_id_it_is_422(client, owner):
    client.force_login(owner)

    response = client.get(PATH, HTTP_HOST=HOST)

    assert error(response) == (422, "invalid_payload")
