"""ASSISTANT-F11 (ASSISTANT-G42) · Know who calls and for which business: every door of the assistant
(``/internal/assistant/*`` and ``/internal/speech/*``) is the Hub's alone, signed as every ``/internal`` call
(``accounts.signing``), and names the business in ``hub`` (its address or its id; a demo, by its ``demo-…`` address).

Cases of the old product's SAAS_ASSISTANT-F01 (``IsHubMachine``/``IsHubMember``, ``api_key_hub_mismatch``,
``hub_not_found``): here the credential is the platform's signature, never a key of a business, so a business can
never be named by another one's credential; what is left is the signature and the business's state. The rate limit
of a business is spent only after both pass (saas#2531: anybody could spend a business's budget with its id).
"""

import time

import pytest
from django.test import Client

from assistant.tests.doors import door, error_code
from hubs.models import Hub

USAGE = "/internal/assistant/usage"
DOORS = [
    "/internal/assistant/chat/stream",
    "/internal/assistant/chat",
    "/internal/assistant/usage",
    "/internal/assistant/embeddings",
    "/internal/assistant/docs/search",
    "/internal/assistant/report",
    "/internal/speech/transcribe",
    "/internal/speech/synthesize",
]

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.mark.parametrize("path", DOORS)
def test_every_door_refuses_an_unsigned_call(client, internal, business, path):
    response = door(client, path, {"hub": business.slug}, signed=False)

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"


@pytest.mark.parametrize("path", DOORS)
def test_every_door_refuses_a_call_signed_with_another_secret(client, internal, business, path):
    response = door(client, path, {"hub": business.slug}, secret="somebody-else")

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"


@pytest.mark.parametrize("path", DOORS)
def test_every_door_takes_only_a_post(client, internal, business, path):
    response = door(client, path, {"hub": business.slug}, method="get")

    assert response.status_code == 405
    assert error_code(response) == "method_not_allowed"
    assert response["Allow"] == "POST"


def test_a_stale_signature_is_refused(client, internal, business):
    response = door(client, USAGE, {"hub": business.slug}, timestamp=int(time.time()) - 301)

    assert response.status_code == 401
    assert error_code(response) == "unauthorized"


def test_a_signature_of_the_previous_secret_still_opens_during_a_rotation(client, internal, business, settings):
    settings.INTERNAL_SHARED_SECRET = "the-new-one"
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = internal

    response = door(client, USAGE, {"hub": business.slug}, secret=internal)

    assert response.status_code == 200


def test_a_v2_signature_opens_the_door(client, internal, business):
    response = door(client, USAGE, {"hub": business.slug}, v2=True)

    assert response.status_code == 200


def test_a_body_that_is_not_json_is_refused(client, internal):
    response = door(client, USAGE, b"not json")

    assert response.status_code == 422
    assert error_code(response) == "invalid_payload"


def test_a_call_without_hub_is_refused_naming_the_field(client, internal):
    response = door(client, USAGE, {})

    assert response.status_code == 422
    assert error_code(response) == "invalid_payload"
    assert "hub" in response.json()["error"]["fields"]


def test_a_business_is_named_by_its_address_or_by_its_id(client, internal, business):
    by_slug = door(client, USAGE, {"hub": business.slug})
    by_id = door(client, USAGE, {"hub": str(business.id)})

    assert by_slug.status_code == by_id.status_code == 200
    assert by_slug.json() == by_id.json()


def test_a_business_the_saas_does_not_know_is_refused(client, internal, business):
    response = door(client, USAGE, {"hub": "nobody-here"})

    assert response.status_code == 404
    assert error_code(response) == "hub_unknown"


def test_a_purged_business_is_unknown(client, internal, business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

    response = door(client, USAGE, {"hub": business.slug})

    assert response.status_code == 404
    assert error_code(response) == "hub_unknown"


@pytest.mark.parametrize("status", [Hub.Status.PREPARING, Hub.Status.SUSPENDED, Hub.Status.DELETING])
def test_a_business_that_does_not_work_gets_no_assistant(client, internal, business, status):
    Hub.objects.filter(pk=business.pk).update(status=status)

    response = door(client, USAGE, {"hub": business.slug})

    assert response.status_code == 403
    assert error_code(response) == "hub_inactive"


def test_a_business_with_a_payment_pending_keeps_its_assistant(client, internal, business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.PAST_DUE)

    response = door(client, USAGE, {"hub": business.slug})

    assert response.status_code == 200


def test_a_demo_is_named_by_its_demo_address(client, internal):
    response = door(client, USAGE, {"hub": "demo-1a2b3c4d"})

    assert response.status_code == 200
    assert response.json()["demo"] is True


def test_the_word_demo_alone_names_nothing(client, internal):
    response = door(client, USAGE, {"hub": "demo"})

    assert response.status_code == 404
    assert error_code(response) == "hub_unknown"


def test_a_declared_body_over_the_limit_is_refused_before_it_is_read(client, internal, business):
    response = client.post(
        USAGE,
        data=b"{}",
        content_type="application/json",
        HTTP_HOST="localhost",
        CONTENT_LENGTH=str(64 * 1024 * 1024),
    )

    assert response.status_code == 413
    assert error_code(response) == "payload_too_large"


def test_saas_2531_an_unsigned_call_spends_nothing_of_the_business_budget(client, internal, business, settings):
    settings.ASSISTANT_TURN_RATELIMIT = "2/h"
    for _ in range(5):
        door(client, USAGE, {"hub": business.slug}, signed=False)
        door(client, USAGE, {"hub": business.slug}, secret="somebody-else")

    assert door(client, USAGE, {"hub": business.slug}).status_code == 200
    assert door(client, USAGE, {"hub": business.slug}).status_code == 200


def test_only_the_platform_resolves_a_caller(ai_admin, business):
    from live.errors import PermissionDenied

    from assistant import queries
    from assistant.schemas import CallerIn
    from assistant.tests.conftest import staff_ctx

    with pytest.raises(PermissionDenied) as refused:
        queries.caller_resolve(staff_ctx(ai_admin), CallerIn(hub=business.slug))

    assert refused.value.code == "assistant.platform_only"
