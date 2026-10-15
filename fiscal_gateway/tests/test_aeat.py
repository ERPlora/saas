"""``fiscal_gateway.aeat``: which AEAT door, whose envelope, and the presentation itself.

Only the AEAT's preproduction is ever reached, through ``respx``: no test opens a connection, and the
production endpoints are checked as strings only. The envelopes are the Hub's (``fixtures/``, copied
byte for byte from hub-next).
"""

import os
import ssl
import stat

import httpx
import pytest

from fiscal_gateway import aeat, seal
from fiscal_gateway.tests.conftest import PASSWORD, b64, fixture, make_p12

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


def test_the_timeouts_are_ten_seconds_to_connect_and_sixty_to_read():
    assert aeat.TIMEOUT.connect == 10
    assert aeat.TIMEOUT.read == 60
