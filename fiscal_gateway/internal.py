"""``POST /internal/verifactu/submit|query|probe``: the Hub hands the gateway an envelope to present.

Contract 3 of the fiscal block (PLAN-SAAS §2.2 and §4): the body is ``{"hub", "nif", "environment":
"testing"|"production", "route": "erplora"|"own", "envelope", "certificate"?: {"p12_base64",
"password"}}`` (``schemas.PresentIn``; the probe has no envelope). Server to server, signed as every
``/internal`` call (``accounts.signing``: v1 or v2, five minutes, the current or the previous secret),
so no CSRF token. Plain Django views, like ``hubs/internal.py``, until the ``/internal`` ninja API.

What each door answers:

- ``200 {"aeat_status", "aeat_body"}``: the AEAT answered, and this is its answer as it came, whatever
  it says (reading it is the Hub's job);
- ``404 {"error": {"code": "hub_unknown", "message"}}``: ``hub`` names no business the SaaS knows (or a
  purged one) and is not the platform's hub through ``erplora``; nothing was sent;
- ``409 {"error": {"code", "message"}}``: nothing was sent. ``nif_mismatch`` (the envelope names a
  taxpayer other than ``nif``, decided before anything else touches the AEAT; or, through ``erplora``,
  the business's approved authorisation covers another taxpayer, or the platform's hub names a taxpayer
  other than the seal's holder), ``representation_not_approved`` (``erplora`` for a business without an
  approved authorisation: none, under review, returned or withdrawn; whatever ``nif`` it declares, ERPlora's
  own included), ``no_seal`` (``erplora`` without a usable seal),
  ``no_certificate`` (``own`` without one), ``certificate_invalid`` (it does not open, cannot
  authenticate as a client, has expired, or TLS refuses it: its key is not the certificate's or is too
  weak; ERPlora's seal in that case is ``no_seal``), ``environment_not_allowed`` (``production`` from a
  deployment that is not prod: ``pre`` only presents to the AEAT's tests);
- ``502 {"error": {"code": "aeat_unreachable", "message", "sent"}}``: no answer from the AEAT. ``sent``
  says whether the request may have reached it (the Hub then keeps the record as sent and asks again). Also,
  ``sent: false``, when the server's trusted certificates cannot be loaded (``aeat.TrustStoreUnreadable``: the
  message names ``SSL_CERT_FILE`` and its file), decided before the AEAT, which the Hub retries in its cycle;
- ``503 gateway_busy``: ``VERIFACTU_GATEWAY_CONCURRENCY`` presentations are already under way in this
  process (the Hub retries, as when the gateway is unreachable);
- ``401`` unsigned, ``405`` not POST, ``413`` over ``MAX_BODY_BYTES``, ``422`` not the contract. A
  declared length over the limit (413) and headers that cannot be signed (401: no timestamp, no
  signature, a timestamp out of the window) are refused before the body is read.

``probe`` presents nothing: ``200 {"ready", "detail"}`` says whether a presentation would leave now
(``detail``: which certificate, or why not; an unknown business or a missing authorisation is
``ready: false`` too). It loads the certificate into TLS as a presentation does, so a certificate TLS
refuses, or trusted certificates the server cannot load, is ``ready: false`` there too.

ERPlora's seal presents for a business's taxpayer only with the business's approved authorisation
(the Anexo I the staff reviewed, ``fiscal.RepresentationGrant``) whose taxpayer is ``nif``. The one
exception is the platform's hub (``hub`` is ``settings.PLATFORM_HUB_SLUG``, a reserved slug no business
bears): ERPlora's own records, in its own name, for the seal's holder only and without an authorisation.
What the authorisation says never reaches an answer nor a log. The reads are ``fiscal_gateway.queries``'.

The body is read here, not through ``request.body``: a submission of a thousand records weighs more
than Django's form limit (``DATA_UPLOAD_MAX_MEMORY_SIZE``, 2.5 MB), and the gateway has its own.
The customer's certificate lives for the call only: it is never kept, never logged and never in an
error message (the schema keeps it as ``SecretStr``; ``sensitive_variables`` hides it from Django's
error reports).
"""

import datetime as dt
import json
import logging
import ssl
import threading
import time
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from pydantic import ValidationError

from accounts.signing import live_secrets, may_be_signed, verify_signed
from billing.nif import normalise_nif
from fiscal_gateway import aeat, queries, seal
from fiscal_gateway.schemas import AnswerOut, PresentIn, ProbeIn, ProbeOut

logger = logging.getLogger(__name__)

