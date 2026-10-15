"""``POST /internal/verifactu/submit|query|probe``: the Hub hands the gateway an envelope to present.

Server to server, signed as every ``/internal`` call (``accounts.signing``: v1 or v2, five minutes, the
current or the previous secret), so no CSRF token. The body is ``{"hub", "nif", "environment", "route",
"envelope", "certificate"?}`` (contract 3 of the fiscal block, PLAN-SAAS §2.2): ``route=erplora``
presents with ERPlora's seal, ``route=own`` with the customer's certificate, which comes in the call
and is never kept nor logged. The AEAT's answer goes back as it came; the refusals answer the single
envelope ``{"error": {"code", "message"}}``. Only the AEAT's preproduction is ever reached, through
``respx``.
"""

import json
import logging
import time

import httpx
import pytest

from accounts.signing import sign, signed_headers
from fiscal_gateway import internal, seal
from fiscal_gateway.tests.conftest import PASSWORD, b64, fixture, make_p12

SECRET = "test-internal-secret"
PATH = "/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
PRE_SEAL = f"https://prewww10.aeat.es{PATH}"
PRE_HOLDER = f"https://prewww1.aeat.es{PATH}"
SENT = fixture("rotation_a_sent_2026-09-22.xml")
ANSWER = fixture("rotation_a_2026-09-22.xml")
HUB = "0199e8a0-0000-7000-8000-000000000001"
ISSUER = "B27593136"


