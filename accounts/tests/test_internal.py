"""``POST /internal/auth/redeem``: the hub spends the one-time code, signed (PLAN-SAAS §3.1 step 6)."""

import json
import time
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from accounts import services
from accounts.models import AuthExchangeCode, HubMembership
from accounts.signing import sign, signed_headers

URL = "/internal/auth/redeem"
SECRET = "test-internal-secret"

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _secret(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET


@pytest.fixture
def code(ana):
    HubMembership.objects.create(
        user=ana, hub_slug="a", role=HubMembership.Role.EMPLOYEE
    )
    return services.issue_code(ana, "a")


def redeem(client, payload, *, timestamp=None, secret=SECRET, signature=None, raw=None):
    body = raw if raw is not None else json.dumps(payload).encode()
    timestamp = int(time.time()) if timestamp is None else timestamp
    headers = {
        "X-Erplora-Timestamp": str(timestamp),
        "X-Erplora-Signature": signature
        if signature is not None
        else sign(body, timestamp, secret),
    }
    return client.post(URL, body, content_type="application/json", headers=headers)


def test_a_signed_valid_code_returns_who_signs_in(client, code, ana):
    response = redeem(client, {"code": code, "hub": "a"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(ana.pk),
        "email": "ana@example.com",
        "name": "Ana García",
        "locale": "es",
        "role": "hub_employee",
    }
    assert "no-store" in response["Cache-Control"]


def test_each_hub_receives_the_role_the_account_has_on_it(client, ana):
    HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)
    HubMembership.objects.create(
        user=ana, hub_slug="b", role=HubMembership.Role.EMPLOYEE
    )
    code_a = services.issue_code(ana, "a")
    code_b = services.issue_code(ana, "b")

    assert redeem(client, {"code": code_a, "hub": "a"}).json()["role"] == "hub_owner"
    assert redeem(client, {"code": code_b, "hub": "b"}).json()["role"] == "hub_employee"


def test_it_needs_no_csrf_token(code):
    response = redeem(Client(enforce_csrf_checks=True), {"code": code, "hub": "a"})

    assert response.status_code == 200


def test_the_second_redemption_is_refused(client, code):
    redeem(client, {"code": code, "hub": "a"})

    response = redeem(client, {"code": code, "hub": "a"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"
    assert response.json()["error"]["message"]


def test_a_code_for_another_hub_is_refused(client, code):
    response = redeem(client, {"code": code, "hub": "b"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"


def test_a_reserved_hub_is_an_invalid_code(client, ana):
    # Rows saved without validation: `admin` is reserved, so no hub named so ever gets a session.
    HubMembership.objects.create(
        user=ana, hub_slug="admin", role=HubMembership.Role.OWNER
    )
    now = timezone.now()
    AuthExchangeCode.objects.create(
        code_hash=AuthExchangeCode.hash_code("a-code"),
        user=ana,
        hub_slug="admin",
        created_at=now,
        expires_at=now + timedelta(seconds=60),
    )

    response = redeem(client, {"code": "a-code", "hub": "admin"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"
    assert AuthExchangeCode.objects.get().used_at is None


def test_a_bad_signature_is_unauthorized_and_does_not_spend_the_code(client, code):
    response = redeem(client, {"code": code, "hub": "a"}, secret="someone-else")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert redeem(client, {"code": code, "hub": "a"}).status_code == 200


def test_a_stale_timestamp_is_unauthorized(client, code):
    response = redeem(
        client, {"code": code, "hub": "a"}, timestamp=int(time.time()) - 301
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_an_unsigned_call_is_unauthorized(client, code):
    response = client.post(
        URL, {"code": code, "hub": "a"}, content_type="application/json"
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "raw", [b"not json", b"[]", b'{"code": 1, "hub": "a"}', b'{"code": "x"}']
)
def test_a_signed_body_that_is_not_a_code_and_a_hub_is_a_bad_request(client, raw):
    response = redeem(client, None, raw=raw)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_only_post_is_allowed(client):
    response = client.get(URL)

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


class TestHubAdminAudience:
    """``"audience": "hub-admin"`` (ronda 13, PLAN §18): the Hub at ``hubs.erplora.com`` spends the code
    of a staff jump and learns the platform role, never a ``hub_*`` one. Without ``audience``, the
    redeem is the member's ``hub-session``."""

    @pytest.fixture
    def platform_admin(self, password):
        user, _ = services.create_platform_user("boss@erplora.com", "admin", password)
        return user

    @pytest.fixture
    def admin_code(self, platform_admin):
        return services.issue_code(platform_admin, "a", audience="hub-admin")

    def test_a_staff_code_returns_the_platform_admin_role(self, client, admin_code, platform_admin):
        response = redeem(client, {"code": admin_code, "hub": "a", "audience": "hub-admin"})

        assert response.status_code == 200
        assert response.json() == {
            "user_id": str(platform_admin.pk),
            "email": "boss@erplora.com",
            "name": "boss@erplora.com",
            "locale": "en",
            "role": "platform_admin",
        }
        assert "no-store" in response["Cache-Control"]

    def test_support_gets_the_platform_support_role(self, client, password):
        helper, _ = services.create_platform_user("help@erplora.com", "support", password)
        code = services.issue_code(helper, "a", audience="hub-admin")

        response = redeem(client, {"code": code, "hub": "a", "audience": "hub-admin"})

        assert response.json()["role"] == "platform_support"

    def test_without_the_audience_a_staff_code_is_invalid_and_not_spent(self, client, admin_code):
        response = redeem(client, {"code": admin_code, "hub": "a"})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_code"
        assert redeem(client, {"code": admin_code, "hub": "a", "audience": "hub-admin"}).status_code == 200

    def test_a_members_code_opens_no_hub_admin(self, client, code):
        response = redeem(client, {"code": code, "hub": "a", "audience": "hub-admin"})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_code"
        assert redeem(client, {"code": code, "hub": "a", "audience": "hub-session"}).status_code == 200

    def test_a_customer_never_gets_a_platform_role_even_with_a_hub_admin_row(self, client, ana):
        # A row saved by hand: the access is re-checked at redemption, and a customer is no staff.
        HubMembership.objects.create(user=ana, hub_slug="a", role=HubMembership.Role.OWNER)
        now = timezone.now()
        AuthExchangeCode.objects.create(
            code_hash=AuthExchangeCode.hash_code("a-code"),
            user=ana,
            audience="hub-admin",
            hub_slug="a",
            created_at=now,
            expires_at=now + timedelta(seconds=60),
        )

        response = redeem(client, {"code": "a-code", "hub": "a", "audience": "hub-admin"})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_code"

    @pytest.mark.parametrize("hub", ["hubs", "hub"])
    def test_the_platform_host_is_no_target(self, client, admin_code, hub):
        response = redeem(client, {"code": admin_code, "hub": hub, "audience": "hub-admin"})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_code"

    @pytest.mark.parametrize("audience", [None, 1, ["hub-admin"], "", "hub-everything", "HUB-ADMIN"])
    def test_an_audience_that_is_not_one_of_the_two_is_a_bad_request(self, client, admin_code, audience):
        response = redeem(client, {"code": admin_code, "hub": "a", "audience": audience})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"
        assert AuthExchangeCode.objects.get().used_at is None


class TestRotationAndTheSignatureV2:
    """L1-A2 (PLAN-SAAS §2.1): two live secrets, and the signature that covers method and path."""

    PREVIOUS = "the-secret-before-the-rotation"

    def _post(self, client, payload, headers):
        return client.post(URL, json.dumps(payload).encode(), content_type="application/json", headers=headers)

    def test_a_hub_still_on_the_previous_secret_redeems_during_the_rotation(self, client, code, settings):
        settings.INTERNAL_SHARED_SECRET_PREVIOUS = self.PREVIOUS

        assert redeem(client, {"code": code, "hub": "a"}, secret=self.PREVIOUS).status_code == 200

    def test_without_the_previous_secret_its_signature_is_unauthorized(self, client, code, settings):
        settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""

        assert redeem(client, {"code": code, "hub": "a"}, secret=self.PREVIOUS).status_code == 401

    def test_a_call_signed_v2_for_this_route_redeems(self, client, code):
        body = json.dumps({"code": code, "hub": "a"}).encode()
        headers = signed_headers("POST", URL, body, int(time.time()), SECRET)

        response = client.post(URL, body, content_type="application/json", headers=headers)

        assert response.status_code == 200

    def test_a_body_signed_v2_for_another_route_is_unauthorized_and_does_not_spend_the_code(self, client, code):
        body = json.dumps({"code": code, "hub": "a"}).encode()
        headers = signed_headers("POST", "/internal/hubs/x/ready", body, int(time.time()), SECRET)

        response = client.post(URL, body, content_type="application/json", headers=headers)

        assert response.status_code == 401
        assert redeem(client, {"code": code, "hub": "a"}).status_code == 200