#: The largest body the gateway reads: a thousand records (the AEAT's maximum per submission) with
#: room to spare, plus a certificate.
MAX_BODY_BYTES = 10 * 1024 * 1024

#: Presentations under way at once in this process; one more answers 503 at once.
SLOTS = threading.BoundedSemaphore(settings.VERIFACTU_GATEWAY_CONCURRENCY)


class _Refused(Exception):
    """The answer of a call the gateway does not present; ``extra``: more fields of its error (``fields``, ``sent``)."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def response(self) -> JsonResponse:
        response = _error(self.status, self.code, self.message, **self.extra)
        if self.status == 405:
            response["Allow"] = "POST"
        return response


def _error(status: int, code: str, message: str, **extra) -> JsonResponse:
    return JsonResponse(
        {"error": {"code": code, "message": message, **extra}}, status=status
    )


@csrf_exempt
@never_cache
def submit(request: HttpRequest) -> JsonResponse:
    return _present(request, "submit")


@csrf_exempt
@never_cache
def query(request: HttpRequest) -> JsonResponse:
    return _present(request, "query")


@csrf_exempt
@never_cache
def probe(request: HttpRequest) -> JsonResponse:
    try:
        body = _body(request, ProbeIn)
    except _Refused as refused:
        return refused.response()
    try:
        _allowed(body.environment)
        identity, _ = _identity(body)
    except _Refused as refused:
        out = ProbeOut(ready=False, detail=refused.message)
    else:
        out = ProbeOut(ready=True, detail=identity.describe())
    logger.info(
        "fiscal_gateway.probe hub=%s nif=%s environment=%s route=%s ready=%s",
        body.hub,
        body.nif,
        body.environment,
        body.route,
        out.ready,
    )
    return JsonResponse(out.model_dump())


def _present(request: HttpRequest, operation: str) -> JsonResponse:
    try:
        body = _body(request, PresentIn)
    except _Refused as refused:
        return refused.response()
    try:
        _allowed(body.environment)
        # Before anything else touches the AEAT: an envelope of somebody else is never presented.
        if not aeat.nif_matches(body.envelope, body.nif):
            raise _Refused(
                409,
                "nif_mismatch",
                f"The envelope names a taxpayer other than {body.nif}.",
            )
        identity, context = _identity(body)
    except _Refused as refused:
        logger.warning(
            "fiscal_gateway.%s.refused code=%s hub=%s nif=%s environment=%s route=%s",
            operation,
            refused.code,
            body.hub,
            body.nif,
            body.environment,
            body.route,
        )
        return refused.response()
    if not SLOTS.acquire(blocking=False):
        logger.warning("fiscal_gateway.%s.busy hub=%s", operation, body.hub)
        return _error(
            503, "gateway_busy", "The gateway is presenting as much as it can; retry."
        )
    try:
        answer = aeat.present(
            identity,
            body.environment,
            body.envelope,
            operation=operation,
            context=context,
        )
    except aeat.AeatUnreachable as unreachable:
        return _error(502, "aeat_unreachable", str(unreachable), sent=unreachable.sent)
    finally:
        SLOTS.release()
    logger.info(
        "fiscal_gateway.%s hub=%s nif=%s environment=%s route=%s kind=%s aeat_status=%s",
        operation,
        body.hub,
        body.nif,
        body.environment,
        body.route,
        identity.kind,
        answer.status,
    )
    return JsonResponse(
        AnswerOut(aeat_status=answer.status, aeat_body=answer.body).model_dump()
    )


@sensitive_variables()
def _body(request: HttpRequest, schema: type[ProbeIn]) -> ProbeIn:
    """The signed body of ``request`` as ``schema``, or the refusal to answer."""
    if request.method != "POST":
        raise _Refused(405, "method_not_allowed", "Only POST is allowed.")
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_BODY_BYTES:
        raise _too_large()
    now = int(time.time())
    max_age = settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS
    # Nothing is read from a call whose headers already rule out a signature.
    if not may_be_signed(request.headers, now=now, max_age=max_age):
        raise _unauthorized(request)
    raw = request.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        raise _too_large()
    signed = verify_signed(
        request.method,
        request.get_full_path(),
        raw,
        request.headers,
        secrets=live_secrets(),
        now=now,
        max_age=max_age,
    )
    if not signed:
        raise _unauthorized(request)
    try:
        data = json.loads(raw)
    except ValueError:
        raise _Refused(422, "invalid_payload", "The body is not JSON.") from None
    try:
        return schema.model_validate(data)
    except ValidationError as invalid:
        # The messages only: pydantic's own text would echo the input, the certificate included.
        fields = {
            ".".join(str(part) for part in error["loc"]) or "body": error["msg"]
            for error in invalid.errors(include_input=False, include_url=False)
        }
        raise _Refused(
            422,
            "invalid_payload",
            "The body is not the gateway's contract.",
            fields=fields,
        ) from None


def _unauthorized(request: HttpRequest) -> _Refused:
    logger.warning("fiscal_gateway.unauthorized path=%s", request.path)
    return _Refused(401, "unauthorized", "Missing, stale or invalid signature.")


def _too_large() -> _Refused:
    return _Refused(
        413, "payload_too_large", f"The body exceeds {MAX_BODY_BYTES} bytes."
    )


def _allowed(environment: str) -> None:
    if environment == "production" and settings.ERPLORA_ENVIRONMENT != "prod":
        raise _Refused(
            409,
            "environment_not_allowed",
            "This deployment presents to the AEAT's test environment only.",
        )


def _known(hub: str) -> UUID:
    """The id of the business ``hub`` names, or the refusal if the SaaS knows none."""
    hub_id = queries.hub_id_for(hub)
    if hub_id is None:
        raise _Refused(
            404, "hub_unknown", "No business the SaaS knows goes by that hub."
        )
    return hub_id


def _platform_files_its_own(body: ProbeIn, holder_tax_id: str) -> None:
    """Refuses the platform's hub a taxpayer other than the seal's holder: it files ERPlora's own records."""
    if normalise_nif(body.nif) != normalise_nif(holder_tax_id):
        raise _Refused(
            409,
            "nif_mismatch",
            f"The platform's hub presents ERPlora's own records only, not {body.nif}'s.",
        )


