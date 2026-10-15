"""The AEAT side of the gateway: which door, whose envelope, and the presentation itself.

``endpoint(environment, kind)``: the AEAT opens two doors to VeriFactu's SOAP service, ``www10`` for
entity seals and ``www1`` for everybody else (a company's representative, a person, or a certificate
whose kind is not proven), each with its preproduction (``prewww10.aeat.es``, ``prewww1.aeat.es``).

``nif_matches(envelope, nif)``: whether every taxpayer the envelope names is ``nif``, the business the
Hub declares. The gateway presents for many businesses with one seal, so an envelope carrying somebody
else's NIF would be filed under the wrong taxpayer, and the AEAT would accept it. Only the fields that
name the taxpayer count, in the AEAT's ``SuministroInformacion`` namespace: the header's
``ObligadoEmision/NIF`` and every ``IDEmisorFactura`` and ``IDEmisorFacturaAnulada`` (not the
recipient's, the software's or the representative's NIF). An envelope that names none, cannot be parsed
or carries a DOCTYPE (which turns a parser into a way to read files and reach the network) matches
nobody. The bytes are never modified.

``present(identity, environment, envelope, operation=…)``: POSTs the Hub's exact bytes over mutual TLS
and returns the AEAT's answer as it came (``Answer``): any HTTP answer is a delivery, and reading it is
the Hub's job. Only the transport's own failures are classified (``AeatUnreachable.sent``):

- nothing left this process (connection refused, connection timeout, TLS refused): ``sent=False``,
  the Hub may retry freely;
- the request left and no answer came back (read timeout, connection lost): ``sent=True``, the AEAT may
  have registered it, and the Hub resends the same bytes (the AEAT answers «duplicado» if it had them).

httpx cannot take a key from memory, so the certificate and its key go to two files of mode 0600 in a
private temporary directory, which goes as soon as TLS has read them, whatever happens. A certificate
TLS refuses (its key is not the certificate's, or is too weak for OpenSSL's security level) raises
``SealInvalid`` before anything leaves (``tls_context``, which the gateway calls first so that it can
refuse it, and probe it, without presenting). Headers as the proven client of the gateway this one
replaces: ``Content-Type: text/xml;charset=UTF-8`` and ``SOAPAction: ""`` (the WSDL's, for both
operations). 10 s to connect and 60 s to read.
"""

import logging
import os
import ssl
import tempfile
from dataclasses import dataclass
from typing import Literal
from xml.parsers import expat

import httpx

from fiscal_gateway.seal import Identity, SealInvalid

logger = logging.getLogger(__name__)

PATH = "/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
HOSTS = {
    ("testing", True): "prewww10.aeat.es",
    ("testing", False): "prewww1.aeat.es",
    ("production", True): "www10.agenciatributaria.gob.es",
    ("production", False): "www1.agenciatributaria.gob.es",
}
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
HEADERS = {"Content-Type": "text/xml;charset=UTF-8", "SOAPAction": ""}
OPERATIONS = ("submit", "query")

SUMINISTRO_INFORMACION = (
    "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/"
    "tike/cont/ws/SuministroInformacion.xsd"
)
_ISSUERS = {"IDEmisorFactura", "IDEmisorFacturaAnulada"}


@dataclass(frozen=True)
class Answer:
    """The AEAT's answer as it came: its HTTP status and its body."""

    status: int
    body: str


class AeatUnreachable(Exception):
    """No answer from the AEAT. ``sent``: whether the request may have reached it."""

    def __init__(self, message: str, *, sent: bool):
        super().__init__(message)
        self.sent = sent


def endpoint(environment: str, kind: str) -> str:
    """The URL of the AEAT's VeriFactu service for ``environment`` and a certificate of ``kind``."""
    host = HOSTS.get((environment, kind == "seal"))
    if host is None:
        raise ValueError(f"Unknown AEAT environment {environment!r}.")
    return f"https://{host}{PATH}"


