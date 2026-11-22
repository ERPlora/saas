"""``/internal/verifactu/<door>``: what is refused before the AEAT, a body that is not the contract and a call
the gateway may not present."""

import logging

import pytest

from fiscal_gateway import internal
from fiscal_gateway.tests.conftest import HUB, PASSWORD, b64, make_p12
from fiscal_gateway.tests.internal_calls import (
    ANSWER,
    ISSUER,
    PRE_SEAL,
    _free_slots,
    assert_certificate_kept_out,
    call,
    error_of,
    own,
    payload,
)

pytestmark = pytest.mark.usefixtures("_known_business", "_secrets")


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
    assert_certificate_kept_out(caplog, response, weak, "pw-5d1e8b")


def test_disabled_production_permission_never_presents_to_production(
    client, settings, respx_mock, erplora_seal
):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.AEAT_PRODUCTION_ENABLED = False

    response = call(client, "submit", payload(environment="production"))

    assert error_of(response) == (409, "environment_not_allowed")
    assert not respx_mock.calls


@pytest.mark.parametrize("label", ["prod", "pre"])
@pytest.mark.parametrize("enabled", [False, True])
def test_fiscal_destination_permission_does_not_depend_on_the_label(settings, label, enabled):
    settings.ERPLORA_ENVIRONMENT = label
    settings.AEAT_PRODUCTION_ENABLED = enabled
    internal._allowed("testing")
    if enabled:
        internal._allowed("production")
    else:
        with pytest.raises(internal._Refused) as refused:
            internal._allowed("production")
        assert refused.value.code == "environment_not_allowed"
