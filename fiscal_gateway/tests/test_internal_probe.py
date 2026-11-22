"""``/internal/verifactu/probe``: whether a presentation would leave now, answered without touching the AEAT."""

import logging

import pytest

from base.tests.conftest import names_the_file
from fiscal_gateway.tests.conftest import HUB, make_p12
from fiscal_gateway.tests.internal_calls import (
    assert_certificate_kept_out,
    call,
    error_of,
    own,
    payload,
    probe_body,
)

pytestmark = pytest.mark.usefixtures("_known_business", "_secrets")


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
    assert_certificate_kept_out(caplog, response, weak, "pw-5d1e8b")


@pytest.mark.parametrize("route", ["erplora", "own"])
def test_probe_without_the_servers_certificates_is_not_ready_and_names_the_file(
    client, respx_mock, erplora_seal, own_p12, unreadable_ca, route
):
    """The probe's own answer for a presentation that would not leave now: ``ready: false`` and why."""
    body = probe_body(payload() if route == "erplora" else own(own_p12))

    response = call(client, "probe", body)

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert names_the_file(response.json()["detail"], unreadable_ca)
    assert not respx_mock.calls


def test_probe_own_route_without_a_certificate_is_not_ready(client):
    body = payload(route="own", hub=HUB)
    del body["envelope"]

    assert call(client, "probe", body).json()["ready"] is False


def test_probe_without_production_permission_is_not_ready(client, settings, erplora_seal):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.AEAT_PRODUCTION_ENABLED = False
    body = payload(environment="production")
    del body["envelope"]

    assert call(client, "probe", body).json()["ready"] is False


def test_probe_needs_a_signature(client, erplora_seal):
    body = payload()
    del body["envelope"]

    assert error_of(call(client, "probe", body, signed=False)) == (401, "unauthorized")
