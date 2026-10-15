"""``POST /internal/verifactu/submit|query|probe``: the Hub hands the gateway an envelope to present.

Server to server, signed as every ``/internal`` call (``accounts.signing``: v1 or v2, five minutes, the
current or the previous secret), so no CSRF token. The body is ``{"hub", "nif", "environment", "route",
"envelope", "certificate"?}`` (contract 3 of the fiscal block, PLAN-SAAS §2.2): ``route=erplora``
presents with ERPlora's seal, ``route=own`` with the customer's certificate, which comes in the call
and is never kept nor logged. The AEAT's answer goes back as it came; the refusals answer the single
envelope ``{"error": {"code", "message"}}``. Only the AEAT's preproduction is ever reached, through
``respx``.

The gateway presents for a business it knows only (``hub_unknown``), and through ERPlora's seal only
for the taxpayer of the business's approved authorisation (``fiscal.RepresentationGrant``). The one
exception is the platform's hub (``PLATFORM_HUB_SLUG``, no business of the SaaS): ERPlora's own records,
in its own name, for the seal's holder only.
"""

import io
import json
import logging
import ssl
import time

import httpx
import pytest
from django.test import RequestFactory

from accounts.signing import sign, signed_headers
from fiscal.tests.conftest import make_grant
from fiscal_gateway import internal, seal
from fiscal_gateway.tests.conftest import (
    HUB,
    HUB_SLUG,
    PASSWORD,
    b64,
    fixture,
    make_p12,
)
from hubs.models import Hub

SECRET = "test-internal-secret"
PATH = "/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
PRE_SEAL = f"https://prewww10.aeat.es{PATH}"
PRE_HOLDER = f"https://prewww1.aeat.es{PATH}"
SENT = fixture("rotation_a_sent_2026-09-22.xml")
ANSWER = fixture("rotation_a_2026-09-22.xml")
ISSUER = "B27593136"
#: The platform's hub: ERPlora's own records, through its seal. No business of the SaaS bears it.
PLATFORM = "erplora"
#: A customer's NIF, and the envelope of the Hub naming it.
CUSTOMER = "B12345674"
CUSTOMER_SENT = SENT.replace(ISSUER, CUSTOMER)


