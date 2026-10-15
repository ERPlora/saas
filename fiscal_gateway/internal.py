"""``POST /internal/verifactu/submit|query|probe``: the Hub hands the gateway an envelope to present.

Contract 3 of the fiscal block (PLAN-SAAS §2.2 and §4): the body is ``{"hub", "nif", "environment":
"testing"|"production", "route": "erplora"|"own", "envelope", "certificate"?: {"p12_base64",
"password"}}`` (``schemas.PresentIn``; the probe has no envelope). Server to server, signed as every
``/internal`` call (``accounts.signing``: v1 or v2, five minutes, the current or the previous secret),
so no CSRF token. Plain Django views, like ``hubs/internal.py``, until the ``/internal`` ninja API.

What each door answers:

- ``200 {"aeat_status", "aeat_body"}``: the AEAT answered, and this is its answer as it came, whatever
  it says (reading it is the Hub's job);
- ``409 {"error": {"code", "message"}}``: nothing was sent. ``nif_mismatch`` (the envelope names a
  taxpayer other than ``nif``; decided before anything else touches the AEAT), ``no_seal`` (``erplora``
  without a usable seal), ``no_certificate`` (``own`` without one), ``certificate_invalid`` (it does not
  open, cannot authenticate as a client, has expired, or TLS refuses it: its key is not the
  certificate's or is too weak), ``environment_not_allowed`` (``production`` from a deployment that is
  not prod: ``pre`` only presents to the AEAT's tests);
- ``502 {"error": {"code": "aeat_unreachable", "message", "sent"}}``: no answer from the AEAT. ``sent``
  says whether the request may have reached it (the Hub then keeps the record as sent and asks again);
- ``503 gateway_busy``: ``VERIFACTU_GATEWAY_CONCURRENCY`` presentations are already under way in this
  process (the Hub retries, as when the gateway is unreachable);
- ``401`` unsigned, ``405`` not POST, ``413`` over ``MAX_BODY_BYTES``, ``422`` not the contract.

``probe`` presents nothing: ``200 {"ready", "detail"}`` says whether a presentation would leave now
(``detail``: which certificate, or why not).

The body is read here, not through ``request.body``: a submission of a thousand records weighs more
than Django's form limit (``DATA_UPLOAD_MAX_MEMORY_SIZE``, 2.5 MB), and the gateway has its own.
The customer's certificate lives for the call only: it is never kept, never logged and never in an
error message (the schema keeps it as ``SecretStr``; ``sensitive_variables`` hides it from Django's
error reports).
"""

import datetime as dt
import json
import logging
import threading
import time

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from pydantic import ValidationError

from accounts.signing import live_secrets, verify_signed
from fiscal_gateway import aeat, seal
from fiscal_gateway.schemas import AnswerOut, PresentIn, ProbeIn, ProbeOut

logger = logging.getLogger(__name__)

#: The largest body the gateway reads: a thousand records (the AEAT's maximum per submission) with
#: room to spare, plus a certificate.
MAX_BODY_BYTES = 10 * 1024 * 1024

#: Presentations under way at once in this process; one more answers 503 at once.
SLOTS = threading.BoundedSemaphore(settings.VERIFACTU_GATEWAY_CONCURRENCY)


class _Refused(Exception):
    def __init__(
        self, status: int, code: str, message: str, fields: dict | None = None
    ):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields

    def response(self) -> JsonResponse:
        extra = {"fields": self.fields} if self.fields else {}
        response = _error(self.status, self.code, self.message, **extra)
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
        identity = _identity(body)
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
        identity = _identity(body)
    except _Refused as refused:
        return _refuse(operation, body, refused)
    if not SLOTS.acquire(blocking=False):
        logger.warning("fiscal_gateway.%s.busy hub=%s", operation, body.hub)
        return _error(
            503, "gateway_busy", "The gateway is presenting as much as it can; retry."
        )
    try:
        answer = aeat.present(
            identity, body.environment, body.envelope, operation=operation
        )
    except seal.SealInvalid as invalid:
        return _refuse(
            operation, body, _Refused(409, "certificate_invalid", str(invalid))
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


def _refuse(operation: str, body: PresentIn, refused: _Refused) -> JsonResponse:
    """Log that nothing was presented (which call, never the certificate) and answer so."""
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


@sensitive_variables()
def _body(request: HttpRequest, schema: type[ProbeIn]) -> ProbeIn:
    """The signed body of ``request`` as ``schema``, or the refusal to answer."""
    if request.method != "POST":
        raise _Refused(405, "method_not_allowed", "Only POST is allowed.")
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    raw = b"" if declared > MAX_BODY_BYTES else request.read(MAX_BODY_BYTES + 1)
    if declared > MAX_BODY_BYTES or len(raw) > MAX_BODY_BYTES:
        raise _Refused(
            413, "payload_too_large", f"The body exceeds {MAX_BODY_BYTES} bytes."
        )
    signed = verify_signed(
        request.method,
        request.get_full_path(),
        raw,
        request.headers,
        secrets=live_secrets(),
        now=int(time.time()),
        max_age=settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS,
    )
    if not signed:
        logger.warning("fiscal_gateway.unauthorized path=%s", request.path)
        raise _Refused(401, "unauthorized", "Missing, stale or invalid signature.")
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
            422, "invalid_payload", "The body is not the gateway's contract.", fields
        ) from None


def _allowed(environment: str) -> None:
    if environment == "production" and settings.ERPLORA_ENVIRONMENT != "prod":
        raise _Refused(
            409,
            "environment_not_allowed",
            "This deployment presents to the AEAT's test environment only.",
        )


@sensitive_variables()
def _identity(body: ProbeIn) -> seal.Identity:
    """The certificate to present ``body`` with, or the refusal to answer."""
    now = dt.datetime.now(dt.UTC)
    if body.route == "erplora":
        identity = seal.current(now)
        if identity is None:
            raise _Refused(
                409, "no_seal", "ERPlora has no usable seal to present with."
            )
        return identity
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
    return identity
