"""The panel's routes under ``/api/hubs/``: each bound to its operation, over HTTP with the single error
envelope (PLAN §14.1): 401 without an account, 404 for a business one has no access to, 403 for a role
below the one needed, 409 with the domain code, 422 with ``fields``.

Django's sync test client (it sees the test's transaction); the session client of pytest-django
skips the CSRF check, which ``config/tests/test_api.py`` covers for the whole API.
"""

import json

import pytest
from live.ninja import ensure_api_parity

from config.api import api
from hubs.models import Hub, HubMember
from hubs.tests.conftest import member_of

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"


def get(client, path, **params):
    return client.get(f"/api{path}", params, HTTP_HOST=HOST)


def post(client, path, data):
    return client.post(
        f"/api{path}",
        json.dumps(data, default=str),
        content_type="application/json",
        HTTP_HOST=HOST,
    )


def error(response):
    return response.status_code, response.json()["error"]["code"]


@pytest.fixture
def signed_in(client):
    def sign_in(user):
        client.force_login(user)
        return client

    return sign_in


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_openapi_lists_the_routes_of_the_panel(client):
    paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]
    operations = {
        op["operationId"] for methods in paths.values() for op in methods.values()
    }

    assert {
        "hubs.business.list",
        "hubs.business.create",
        "hubs.business.open",
        "hubs.member.invite",
        "hubs.invitation.accept",
        "hubs.ownership.transfer",
        "hubs.billing_profile.update",
        "hubs.plan.list",
    } <= operations
    assert (
        "hubs.business.mark_ready" not in operations
    )  # the Hub's callback, never a public route


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/hubs/businesses"),
        ("POST", "/hubs/businesses"),
        ("GET", "/hubs/invitations"),
        ("POST", "/hubs/members/invite"),
    ],
)
def test_without_an_account_it_is_401(client, method, path):
    response = get(client, path) if method == "GET" else post(client, path, {})

    assert error(response) == (401, "unauthorized")


def test_the_whole_sign_up_over_http(signed_in, owner, plans):
    client = signed_in(owner)

    created = post(client, "/hubs/businesses", {"name": "Bar Manolo", "country": "es"})

    assert created.status_code == 201
    body = created.json()
    assert (body["slug"], body["status"], body["role"]) == (
        "bar-manolo",
        "preparing",
        "hub_owner",
    )
    listed = get(client, "/hubs/businesses").json()
    assert [row["name"] for row in listed["rows"]] == ["Bar Manolo"]
    assert (
        get(client, "/hubs/businesses/detail", id=body["id"]).json()["name"]
        == "Bar Manolo"
    )


def test_an_invalid_sign_up_is_422_per_field(signed_in, owner, plans):
    response = post(signed_in(owner), "/hubs/businesses", {"name": "", "country": "US"})

    assert error(response) == (422, "invalid_payload")
    assert set(response.json()["error"]["fields"]) == {"name", "country"}


def test_a_reserved_or_taken_address_is_409_with_its_code(
    signed_in, owner, plans, make_user
):
    client = signed_in(owner)

    assert error(
        post(
            client, "/hubs/businesses", {"name": "Hub", "country": "ES", "slug": "hubs"}
        )
    ) == (409, "hubs.slug_reserved")
    post(client, "/hubs/businesses", {"name": "Bar Manolo", "country": "ES"})
    client.force_login(make_user("other@example.com"))
    assert error(
        post(
            client,
            "/hubs/businesses",
            {"name": "Bar", "country": "ES", "slug": "bar-manolo"},
        )
    ) == (409, "hubs.slug_taken")


def test_a_business_of_somebody_else_is_404_and_a_low_role_403(
    signed_in, business, team
):
    client = signed_in(team["stranger"])
    assert error(get(client, "/hubs/businesses/detail", id=str(business.id))) == (
        404,
        "not_found",
    )

    client = signed_in(team["employee"])
    assert error(get(client, "/hubs/members", hub_id=str(business.id))) == (
        403,
        "permission_denied",
    )


def test_the_members_page_and_an_invitation_over_http(signed_in, business, team):
    client = signed_in(team["owner"])

    invited = post(
        client,
        "/hubs/members/invite",
        {"hub_id": str(business.id), "email": "new@example.com", "role": "hub_manager"},
    )
    page = get(client, "/hubs/members", hub_id=str(business.id), limit=10).json()

    assert invited.status_code == 200 and invited.json()["status"] == "pending"
    assert "new@example.com" in [row["email"] for row in page["rows"]]
    assert error(
        post(
            client,
            "/hubs/members/invite",
            {"hub_id": str(business.id), "email": "x@example.com", "role": "hub_owner"},
        )
    ) == (
        422,
        "invalid_payload",
    )


def test_an_invitee_answers_over_http(signed_in, business, team):
    client = signed_in(team["invitee"])
    (invitation,) = get(client, "/hubs/invitations").json()["invitations"]

    accepted = post(client, "/hubs/invitations/accept", {"id": invitation["id"]})

    assert accepted.status_code == 200 and accepted.json()["name"] == "Bar Manolo"
    assert member_of(business, team["invitee"]).accepted_at is not None


def test_opening_answers_the_hubs_start(signed_in, business, owner):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.ACTIVE)

    opened = post(
        signed_in(owner), "/hubs/businesses/open", {"id": str(business.id), "next": "/"}
    )

    assert opened.status_code == 200
    assert opened.json() == {"url": "http://bar-manolo.localhost:8000/auth/login?next=/"}


def test_deleting_needs_the_name_and_answers_the_deleted_business(
    signed_in, business, owner
):
    client = signed_in(owner)

    refused = post(
        client,
        "/hubs/businesses/delete",
        {"id": str(business.id), "confirm_name": "nope"},
    )
    deleted = post(
        client,
        "/hubs/businesses/delete",
        {"id": str(business.id), "confirm_name": "Bar Manolo"},
    )

    assert error(refused) == (422, "invalid_payload") and set(
        refused.json()["error"]["fields"]
    ) == {"confirm_name"}
    assert deleted.json()["status"] == "deleting"


def test_the_ownership_and_the_payer_over_http(signed_in, business, team):
    client = signed_in(team["owner"])
    admin = HubMember.objects.get(hub=business, user=team["admin"])

    offered = post(
        client,
        "/hubs/ownership/transfer",
        {"hub_id": str(business.id), "member_id": str(admin.id)},
    )
    payer = post(
        client,
        "/hubs/billing-profile",
        {"hub_id": str(business.id), "same_as_business": True},
    )

    assert offered.json()["status"] == "pending"
    assert payer.json()["billing_name"] == "Bar Manolo"
    assert (
        get(client, "/hubs/billing-profile", hub_id=str(business.id)).json()[
            "same_as_business"
        ]
        is True
    )


def test_the_proposed_address_over_http(signed_in, owner, plans):
    assert (
        get(signed_in(owner), "/hubs/address", name="Peluquería Ana").json()["slug"]
        == "peluqueria-ana"
    )