@pytest.fixture(autouse=True)
def _secrets(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.PLATFORM_HUB_SLUG = PLATFORM


@pytest.fixture(autouse=True)
def _known_business(business):
    """``HUB`` is a business the SaaS knows."""


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
    """The platform's hub presenting ERPlora's own records through its seal, unless ``changes`` say."""
    body = {
        "hub": PLATFORM,
        "nif": ISSUER,
        "environment": "testing",
        "route": "erplora",
        "envelope": SENT,
    }
    body.update(changes)
    return body


def own(p12, password=PASSWORD, **changes):
    """The business ``HUB`` presenting with its own certificate."""
    return payload(
        **{
            "hub": HUB,
            "route": "own",
            "certificate": {"p12_base64": b64(p12), "password": password},
            **changes,
        }
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


@pytest.mark.parametrize("hub", ["", "Demo", "a" * 65, "x y"])
def test_a_hub_that_is_neither_a_slug_nor_a_uuid_is_invalid(client, respx_mock, hub):
    response = call(client, "submit", payload(hub=hub))

    assert error_of(response) == (422, "invalid_payload")
    assert set(response.json()["error"]["fields"]) == {"hub"}
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


def test_through_erplora_with_a_seal_tls_refuses_is_no_seal(
    client, respx_mock, settings
):
    """ERPlora's seal that TLS refuses (here, a 1024-bit key) is no usable seal, as an unreadable or
    expired one: ``seal.current()`` returns it (it opens), and the gateway refuses it before the AEAT."""
    weak = make_p12(org_id="VATES-B27593136", serial=None, eseal=True, key_size=1024)
    settings.FISCAL_SEAL_CURRENT_P12_BASE64 = b64(weak)
    settings.FISCAL_SEAL_CURRENT_PASSWORD = PASSWORD
    settings.FISCAL_SEAL_NEXT_P12_BASE64 = ""
    settings.FISCAL_SEAL_NEXT_PASSWORD = ""
    body = payload()
    probe_body = {k: v for k, v in body.items() if k != "envelope"}

    assert error_of(call(client, "submit", body)) == (409, "no_seal")
    assert call(client, "probe", probe_body).json()["ready"] is False
    assert not respx_mock.calls


def test_own_route_without_a_certificate(client, respx_mock, erplora_seal):
    response = call(client, "submit", payload(route="own", hub=HUB))

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


def test_own_route_with_a_certificate_tls_refuses_is_invalid_not_a_crash(
    client, respx_mock, caplog
):
    weak = make_p12(
        org_id="VATES-B27593136",
        serial="IDCES-12345678Z",
        key_size=1024,
        password="pw-5d1e8b",
    )

    with caplog.at_level(logging.DEBUG):
        response = call(client, "submit", own(weak, password="pw-5d1e8b"))

    assert error_of(response) == (409, "certificate_invalid")
    assert not respx_mock.calls
    assert _free_slots() == 8
    logged = caplog.text + "".join(str(record.args) for record in caplog.records)
    assert caplog.records
    for secret in ("pw-5d1e8b", b64(weak)[:60], b64(weak)[-60:], "PRIVATE KEY"):
        assert secret not in logged
        assert secret not in response.content.decode()


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


@pytest.mark.parametrize("hub", [HUB_SLUG, HUB])
def test_a_submission_names_its_hub_by_slug_or_uuid(client, respx_mock, own_p12, hub):
    # Phase 1: the Hub sends ``ctx.scope.key``, the slug of its host.
    route = respx_mock.post(PRE_HOLDER).respond(200, text=ANSWER)

    response = call(client, "submit", own(own_p12, hub=hub))

    assert response.status_code == 200
    assert response.json() == {"aeat_status": 200, "aeat_body": ANSWER}
    assert route.called


def test_a_submission_with_the_customers_certificate_goes_through_the_holders_door(
    client, respx_mock, own_p12
):
    route = respx_mock.post(PRE_HOLDER).respond(200, text=ANSWER)

    response = call(client, "submit", own(own_p12))

    assert response.json() == {"aeat_status": 200, "aeat_body": ANSWER}
    assert route.called


def test_a_submission_loads_the_certificate_into_tls_once(
    client, respx_mock, own_p12, monkeypatch
):
    respx_mock.post(PRE_HOLDER).respond(200, text=ANSWER)
    loads = []
    original = ssl.SSLContext.load_cert_chain

    def count(context, certfile, keyfile=None, password=None):
        loads.append(certfile)
        return original(context, certfile, keyfile, password)

    monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", count)

    call(client, "submit", own(own_p12))

    assert len(loads) == 1


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


# Representation: through ERPlora's seal, only for whom ERPlora may present


def customer(**changes):
    """The business ``HUB`` presenting its customer's records through ERPlora's seal."""
    return payload(
        **{"hub": HUB, "nif": CUSTOMER, "envelope": CUSTOMER_SENT, **changes}
    )


def probe_body(body):
    return {k: v for k, v in body.items() if k != "envelope"}


@pytest.mark.parametrize("hub", ["bar-paco", "0199e8a0-0000-7000-8000-0000000000ff"])
@pytest.mark.parametrize("route", ["erplora", "own"])
def test_a_business_the_saas_does_not_know_is_404_before_the_aeat(
    client, respx_mock, erplora_seal, own_p12, hub, route
):
    body = payload(hub=hub) if route == "erplora" else own(own_p12, hub=hub)

    response = call(client, "submit", body)

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls


def test_a_purged_business_is_unknown(client, respx_mock, erplora_seal, business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

    response = call(client, "submit", payload(hub=HUB))

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls


@pytest.mark.parametrize("door", ["submit", "query"])
def test_without_an_authorisation_erplora_does_not_present_for_a_customer(
    client, respx_mock, erplora_seal, door
):
    response = call(client, door, customer())

    assert error_of(response) == (409, "representation_not_approved")
    assert response.json()["error"]["message"]
    assert not respx_mock.calls


@pytest.mark.parametrize("status", ["submitted", "returned", "revoked"])
def test_an_authorisation_not_in_force_is_not_enough(
    client, respx_mock, erplora_seal, business, status
):
    make_grant(business, status=status, taxpayer_tax_id=CUSTOMER)

    response = call(client, "submit", customer())

    assert error_of(response) == (409, "representation_not_approved")
    assert not respx_mock.calls


def test_an_approval_of_another_business_is_not_enough(
    client, respx_mock, erplora_seal
):
    other = Hub.objects.create(slug="bar-paco", name="Bar Paco", country="ES")
    make_grant(other, status="approved", taxpayer_tax_id=CUSTOMER)

    response = call(client, "submit", customer())

    assert error_of(response) == (409, "representation_not_approved")
    assert not respx_mock.calls


def test_an_approval_for_another_taxpayer_is_a_nif_mismatch(
    client, respx_mock, erplora_seal, business, caplog
):
    make_grant(business, status="approved", taxpayer_tax_id="B99999999")

    with caplog.at_level(logging.DEBUG):
        response = call(client, "submit", customer())

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls
    # Nothing of the authorisation reaches the answer nor a log.
    logged = caplog.text + "".join(str(record.args) for record in caplog.records)
    assert "B99999999" not in response.content.decode()
    assert "B99999999" not in logged


@pytest.mark.parametrize("hub", [HUB_SLUG, HUB])
@pytest.mark.parametrize("door", ["submit", "query"])
def test_an_approved_authorisation_lets_erplora_present_for_its_taxpayer(
    client, respx_mock, erplora_seal, business, hub, door
):
    make_grant(business, status="approved", taxpayer_tax_id=CUSTOMER)
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, door, customer(hub=hub, nif=CUSTOMER.lower()))

    assert response.status_code == 200
    assert route.calls.last.request.content == CUSTOMER_SENT.encode("utf-8")


def test_the_platform_hub_presents_erploras_own_records_without_an_authorisation(
    client, respx_mock, erplora_seal
):
    """ERPLORA CLOUD SL files in its own name, with its own seal, from a hub that is no business of the
    SaaS."""
    assert not Hub.objects.filter(slug=PLATFORM).exists()
    route = respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    response = call(client, "submit", payload(nif=ISSUER.lower()))

    assert response.status_code == 200
    assert route.called


def test_the_platform_hub_presents_for_erplora_only(client, respx_mock, erplora_seal):
    response = call(client, "submit", customer(hub=PLATFORM))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls


def test_a_business_declaring_erploras_nif_needs_an_authorisation_too(
    client, respx_mock, erplora_seal
):
    """Only the platform's hub presents in ERPlora's name: a customer's hub never gets the seal for it."""
    response = call(client, "submit", payload(hub=HUB))

    assert error_of(response) == (409, "representation_not_approved")
    assert not respx_mock.calls


def test_a_business_declaring_erploras_nif_with_an_authorisation_of_its_own_is_a_mismatch(
    client, respx_mock, erplora_seal, business
):
    make_grant(business, status="approved", taxpayer_tax_id=CUSTOMER)

    response = call(client, "submit", payload(hub=HUB_SLUG))

    assert error_of(response) == (409, "nif_mismatch")
    assert not respx_mock.calls


def test_the_platform_hub_is_the_configured_one(
    client, settings, respx_mock, erplora_seal
):
    settings.PLATFORM_HUB_SLUG = "erplora-cloud"
    respx_mock.post(PRE_SEAL).respond(200, text=ANSWER)

    assert error_of(call(client, "submit", payload())) == (404, "hub_unknown")
    assert call(client, "submit", payload(hub="erplora-cloud")).status_code == 200


def test_the_platform_hub_has_no_exception_with_a_certificate_of_its_own(
    client, respx_mock, own_p12
):
    response = call(client, "submit", own(own_p12, hub=PLATFORM))

    assert error_of(response) == (404, "hub_unknown")
    assert not respx_mock.calls


def test_the_own_route_needs_no_authorisation(client, respx_mock):
    p12 = make_p12(org_id=f"VATES-{CUSTOMER}", serial="IDCES-12345678Z")
    respx_mock.post(PRE_HOLDER).respond(200, text=ANSWER)

    response = call(client, "submit", own(p12, nif=CUSTOMER, envelope=CUSTOMER_SENT))

    assert response.status_code == 200


def test_probe_through_erplora_without_an_authorisation_is_not_ready(
    client, respx_mock, erplora_seal
):
    response = call(client, "probe", probe_body(customer()))

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert "authorisation" in response.json()["detail"]
    assert not respx_mock.calls


def test_probe_through_erplora_with_an_approved_authorisation_is_ready(
    client, erplora_seal, business
):
    make_grant(business, status="approved", taxpayer_tax_id=CUSTOMER)

    response = call(client, "probe", probe_body(customer()))

    assert response.json()["ready"] is True


def test_probe_of_a_business_the_saas_does_not_know_is_not_ready(client, erplora_seal):
    response = call(client, "probe", probe_body(payload(hub="bar-paco")))

    assert response.status_code == 200
    assert response.json()["ready"] is False


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


def test_probe_with_a_certificate_tls_refuses_is_not_ready(client, respx_mock, caplog):
    """Like every other unusable certificate, the probe answers ``ready: false`` with the reason
    (submit/query answer 409 ``certificate_invalid``), never ``ready: true``."""
    weak = make_p12(
        org_id="VATES-B27593136",
        serial="IDCES-12345678Z",
        key_size=1024,
        password="pw-5d1e8b",
    )
    body = own(weak, password="pw-5d1e8b")
    del body["envelope"]

    with caplog.at_level(logging.DEBUG):
        response = call(client, "probe", body)

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert "TLS" in response.json()["detail"]
    assert not respx_mock.calls
    logged = caplog.text + "".join(str(record.args) for record in caplog.records)
    assert caplog.records
    for secret in ("pw-5d1e8b", b64(weak)[:60], b64(weak)[-60:], "PRIVATE KEY"):
        assert secret not in logged
        assert secret not in response.content.decode()


def test_probe_own_route_without_a_certificate_is_not_ready(client):
    body = payload(route="own", hub=HUB)
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