@pytest.fixture(autouse=True)
def _secrets(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
    settings.ERPLORA_ENVIRONMENT = "prod"


@pytest.fixture
def erplora_seal(settings):
    """ERPlora's seal in the CURRENT slot: an entity seal (eIDAS QcType eSeal) of ERPLORA CLOUD SL."""
    p12 = make_p12(org_id="VATES-B27593136", serial=None, eseal=True)
    settings.FISCAL_SEAL_CURRENT_P12_BASE64 = b64(p12)
    settings.FISCAL_SEAL_CURRENT_PASSWORD = PASSWORD
    settings.FISCAL_SEAL_NEXT_P12_BASE64 = ""
    settings.FISCAL_SEAL_NEXT_PASSWORD = ""
    return seal.load(b64(p12), PASSWORD)


@pytest.fixture
def own_p12():
    """A customer's own certificate: a representative of B27593136."""
    return make_p12(org_id="VATES-B27593136", serial="IDCES-12345678Z")


def payload(**changes):
    body = {
        "hub": HUB,
        "nif": ISSUER,
        "environment": "testing",
        "route": "erplora",
        "envelope": SENT,
    }
    body.update(changes)
    return body


def own(p12, password=PASSWORD, **changes):
    return payload(
        route="own",
        certificate={"p12_base64": b64(p12), "password": password},
        **changes,
    )


def call(client, door, body=None, *, secret=SECRET, signed=True, v2=False, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    path = f"/internal/verifactu/{door}"
    timestamp = int(time.time())
    headers = {}
    if signed and v2:
        headers = signed_headers("POST", path, data, timestamp, secret)
    elif signed:
        headers = {
            "X-Erplora-Timestamp": str(timestamp),
            "X-Erplora-Signature": sign(data, timestamp, secret),
        }
    return client.post(path, data, content_type="application/json", headers=headers)


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


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


# The request


def test_a_body_that_is_not_the_contract_is_invalid_without_echoing_it(
    client, respx_mock
):
    response = call(
        client,
        "submit",
        {
            "nif": ISSUER,
            "route": "own",
            "certificate": {"p12_base64": 7, "password": "hunter2"},
        },
    )

    assert error_of(response) == (422, "invalid_payload")
    assert {"hub", "environment", "envelope", "certificate.p12_base64"} <= set(
        response.json()["error"]["fields"]
    )
    assert "hunter2" not in response.content.decode()
    assert not respx_mock.calls


def test_a_body_that_is_not_json_is_invalid(client):
    assert error_of(call(client, "submit", raw=b"{nope")) == (422, "invalid_payload")


def test_a_body_over_the_gateways_limit_is_refused(client, monkeypatch, respx_mock):
    monkeypatch.setattr(internal, "MAX_BODY_BYTES", 1000)

    response = call(client, "submit", payload())

    assert error_of(response) == (413, "payload_too_large")
    assert not respx_mock.calls


def test_a_big_submission_is_not_bound_by_djangos_form_limit(
    client, settings, respx_mock, erplora_seal
):
    """A thousand records weigh more than Django's 2.5 MB: the gateway has its own limit."""
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 1000
    respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    assert call(client, "submit", payload()).status_code == 200


# Refusals: nothing reaches the AEAT


def test_an_envelope_of_another_taxpayer_is_refused_before_the_aeat(
    client, respx_mock, erplora_seal
):
    response = call(client, "submit", payload(nif="B12345674"))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls


def test_a_query_of_another_taxpayer_is_refused_too(client, respx_mock, erplora_seal):
    response = call(client, "query", payload(nif="B12345674"))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls


def test_through_erplora_without_a_seal(client, respx_mock, no_seal):
    response = call(client, "submit", payload())

    assert error_of(response) == (409, "no_seal")
    assert not respx_mock.calls


def test_own_route_without_a_certificate(client, respx_mock, erplora_seal):
    response = call(client, "submit", payload(route="own"))

    assert error_of(response) == (409, "no_certificate")
    assert not respx_mock.calls


def test_own_route_with_a_certificate_its_password_does_not_open(
    client, respx_mock, own_p12
):
    response = call(client, "submit", own(own_p12, password="hunter2"))

    assert error_of(response) == (409, "certificate_invalid")
    assert "hunter2" not in response.content.decode()
    assert not respx_mock.calls


def test_own_route_with_an_expired_certificate(client, respx_mock):
    expired = make_p12(org_id="VATES-B27593136", serial="IDCES-12345678Z", days=-1)

    response = call(client, "submit", own(expired))

    assert error_of(response) == (409, "certificate_invalid")
    assert not respx_mock.calls


def test_own_route_with_a_certificate_without_client_authentication(client, respx_mock):
    no_client = make_p12(org_id="VATES-B27593136", client_auth=False)

    assert error_of(call(client, "submit", own(no_client))) == (
        409,
        "certificate_invalid",
    )
    assert not respx_mock.calls


def test_the_pre_deployment_never_presents_to_production(
    client, settings, respx_mock, erplora_seal
):
    settings.ERPLORA_ENVIRONMENT = "pre"

    response = call(client, "submit", payload(environment="production"))

    assert error_of(response) == (409, "environment_not_allowed")
    assert not respx_mock.calls


# Presentation


def test_a_submission_through_erplora_returns_the_aeats_answer_as_it_came(
    client, respx_mock, erplora_seal
):
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, "submit", payload())

    assert response.status_code == 200
    assert response.json() == {"aeat_status": 200, "aeat_body": ANSWER}
    assert route.calls.last.request.content == SENT.encode("utf-8")
    assert "no-store" in response["Cache-Control"]


def test_a_submission_with_the_customers_certificate_goes_through_the_holders_door(
    client, respx_mock, own_p12
):
    route = respx_mock.post(PRE_HOLDER).respond(200, text=ANSWER)

    response = call(client, "submit", own(own_p12))

    assert response.json() == {"aeat_status": 200, "aeat_body": ANSWER}
    assert route.called


def test_a_query_returns_the_aeats_answer(client, respx_mock, erplora_seal):
    consulted = fixture("consulta_preproduccion_2026-08-01.xml")
    respx_mock.post(PRE_SEAL).respond(200, text=consulted)

    response = call(client, "query", payload())

    assert response.json() == {"aeat_status": 200, "aeat_body": consulted}


def test_an_aeat_error_is_still_its_answer(client, respx_mock, erplora_seal):
    respx_mock.post(PRE_SEAL).respond(500, text="<env:Fault/>")

    response = call(client, "submit", payload())

    assert (response.status_code, response.json()) == (
        200,
        {"aeat_status": 500, "aeat_body": "<env:Fault/>"},
    )


def test_no_answer_after_the_request_left_is_502_sent(client, respx_mock, erplora_seal):
    respx_mock.post(PRE_SEAL).mock(side_effect=httpx.ReadTimeout("no answer"))

    response = call(client, "submit", payload())

    assert response.status_code == 502
    error = response.json()["error"]
    assert (error["code"], error["sent"]) == ("aeat_unreachable", True)


def test_a_refused_connection_is_502_not_sent(client, respx_mock, erplora_seal):
    respx_mock.post(PRE_SEAL).mock(side_effect=httpx.ConnectError("refused"))

    response = call(client, "submit", payload())

    assert response.status_code == 502
    assert response.json()["error"]["sent"] is False


# Concurrency


def _free_slots() -> int:
    taken = 0
    while internal.SLOTS.acquire(blocking=False):
        taken += 1
    for _ in range(taken):
        internal.SLOTS.release()
    return taken


def test_the_gateway_is_capped_at_its_concurrency(settings):
    assert settings.VERIFACTU_GATEWAY_CONCURRENCY == 8
    assert _free_slots() == 8


def test_a_full_gateway_answers_busy_without_presenting(
    client, respx_mock, erplora_seal
):
    taken = 0
    while internal.SLOTS.acquire(blocking=False):
        taken += 1
    try:
        response = call(client, "submit", payload())
    finally:
        for _ in range(taken):
            internal.SLOTS.release()

    assert error_of(response) == (503, "gateway_busy")
    assert not respx_mock.calls


def test_a_slot_is_given_back_whatever_the_aeat_did(client, respx_mock, erplora_seal):
    respx_mock.post(PRE_SEAL).mock(
        side_effect=[httpx.ReadTimeout("no answer"), httpx.Response(200, text=ANSWER)]
    )

    call(client, "submit", payload())
    call(client, "submit", payload())

    assert _free_slots() == 8


# Probe


def test_probe_through_erplora_names_the_seal_without_touching_the_aeat(
    client, respx_mock, erplora_seal
):
    response = call(
        client, "probe", {k: v for k, v in payload().items() if k != "envelope"}
    )

    expires = erplora_seal.expires_at.date().isoformat()
    assert response.json() == {
        "ready": True,
        "detail": f"seal B27593136, expires {expires}",
    }
    assert not respx_mock.calls


def test_probe_without_a_seal_is_not_ready(client, no_seal):
    response = call(
        client, "probe", {k: v for k, v in payload().items() if k != "envelope"}
    )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["detail"]


def test_probe_with_the_customers_certificate(client, own_p12):
    body = own(own_p12)
    del body["envelope"]

    assert call(client, "probe", body).json()["ready"] is True


def test_probe_with_an_unusable_certificate_is_not_ready(client, own_p12):
    body = own(own_p12, password="hunter2")
    del body["envelope"]

    response = call(client, "probe", body)

    assert response.json()["ready"] is False
    assert "hunter2" not in response.content.decode()


def test_probe_own_route_without_a_certificate_is_not_ready(client):
    body = payload(route="own")
    del body["envelope"]

    assert call(client, "probe", body).json()["ready"] is False


def test_probe_of_production_from_pre_is_not_ready(client, settings, erplora_seal):
    settings.ERPLORA_ENVIRONMENT = "pre"
    body = payload(environment="production")
    del body["envelope"]

    assert call(client, "probe", body).json()["ready"] is False


def test_probe_needs_a_signature(client, erplora_seal):
    body = payload()
    del body["envelope"]

    assert error_of(call(client, "probe", body, signed=False)) == (401, "unauthorized")


# Secrets


def test_the_customers_certificate_never_reaches_a_log(client, respx_mock, caplog):
    p12 = make_p12(
        org_id="VATES-B27593136", serial="IDCES-12345678Z", password="pw-7f3a9c"
    )
    respx_mock.post(PRE_HOLDER).mock(
        side_effect=[httpx.Response(200, text=ANSWER), httpx.ReadTimeout("no answer")]
    )

    with caplog.at_level(logging.DEBUG):
        call(client, "submit", own(p12, password="pw-7f3a9c"))
        call(client, "submit", own(p12, password="pw-7f3a9c"))
        call(client, "submit", own(p12, password="wrong-pw-91b2"))
        call(client, "submit", own(p12, password="pw-7f3a9c", nif="B12345674"))
        body = own(p12, password="pw-7f3a9c")
        del body["envelope"]
        call(client, "probe", body)

    logged = caplog.text + "".join(str(record.args) for record in caplog.records)
    assert caplog.records
    for secret in (
        "pw-7f3a9c",
        "wrong-pw-91b2",
        b64(p12)[:60],
        b64(p12)[-60:],
        "PRIVATE KEY",
    ):
        assert secret not in logged
