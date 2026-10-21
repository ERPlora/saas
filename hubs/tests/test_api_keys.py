"""An account's API key reads its businesses (``expose_api=True``; plan 2026-10-13, L3-A; PLAN-SAAS §2.4).

A key opens only the operations declared with ``expose_api=True``, within its scopes (``accounts.api_auth``):
hubs exposes its reads to ``hubs.read`` and billing its tax preview, ERPlora's invoices (L3-C) and the
subscriptions of the account's businesses (BILLING-F18) to ``billing.read``; no write yet. The key
acts as its account, so it sees what the account sees and nothing else (``queries.access``). The taxonomy and
the plans on sale are public routes: exposed too, a key there is simply ignored.
"""

from decimal import Decimal

import pytest
from django.test import Client
from live.operations import registry

from accounts.models import ApiKey
from hubs.models import HubMember
from hubs.tests.conftest import add_member, create_business, member_of

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
#: The reads a key may make, and nothing else of the SaaS (no write yet).
EXPOSED = {
    "hubs.business.list",
    "hubs.business.get",
    "hubs.member.list",
    # The usage of a business (L4-A).
    "hubs.usage.get",
    "hubs.usage.series",
    "hubs.plan.list",
    "hubs.sector.list",
    "hubs.business_type.list",
    "billing.tax.preview",
    # ERPlora's invoices of the account (billing, lot L3-C): the scope «Invoices · read».
    "billing.invoice.list",
    "billing.invoice.get",
    "billing.invoice.pdf",
    "billing.invoice.csv",
    # The subscriptions of the account's businesses (BILLING-F18, the old SaaS's subscriptions API).
    "billing.subscription.list",
}


def key_of(user, *scopes):
    secret, prefix, key_hash = ApiKey.new_secret()
    ApiKey.objects.create(
        user=user,
        name="integration",
        prefix=prefix,
        key_hash=key_hash,
        scopes=list(scopes),
    )
    return secret


def get(path, secret, **params):
    return Client(enforce_csrf_checks=True).get(
        f"/api{path}", params, HTTP_HOST=HOST, HTTP_AUTHORIZATION=f"Bearer {secret}"
    )


def post(path, secret, body):
    return Client(enforce_csrf_checks=True).post(
        f"/api{path}",
        body,
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_AUTHORIZATION=f"Bearer {secret}",
    )


def test_exactly_these_operations_are_exposed_and_all_are_reads():
    exposed = {name for name, op in registry.items() if op.expose_api}

    assert exposed == EXPOSED
    assert {registry[name].kind for name in exposed} == {"query"}


class TestAKeyWithHubsRead:
    def test_it_lists_the_businesses_its_account_sees(
        self, business, team, owner, make_user
    ):
        create_business(make_user("paco@example.com"), name="Bar Paco", slug="bar-paco")
        secret = key_of(team["employee"], "hubs.read")

        response = get("/hubs/businesses", secret)

        assert response.status_code == 200
        assert [row["id"] for row in response.json()["rows"]] == [str(business.id)]

    def test_it_reads_a_business_and_its_members_as_its_account_may(
        self, business, team
    ):
        secret = key_of(team["admin"], "hubs.read")

        detail = get("/hubs/businesses/detail", secret, id=str(business.id))
        members = get("/hubs/members", secret, hub_id=str(business.id))

        assert (detail.status_code, detail.json()["id"]) == (200, str(business.id))
        assert members.status_code == 200
        assert str(member_of(business, team["employee"]).id) in {
            row["id"] for row in members.json()["rows"]
        }

    def test_it_never_reaches_a_business_its_account_does_not_answer(
        self, business, team
    ):
        secret = key_of(team["stranger"], "hubs.read")

        assert (
            get("/hubs/businesses/detail", secret, id=str(business.id)).status_code
            == 404
        )

    def test_the_public_lists_ignore_it(self, plans, make_user):
        secret = key_of(make_user("integration@example.com"), "hubs.read")

        assert get("/plans", secret).status_code == 200
        assert get("/catalog/sectors", secret).status_code == 200
        assert get("/catalog/business-types", secret).status_code == 200


class TestRefused:
    def test_a_key_without_the_scope_is_403_missing_scope(self, business, team):
        secret = key_of(team["owner"], "billing.read")

        response = get("/hubs/businesses", secret)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "api_key_missing_scope"

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/hubs/address"),
            ("get", "/hubs/invitations"),
            ("post", "/hubs/businesses"),
            ("post", "/hubs/members/remove"),
        ],
    )
    def test_an_operation_not_exposed_is_403_not_allowed(
        self, business, team, method, path
    ):
        secret = key_of(team["owner"], "hubs.read", "hubs.write", "billing.read")

        response = (
            get(path, secret, name="Bar")
            if method == "get"
            else post(path, secret, {"name": "Bar", "country": "ES"})
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "api_key_not_allowed"

    def test_a_write_with_hubs_write_is_still_refused(self, business, team):
        secret = key_of(team["owner"], "hubs.write")

        response = post(
            "/hubs/members/remove",
            secret,
            {"id": str(member_of(business, team["employee"]).id)},
        )

        assert response.json()["error"]["code"] == "api_key_not_allowed"
        assert HubMember.objects.filter(
            pk=member_of(business, team["employee"]).pk
        ).exists()


class TestBillingRead:
    def test_a_key_with_billing_read_previews_the_tax(self, owner):
        secret = key_of(owner, "billing.read")

        response = get(
            "/billing/tax-preview",
            secret,
            country="ES",
            postal_code="28001",
            net="29.99",
        )

        assert response.status_code == 200
        assert Decimal(response.json()["total"]) == Decimal("36.29")

    def test_hubs_read_does_not_open_it(self, owner):
        secret = key_of(owner, "hubs.read")

        response = get("/billing/tax-preview", secret, country="ES", net="10")

        assert (response.status_code, response.json()["error"]["code"]) == (
            403,
            "api_key_missing_scope",
        )
