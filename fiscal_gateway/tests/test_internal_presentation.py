"""``/internal/verifactu/submit|query``: what the gateway presents and the answer it gives back, its cap on
presentations at once, and a customer's certificate that never reaches a log. Only the AEAT's preproduction is
ever reached, through ``respx``."""

import logging
import ssl

import httpx
import pytest

from base.tests.conftest import names_the_file
from fiscal_gateway import internal
from fiscal_gateway.tests.conftest import HUB, HUB_SLUG, b64, fixture, make_p12
from fiscal_gateway.tests.internal_calls import (
    ANSWER,
    PRE_HOLDER,
    PRE_SEAL,
    SENT,
    _free_slots,
    call,
    error_of,
    log_text,
    own,
    payload,
)

pytestmark = pytest.mark.usefixtures("_known_business", "_secrets")


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
    # The Hub sends ``ctx.scope.key``, the slug of its host; the registry's UUID names it too.
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


@pytest.mark.parametrize("door", ["submit", "query"])
@pytest.mark.parametrize("route", ["erplora", "own"])
def test_without_the_servers_certificates_nothing_is_sent_and_the_file_is_named(
    client, respx_mock, erplora_seal, own_p12, unreadable_ca, caplog, door, route
):
    """The gateway's own configuration, not the AEAT: ``502 aeat_unreachable`` with ``sent: false``, which the
    Hub keeps in its queue and retries, never a mute 500. It is logged once, in ``base.tls``'s ERROR line naming
    the gateway, never in a copy of its own."""
    body = payload() if route == "erplora" else own(own_p12)

    with caplog.at_level(logging.ERROR):
        response = call(client, door, body)

    assert response.status_code == 502
    error = response.json()["error"]
    assert (error["code"], error["sent"]) == ("aeat_unreachable", False)
    assert names_the_file(error["message"], unreadable_ca)
    (line,) = [record for record in caplog.records if "trust_store_unreadable" in record.getMessage()]
    assert (line.name, line.levelno) == ("base.tls", logging.ERROR)
    assert "caller=fiscal_gateway.aeat " in line.getMessage()
    assert names_the_file(line.getMessage(), unreadable_ca)
    assert not respx_mock.calls


# Concurrency


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

    logged = log_text(caplog)
    assert caplog.records
    for secret in (
        "pw-7f3a9c",
        "wrong-pw-91b2",
        b64(p12)[:60],
        b64(p12)[-60:],
        "PRIVATE KEY",
    ):
        assert secret not in logged
