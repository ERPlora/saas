"""``POST /internal/hubs/{id}/ready``: the Hub says a business's database is ready (PLAN-SAAS §3.1 step 3;
round 17 §2.14).

Server to server, signed as ``/internal/auth/redeem`` (``accounts.signing``), so no CSRF token; the body
may name the hub, and then it must be the one of the path (the signature covers the body only). It
runs ``hubs.business.mark_ready`` as the platform, in the owner's channel. Errors answer the single
envelope.
"""

import json
import time
import uuid

import pytest
from live.models import OutboxEvent

from accounts.signing import sign
from hubs.models import Hub
from hubs.tests.conftest import SECRET

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _secret(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET


def ready(client, hub_id, payload=None, *, secret=SECRET, timestamp=None, raw=None):
    body = (
        raw
        if raw is not None
        else (b"" if payload is None else json.dumps(payload).encode())
    )
    timestamp = int(time.time()) if timestamp is None else timestamp
    return client.post(
        f"/internal/hubs/{hub_id}/ready",
        body,
        content_type="application/json",
        headers={
            "X-Erplora-Timestamp": str(timestamp),
            "X-Erplora-Signature": sign(body, timestamp, secret),
        },
    )


def test_a_signed_callback_makes_the_business_active(client, business):
    response = ready(client, business.id, {"id": str(business.id)})

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["status"]) == (str(business.id), "active")
    hub = Hub.objects.get(pk=business.pk)
    assert (hub.status, hub.ready_at is not None) == ("active", True)
    assert "no-store" in response["Cache-Control"]


def test_an_empty_body_is_refused(client, business):
    """Review of L1-A: the signature covers the body only, so the body must name the hub of the path."""
    response = ready(client, business.id)

    assert (response.status_code, response.json()["error"]["code"]) == (400, "invalid_request")
    assert Hub.objects.get(pk=business.pk).status == "preparing"


def test_its_event_reaches_the_owners_lists(client, business, owner):
    ready(client, business.id, {"id": str(business.id)})

    event = OutboxEvent.objects.get(name="hubs.business.ready")
    assert (event.scope_kind, event.scope_key, event.actor) == (
        "user",
        str(owner.pk),
        "system",
    )


def test_a_body_naming_another_hub_is_refused(client, business):
    response = ready(client, business.id, {"id": str(uuid.uuid7())})

    assert (response.status_code, response.json()["error"]["code"]) == (
        400,
        "invalid_request",
    )
    assert Hub.objects.get(pk=business.pk).status == "preparing"


@pytest.mark.parametrize("kind", ["unsigned", "other secret", "stale"])
def test_without_a_valid_signature_nothing_happens(client, business, kind):
    if kind == "unsigned":
        response = client.post(
            f"/internal/hubs/{business.id}/ready", b"", content_type="application/json"
        )
    elif kind == "other secret":
        response = ready(client, business.id, {"id": str(business.id)}, secret="not-the-secret")
    else:
        response = ready(client, business.id, {"id": str(business.id)}, timestamp=int(time.time()) - 3600)

    assert (response.status_code, response.json()["error"]["code"]) == (
        401,
        "unauthorized",
    )
    assert Hub.objects.get(pk=business.pk).status == "preparing"


def test_an_unknown_business_is_404(client, plans):
    hub_id = uuid.uuid7()
    response = ready(client, hub_id, {"id": str(hub_id)})

    assert (response.status_code, response.json()["error"]["code"]) == (
        404,
        "not_found",
    )


def test_a_malformed_body_is_400(client, business):
    response = ready(client, business.id, raw=b"{not json")

    assert (response.status_code, response.json()["error"]["code"]) == (
        400,
        "invalid_request",
    )


def test_only_post(client, business):
    response = client.get(f"/internal/hubs/{business.id}/ready")

    assert (response.status_code, response.json()["error"]["code"]) == (
        405,
        "method_not_allowed",
    )


def test_a_deleted_business_stays_deleted(client, business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

    assert ready(client, business.id, {"id": str(business.id)}).json()["status"] == "deleting"