def _represented(body: ProbeIn, hub_id: UUID) -> None:
    """Refuses ERPlora's seal for ``body.nif`` unless it is the taxpayer of the business's approved
    authorisation. Never says whom that authorisation covers."""
    nif = normalise_nif(body.nif)
    approved = queries.approved_taxpayer(hub_id)
    if approved is None:
        raise _Refused(
            409,
            "representation_not_approved",
            "ERPlora has no approved authorisation to present for this business: its signed "
            "authorisation (Anexo I) must be approved first.",
        )
    if approved != nif:
        raise _Refused(
            409,
            "nif_mismatch",
            f"The business's approved authorisation covers a taxpayer other than {body.nif}.",
        )


@sensitive_variables()
def _identity(body: ProbeIn) -> tuple[seal.Identity, ssl.SSLContext]:
    """The certificate to present ``body`` with and its TLS context, or the refusal to answer."""
    now = dt.datetime.now(dt.UTC)
    # The platform's hub is no business of the SaaS: it is known through ERPlora's seal only.
    platform = body.route == "erplora" and body.hub == settings.PLATFORM_HUB_SLUG
    hub_id = None if platform else _known(body.hub)
    if body.route == "erplora":
        identity = seal.current(now)
        if identity is None:
            raise _Refused(
                409, "no_seal", "ERPlora has no usable seal to present with."
            )
        if platform:
            _platform_files_its_own(body, identity.holder_tax_id)
        else:
            _represented(body, hub_id)
        return identity, _tls(identity, "no_seal")
    if body.certificate is None:
        raise _Refused(
            409, "no_certificate", "The «own» route needs the business's certificate."
        )
    try:
        identity = seal.load(
            body.certificate.p12_base64.get_secret_value(),
            body.certificate.password.get_secret_value(),
        )
    except seal.SealInvalid as invalid:
        raise _Refused(409, "certificate_invalid", str(invalid)) from None
    if not identity.usable_at(now):
        raise _Refused(
            409,
            "certificate_invalid",
            f"The certificate expired on {identity.expires_at.date().isoformat()}.",
        )
    return identity, _tls(identity, "certificate_invalid")


@sensitive_variables()
def _tls(identity: seal.Identity, code: str) -> ssl.SSLContext:
    """``identity`` loaded into TLS, or the refusal ``code`` if TLS will not take it; ``aeat_unreachable``, not
    sent, if the server's trusted certificates cannot be loaded."""
    try:
        return aeat.tls_context(identity)
    except seal.SealInvalid as invalid:
        raise _Refused(409, code, str(invalid)) from None
    except aeat.TrustStoreUnreadable as unreadable:
        raise _Refused(
            502, "aeat_unreachable", str(unreadable), sent=unreadable.sent
        ) from None
