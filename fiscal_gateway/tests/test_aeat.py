"""``fiscal_gateway.aeat``: which AEAT door, whose envelope, and the presentation itself (FISCAL-F02).

Only the AEAT's preproduction is ever reached, through ``respx``: no test opens a connection, and the
production endpoints are checked as strings only. The envelopes are the Hub's (``fixtures/``, copied
byte for byte from hub-next).
"""

import asyncio
import dataclasses
import logging
import os
import ssl
import stat
import time

import httpx
import pytest

from base.tests.conftest import names_the_file
from fiscal_gateway import aeat, seal
from fiscal_gateway.tests.conftest import (
    PASSWORD,
    b64,
    fixture,
    make_p12,
)

PATH = "/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
PRE_SEAL = f"https://prewww10.aeat.es{PATH}"
PRE_HOLDER = f"https://prewww1.aeat.es{PATH}"
SENT = fixture("rotation_a_sent_2026-09-22.xml")
ISSUER = "B27593136"


def query_envelope(nif: str) -> str:
    """A ``ConsultaFactuSistemaFacturacion`` as the Hub builds it (``apps/verifactu/envelope.py``)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"'
        ' xmlns:con="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/ConsultaLR.xsd"'
        ' xmlns:sum1="https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd">'
        "<soapenv:Header/><soapenv:Body><con:ConsultaFactuSistemaFacturacion>"
        "<con:Cabecera><sum1:IDVersion>1.0</sum1:IDVersion><sum1:ObligadoEmision>"
        f"<sum1:NombreRazon>ACME SL</sum1:NombreRazon><sum1:NIF>{nif}</sum1:NIF>"
        "</sum1:ObligadoEmision></con:Cabecera>"
        "<con:FiltroConsulta><con:PeriodoImputacion><sum1:Ejercicio>2026</sum1:Ejercicio>"
        "<sum1:Periodo>09</sum1:Periodo></con:PeriodoImputacion></con:FiltroConsulta>"
        "</con:ConsultaFactuSistemaFacturacion></soapenv:Body></soapenv:Envelope>"
    )


def test_a_seal_goes_through_the_entities_door():
    assert aeat.endpoint("testing", "seal") == PRE_SEAL
    assert (
        aeat.endpoint("production", "seal")
        == f"https://www10.agenciatributaria.gob.es{PATH}"
    )


def test_every_other_certificate_goes_through_the_holders_door():
    assert (
        aeat.endpoint("production", "representative")
        == f"https://www1.agenciatributaria.gob.es{PATH}"
    )
    assert aeat.endpoint("testing", "personal") == PRE_HOLDER
    assert aeat.endpoint("testing", "unknown") == PRE_HOLDER


def test_an_unknown_environment_has_no_door():
    with pytest.raises(ValueError):
        aeat.endpoint("staging", "seal")


def test_the_hubs_envelope_belongs_to_its_issuer():
    assert aeat.nif_matches(SENT, ISSUER) is True
    assert aeat.nif_matches(SENT, " b27593136 ") is True
    assert aeat.nif_matches(SENT, "B12345674") is False


def test_an_envelope_with_two_issuers_matches_none():
    first = "<sum1:IDEmisorFactura>B27593136</sum1:IDEmisorFactura>"
    two_issuers = SENT.replace(
        first, "<sum1:IDEmisorFactura>B99999999</sum1:IDEmisorFactura>", 1
    )

    assert aeat.nif_matches(two_issuers, ISSUER) is False
    assert aeat.nif_matches(two_issuers, "B99999999") is False


def test_the_header_obligado_must_be_the_issuer_too():
    other_obligado = SENT.replace(
        "<sum1:NIF>B27593136</sum1:NIF></sum1:ObligadoEmision>",
        "<sum1:NIF>B99999999</sum1:NIF></sum1:ObligadoEmision>",
    )

    assert aeat.nif_matches(other_obligado, ISSUER) is False


def test_the_recipient_and_the_software_do_not_count():
    with_recipient = SENT.replace(
        "<sum1:Desglose>",
        "<sum1:Destinatarios><sum1:IDDestinatario><sum1:NombreRazon>OTRA SL</sum1:NombreRazon>"
        "<sum1:NIF>B99999999</sum1:NIF></sum1:IDDestinatario></sum1:Destinatarios><sum1:Desglose>",
    ).replace(
        "<sum1:NIF>B27593136</sum1:NIF><sum1:NombreSistemaInformatico>",
        "<sum1:NIF>B88888888</sum1:NIF><sum1:NombreSistemaInformatico>",
    )

    assert aeat.nif_matches(with_recipient, ISSUER) is True


def test_a_query_is_matched_by_its_obligado():
    assert aeat.nif_matches(query_envelope(ISSUER), ISSUER) is True
    assert aeat.nif_matches(query_envelope("B99999999"), ISSUER) is False


def test_an_annulment_is_matched_by_the_annulled_invoices_issuer():
    def annulment(issuer: str) -> str:
        start = SENT.index("<sum1:RegistroAlta>")
        end = SENT.index("</sum1:RegistroAlta>") + len("</sum1:RegistroAlta>")
        return (
            SENT[:start]
            + "<sum1:RegistroAnulacion><sum1:IDVersion>1.0</sum1:IDVersion><sum1:IDFactura>"
            f"<sum1:IDEmisorFacturaAnulada>{issuer}</sum1:IDEmisorFacturaAnulada>"
            "<sum1:NumSerieFacturaAnulada>A-1</sum1:NumSerieFacturaAnulada>"
            "<sum1:FechaExpedicionFacturaAnulada>22-09-2026</sum1:FechaExpedicionFacturaAnulada>"
            "</sum1:IDFactura></sum1:RegistroAnulacion>" + SENT[end:]
        )

    assert aeat.nif_matches(annulment(ISSUER), ISSUER) is True
    assert aeat.nif_matches(annulment("B99999999"), ISSUER) is False


def test_an_envelope_naming_nobody_matches_nobody():
    empty = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soapenv:Body/></soapenv:Envelope>"
    )

    assert aeat.nif_matches(empty, ISSUER) is False
    assert aeat.nif_matches(SENT, "") is False


def test_a_nif_in_another_namespace_does_not_count():
    foreign = SENT.replace(
        "<sum1:NumSerieFactura>ROT",
        '<x:IDEmisorFactura xmlns:x="urn:other">B99999999</x:IDEmisorFactura>'
        "<sum1:NumSerieFactura>ROT",
        1,
    )

    assert foreign != SENT
    assert aeat.nif_matches(foreign, ISSUER) is True


def test_malformed_xml_or_a_doctype_matches_nobody():
    doctype = SENT.replace(
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE x [<!ENTITY nif "B27593136">]>',
    )

    assert aeat.nif_matches(doctype, ISSUER) is False
    assert aeat.nif_matches(SENT[:-40], ISSUER) is False


@pytest.fixture
def identity():
    return seal.load(b64(make_p12()), PASSWORD)


@pytest.fixture
def private_tmp(tmp_path, monkeypatch):
    """Where ``tempfile`` writes during the test, to see what the presentation leaves behind."""
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    return tmp_path


def test_present_posts_the_exact_bytes_and_returns_the_answer_as_it_came(
    identity, respx_mock, private_tmp
):
    answer_body = fixture("rotation_a_2026-09-22.xml")
    route = respx_mock.post(PRE_HOLDER).respond(
        200, text=answer_body, headers={"Content-Type": "text/xml;charset=UTF-8"}
    )

    answer = aeat.present(identity, "testing", SENT, operation="submit")

    assert answer == aeat.Answer(status=200, body=answer_body)
    request = route.calls.last.request
    assert request.content == SENT.encode("utf-8")
    assert request.headers["Content-Type"] == "text/xml;charset=UTF-8"
    assert request.headers["SOAPAction"] == ""


def test_an_aeat_error_status_is_still_an_answer(identity, respx_mock):
    respx_mock.post(PRE_HOLDER).respond(500, text="<soap:Fault/>")

    assert aeat.present(identity, "testing", SENT, operation="query") == aeat.Answer(
        status=500, body="<soap:Fault/>"
    )


def test_the_key_lives_in_private_temporary_files_deleted_after_use(
    identity, respx_mock, private_tmp, monkeypatch
):
    respx_mock.post(PRE_HOLDER).respond(200, text="<ok/>")
    seen = []
    original = ssl.SSLContext.load_cert_chain

    def spy(context, certfile, keyfile=None, password=None):
        seen.append(
            (
                stat.S_IMODE(os.stat(certfile).st_mode),
                stat.S_IMODE(os.stat(keyfile).st_mode),
            )
        )
        return original(context, certfile, keyfile, password)

    monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", spy)

    aeat.present(identity, "testing", SENT, operation="submit")

    assert seen == [(0o600, 0o600)]
    assert list(private_tmp.iterdir()) == []


def test_the_temporary_files_go_even_when_the_aeat_is_not_reached(
    identity, respx_mock, private_tmp
):
    respx_mock.post(PRE_HOLDER).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(aeat.AeatUnreachable):
        aeat.present(identity, "testing", SENT, operation="submit")

    assert list(private_tmp.iterdir()) == []


def test_a_key_that_is_not_the_certificates_is_refused_before_the_aeat(
    identity, respx_mock, private_tmp
):
    stranger = seal.load(b64(make_p12()), PASSWORD)
    mismatched = dataclasses.replace(identity, key_pem=stranger.key_pem)

    with pytest.raises(seal.SealInvalid) as invalid:
        aeat.present(mismatched, "testing", SENT, operation="submit")

    assert invalid.value.__suppress_context__
    assert str(private_tmp) not in str(invalid.value)
    assert not respx_mock.calls
    assert list(private_tmp.iterdir()) == []


def test_a_seal_presents_through_the_entities_door(respx_mock):
    sealed = seal.load(b64(make_p12(serial=None, eseal=True)), PASSWORD)
    route = respx_mock.post(PRE_SEAL).respond(200, text="<ok/>")

    aeat.present(sealed, "testing", SENT, operation="submit")

    assert route.called


def test_a_read_timeout_means_the_request_may_have_arrived(identity, respx_mock):
    respx_mock.post(PRE_HOLDER).mock(side_effect=httpx.ReadTimeout("no answer"))

    with pytest.raises(aeat.AeatUnreachable) as unreachable:
        aeat.present(identity, "testing", SENT, operation="submit")

    assert unreachable.value.sent is True


def test_a_refused_connection_means_nothing_was_sent(identity, respx_mock):
    respx_mock.post(PRE_HOLDER).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(aeat.AeatUnreachable) as unreachable:
        aeat.present(identity, "testing", SENT, operation="submit")

    assert unreachable.value.sent is False


def test_a_connect_timeout_means_nothing_was_sent(identity, respx_mock):
    respx_mock.post(PRE_HOLDER).mock(side_effect=httpx.ConnectTimeout("slow"))

    with pytest.raises(aeat.AeatUnreachable) as unreachable:
        aeat.present(identity, "testing", SENT, operation="submit")

    assert unreachable.value.sent is False


def test_the_four_timeouts_are_set_five_to_connect_thirty_to_read_and_short_to_write_and_wait():
    """PLAN-SAAS §4 (round 2026-10-15c) and PLAN §28: gateway → AEAT, 5 s to connect and 30 s to read. httpx
    takes one figure for every phase it is not told otherwise, so writing the envelope and waiting for a
    connection are set too, short: the envelope is a few kilobytes and each submission opens its own client."""
    assert aeat.TIMEOUT.connect == 5
    assert aeat.TIMEOUT.read == 30
    assert aeat.TIMEOUT.write == 5
    assert aeat.TIMEOUT.pool == 1


def test_the_gateway_gives_up_on_the_aeat_before_the_hub_gives_up_on_the_gateway():
    """The Hub reads the gateway for 45 s (``HUB_READ_SECONDS``, its ``apps/verifactu/gateway.py``, which the
    SaaS cannot import: another repository). Waiting longer for the AEAT, the Hub would give up first and treat
    as unknown a record the gateway did present. httpx's timeouts are per operation (the read one, per chunk
    received), so no sum of them bounds a submission: the deadline does, and an exchange that takes every
    phase's whole time still fits in it, with room before the Hub's for the checks around it."""
    phases = aeat.TIMEOUT.connect + aeat.TIMEOUT.write + aeat.TIMEOUT.read + aeat.TIMEOUT.pool

    assert phases <= aeat.DEADLINE_SECONDS
    assert aeat.HUB_READ_SECONDS - aeat.DEADLINE_SECONDS >= 4


def test_an_answer_slower_than_the_deadline_is_cut_and_may_have_arrived(identity, respx_mock, monkeypatch):
    """However the AEAT dribbles its answer, the submission ends at the deadline: as a read timeout, the
    request left, so the Hub resends the same bytes (the AEAT answers «duplicado» if it had them)."""

    async def dribbles(request):
        await asyncio.sleep(2)
        return httpx.Response(200, text="<late/>")

    monkeypatch.setattr(aeat, "DEADLINE_SECONDS", 0.2)
    respx_mock.post(PRE_HOLDER).mock(side_effect=dribbles)
    started = time.monotonic()

    with pytest.raises(aeat.AeatUnreachable) as unreachable:
        aeat.present(identity, "testing", SENT, operation="submit")

    assert unreachable.value.sent is True
    assert time.monotonic() - started < 1.5


# The server's trusted certificates (FIX-SAAS-FISCAL-GATEWAY-AEAT-TLS-CRASHES-WHEN-SSL-CERT-FILE-MISSING)
#
# FIX-SAAS-FISCAL-GATEWAY-OWN-TRUST-STORE-COPY-INSTEAD-OF-BASE-TLS: they are read by ``base.tls``, the one place every
# outgoing call of the SaaS reads them, never by a copy of the gateway's own: one ERROR line, ``base.tls``'s, naming
# the caller.


def the_trust_store_line(caplog, path) -> None:
    """The single ERROR line of the unreadable certificates is ``base.tls``'s, naming the gateway, the setting and
    its file: nothing of the gateway logs them a second time."""
    (line,) = [record for record in caplog.records if "trust_store_unreadable" in record.getMessage()]
    assert (line.name, line.levelno) == ("base.tls", logging.ERROR)
    assert "caller=fiscal_gateway.aeat " in line.getMessage()
    assert names_the_file(line.getMessage(), path)


def test_without_the_servers_certificates_the_tls_context_fails_naming_the_file(
    identity, unreadable_ca, caplog
):
    with caplog.at_level(logging.ERROR), pytest.raises(aeat.TrustStoreUnreadable) as raised:
        aeat.tls_context(identity)

    assert raised.value.sent is False
    assert raised.value.__suppress_context__
    assert names_the_file(str(raised.value), unreadable_ca)
    the_trust_store_line(caplog, unreadable_ca)


def test_ssl_cert_file_naming_a_folder_is_unreadable_too(identity, tmp_path, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path))
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    with pytest.raises(aeat.TrustStoreUnreadable) as raised:
        aeat.tls_context(identity)

    assert raised.value.sent is False
    assert names_the_file(str(raised.value), tmp_path)


def test_a_presentation_without_the_servers_certificates_sends_nothing(
    identity, unreadable_ca, respx_mock, private_tmp, caplog
):
    """Nothing left this process: the Hub keeps the record and retries it in its own cycle, without duplicating it."""
    with caplog.at_level(logging.ERROR), pytest.raises(aeat.AeatUnreachable) as raised:
        aeat.present(identity, "testing", SENT, operation="submit")

    assert isinstance(raised.value, aeat.TrustStoreUnreadable)
    assert raised.value.sent is False
    assert names_the_file(str(raised.value), unreadable_ca)
    the_trust_store_line(caplog, unreadable_ca)
    assert not respx_mock.calls
    assert not list(private_tmp.glob("fiscal-gateway-*"))


def test_a_presentation_uses_the_trusted_certificates_it_read(identity, respx_mock, ca_gone_after_one_read):
    """The client takes the context ``tls_context`` built (``verify=``): the certificates are read once per
    presentation, so a file renewed between that reading and the POST never breaks it."""
    respx_mock.post(PRE_HOLDER).mock(return_value=httpx.Response(200, text="<ok/>"))

    answer = aeat.present(identity, "testing", SENT, operation="submit")

    assert answer == aeat.Answer(status=200, body="<ok/>")
    assert not ca_gone_after_one_read.exists()


def test_without_ssl_cert_file_the_failure_of_the_bundled_certificates_is_told_too(
    identity, tmp_path, monkeypatch
):
    import certifi

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(certifi, "where", lambda: str(tmp_path / "gone.pem"))

    with pytest.raises(aeat.TrustStoreUnreadable) as raised:
        aeat.tls_context(identity)

    assert raised.value.sent is False
    assert "the default certificates" in str(raised.value)