def nif_matches(envelope: str, nif: str) -> bool:
    """Whether every taxpayer ``envelope`` names is ``nif`` (and it names at least one)."""
    wanted = _normal(nif)
    found = _taxpayers(envelope)
    return bool(wanted and found) and all(_normal(each) == wanted for each in found)


def present(
    identity: Identity,
    environment: str,
    envelope: str,
    *,
    operation: Literal["submit", "query"],
    context: ssl.SSLContext | None = None,
) -> Answer:
    """POST ``envelope`` to the AEAT with ``identity``; the answer as it came, or ``AeatUnreachable``.

    ``context``: ``identity`` already loaded by ``tls_context``, so it is not loaded twice; without
    it, ``SealInvalid`` if TLS refuses ``identity`` (nothing was sent)."""
    if operation not in OPERATIONS:
        raise ValueError(f"Unknown operation {operation!r}.")
    url = endpoint(environment, identity.kind)
    try:
        if context is None:
            context = tls_context(identity)
        with httpx.Client(verify=context, timeout=TIMEOUT) as client:
            response = client.post(
                url, content=envelope.encode("utf-8"), headers=HEADERS
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
        logger.warning(
            "fiscal_gateway.aeat.unreachable operation=%s url=%s sent=false error=%s",
            operation,
            url,
            type(error).__name__,
        )
        raise AeatUnreachable(
            f"The AEAT could not be reached; nothing was sent ({type(error).__name__}).",
            sent=False,
        ) from None
    except httpx.HTTPError as error:
        logger.warning(
            "fiscal_gateway.aeat.unreachable operation=%s url=%s sent=true error=%s",
            operation,
            url,
            type(error).__name__,
        )
        raise AeatUnreachable(
            f"The request left and no answer came back from the AEAT ({type(error).__name__}).",
            sent=True,
        ) from None
    logger.info(
        "fiscal_gateway.aeat.answered operation=%s url=%s status=%s",
        operation,
        url,
        response.status_code,
    )
    return Answer(status=response.status_code, body=response.text)


def tls_context(identity: Identity) -> ssl.SSLContext:
    """httpx's TLS context (certifi's roots) with ``identity`` as the client certificate.

    ``SealInvalid`` if TLS refuses it."""
    context = httpx.create_ssl_context()
    with tempfile.TemporaryDirectory(prefix="fiscal-gateway-") as directory:
        cert_file = os.path.join(directory, "cert.pem")
        key_file = os.path.join(directory, "key.pem")
        _write_private(cert_file, identity.cert_pem)
        _write_private(key_file, identity.key_pem)
        try:
            context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        except ssl.SSLError:
            # OpenSSL's message may name the temporary files: only the reason leaves.
            raise SealInvalid(
                "The certificate and its private key cannot be used for TLS: "
                "they do not match or the key is too weak."
            ) from None
    return context


def _write_private(path: str, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(data)


def _normal(nif: str) -> str:
    """As the AEAT compares: no surrounding spaces, upper case."""
    return nif.strip().upper()


class _Refused(Exception):
    pass


def _taxpayers(envelope: str) -> list[str] | None:
    """The NIFs that name a taxpayer in ``envelope``; ``None`` if it is not XML we read."""
    parser = expat.ParserCreate(namespace_separator=" ")
    path: list[tuple[str, str]] = []
    text: list[str] = []
    found: list[str] = []

    def refuse(*_args):
        raise _Refused

    def start(name: str, _attributes):
        namespace, _, local = name.rpartition(" ")
        path.append((namespace, local))
        text.clear()

    def end(_name: str):
        namespace, local = path.pop()
        if namespace == SUMINISTRO_INFORMACION and (
            local in _ISSUERS
            or (
                local == "NIF"
                and path[-1:] == [(SUMINISTRO_INFORMACION, "ObligadoEmision")]
            )
        ):
            found.append("".join(text))
        text.clear()

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text.append
    try:
        parser.Parse(envelope, True)
    except _Refused, expat.ExpatError:
        return None
    return found
