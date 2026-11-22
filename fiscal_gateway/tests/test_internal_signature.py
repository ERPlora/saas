"""``/internal/verifactu/<door>``: who may call. Signed as every ``/internal`` call (``accounts.signing``: v1
or v2, five minutes, the current or the previous secret), and a call that cannot be signed is refused before its
body is read."""

import io
import json
import time

import pytest
from django.test import RequestFactory

from accounts.signing import signed_headers
from fiscal_gateway import internal
from fiscal_gateway.tests.conftest import SECRET
from fiscal_gateway.tests.internal_calls import ANSWER, PRE_SEAL, call, error_of, payload

pytestmark = pytest.mark.usefixtures("_known_business", "_secrets")


# Signature


def test_without_a_signature_nothing_is_presented(client, respx_mock, erplora_seal):
    response = call(client, "submit", payload(), signed=False)

    assert error_of(response) == (401, "unauthorized")
    assert not respx_mock.calls


def test_a_signature_with_another_secret_is_unauthorized(
    client, respx_mock, erplora_seal
):
    response = call(client, "submit", payload(), secret="not-the-secret")

    assert error_of(response) == (401, "unauthorized")
    assert not respx_mock.calls


def test_the_previous_secret_still_opens_during_a_rotation(
    client, settings, respx_mock, erplora_seal
):
    settings.INTERNAL_SHARED_SECRET = "the-new-secret"
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = SECRET
    respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    assert call(client, "submit", payload()).status_code == 200


def test_a_v2_signature_for_this_door_is_heard(client, respx_mock, erplora_seal):
    respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    assert call(client, "submit", payload(), v2=True).status_code == 200


def test_a_v2_signature_of_another_door_is_unauthorized(
    client, respx_mock, erplora_seal
):
    data = json.dumps(payload()).encode()
    headers = signed_headers(
        "POST", "/internal/verifactu/query", data, int(time.time()), SECRET
    )

    response = client.post(
        "/internal/verifactu/submit",
        data,
        content_type="application/json",
        headers=headers,
    )

    assert error_of(response) == (401, "unauthorized")
    assert not respx_mock.calls


def test_only_post_is_allowed(client):
    response = client.get("/internal/verifactu/submit")

    assert error_of(response) == (405, "method_not_allowed")
    assert response["Allow"] == "POST"


# The headers before the body


def plausible_headers(**changes):
    """A fresh timestamp and a signature that only the body could prove wrong."""
    return {
        "X-Erplora-Timestamp": str(int(time.time())),
        "X-Erplora-Signature": "0" * 64,
        **changes,
    }


class UnreadableBody(io.RawIOBase):
    """A body the view must never read: reading it fails the test."""

    def readable(self):
        return True

    def readinto(self, buffer):
        raise AssertionError("the body was read")


@pytest.mark.parametrize("door", ["submit", "query", "probe"])
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Erplora-Timestamp": str(int(time.time()))},
        {"X-Erplora-Signature": "0" * 64, "X-Erplora-Signature-V2": "0" * 64},
        plausible_headers(**{"X-Erplora-Timestamp": str(int(time.time()) - 3600)}),
        plausible_headers(**{"X-Erplora-Timestamp": str(int(time.time()) + 3600)}),
        plausible_headers(**{"X-Erplora-Timestamp": "9" * 5000}),
    ],
    ids=[
        "no headers",
        "no signature",
        "no timestamp",
        "stale",
        "future",
        "too many digits",
    ],
)
def test_a_call_that_cannot_be_signed_is_401_before_its_body_is_read(headers, door):
    """Up to 10 MiB are read only for a call that may be signed."""
    request = RequestFactory().post(
        f"/internal/verifactu/{door}",
        b"{}",
        content_type="application/json",
        headers=headers,
    )
    request._stream = UnreadableBody()
    request.META["CONTENT_LENGTH"] = str(internal.MAX_BODY_BYTES)

    response = getattr(internal, door)(request)

    assert response.status_code == 401
    assert json.loads(response.content)["error"]["code"] == "unauthorized"


def test_a_timestamp_of_too_many_digits_is_401_not_a_crash(client, respx_mock):
    data = json.dumps(payload()).encode()

    response = client.post(
        "/internal/verifactu/submit",
        data,
        content_type="application/json",
        headers=plausible_headers(**{"X-Erplora-Timestamp": "9" * 5000}),
    )

    assert error_of(response) == (401, "unauthorized")
    assert not respx_mock.calls
