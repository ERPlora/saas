"""The Hub's two calls about a business's signed authorisation (plan 2026-10-15, «Contrato»):

- ``POST /internal/hubs/{id}/representation``: the customer's documents, uploaded in the Hub's module, filed
  for the staff's review (``fiscal.representation.submit``, run as the platform in the owner's channel) →
  201 ``{status: "submitted", version, submitted_at}``.
- ``GET /internal/representation/model``: the blank model the customer signs (Anexo I, p. 11, of the AEAT's
  agreement 017 for the direct representation of a client), a static PDF without anybody's data.

Server to server, signed as ``/internal/auth/redeem`` (``accounts.signing.verify_signed``: HMAC-SHA256 +
timestamp, v1 over the body, v2 also over the method and the path), so no CSRF token. v1 covers the body
only, so a body that names a business must name the one of the path. The upload reads its body itself, up to
``MAX_BODY_BYTES``: Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB, for every other view) stays as it is.
Every refusal answers the single envelope ``{"error": {"code", "message", "fields"?}}`` (PLAN §14.1): 400 a
body that is no JSON object or a ``Content-Length`` that is no length, 401 the signature, 404 a business
unknown or deleted, 405 another method, 413 (``fiscal.body_too_large``) a body beyond ``MAX_BODY_BYTES``,
before anything else is checked, 422 a broken rule (its ``fiscal.*`` code) or a malformed field
(``invalid_payload``). The field messages speak the language the Hub asks (``Accept-Language``). Nothing is
cached: the answers carry ``Cache-Control: no-store``. Plain Django views, like ``hubs.internal``, until the
``/internal`` ninja API takes them all.
"""

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pydantic
from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.utils import translation
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from live.errors import OperationError

from accounts.signing import live_secrets, verify_request, verify_signed
from fiscal import services
from fiscal.schemas import RepresentationSubmitIn
from hubs.services import system_ctx_for

logger = logging.getLogger(__name__)

#: The blank Anexo I the customer signs (copied from ``knowledge/company/aeat-agreement-017``).
MODEL = Path(__file__).resolve().parent / "static" / "fiscal" / "representation-model.pdf"
MODEL_FILENAME = "anexo-i-otorgamiento-representacion-erplora.pdf"
#: The largest upload body: four PDFs of 5 MB (``fiscal.documents.MAX_DOCUMENT_BYTES``) in base64 are about
#: 26.7 MB, plus the names and the JSON around them.
MAX_BODY_BYTES = 32 * 1024 * 1024


def _error(status: int, code: str, message: str, *, fields: dict[str, str] | None = None) -> JsonResponse:
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return JsonResponse({"error": error}, status=status)


def _not_allowed(request: HttpRequest, method: str) -> JsonResponse | None:
    """405 with ``Allow`` unless ``request`` is ``method``."""
    if request.method == method:
        return None
    response = _error(405, "method_not_allowed", f"Only {method} is allowed.")
    response["Allow"] = method
    return response


def _unauthorized(request: HttpRequest) -> JsonResponse:
    logger.warning("internal.fiscal.unauthorized path=%s", request.path)
    return _error(401, "unauthorized", "Missing, stale or invalid signature.")


def _only(request: HttpRequest, method: str) -> JsonResponse | None:
    """405 with ``Allow`` unless ``request`` is ``method``; then 401 unless it is signed."""
    refused = _not_allowed(request, method)
    if refused is None and not verify_request(request):
        refused = _unauthorized(request)
    return refused


def _body(request: HttpRequest, hub_id: UUID) -> bytes | JsonResponse:
    """The body, read from the stream (never ``request.body``, bound by ``DATA_UPLOAD_MAX_MEMORY_SIZE``), or
    its refusal: 400 a ``Content-Length`` that is no length, 413 a body beyond ``MAX_BODY_BYTES``. Read up to
    one byte past the ceiling, so a length understated or absent (HTTP reads a request without one as empty,
    or as chunked, which ASGI buffers as it arrives) is caught by what arrives."""
    stated = request.META.get("CONTENT_LENGTH")
    length = 0
    if stated:
        try:
            length = int(stated)
        except ValueError:
            length = -1
        if length < 0:
            return _error(400, "invalid_request", "Content-Length must be a length.")
    body = b"" if length > MAX_BODY_BYTES else request.read(MAX_BODY_BYTES + 1)
    if length > MAX_BODY_BYTES or len(body) > MAX_BODY_BYTES:
        logger.warning("internal.fiscal.representation.too_large hub=%s", hub_id)
        return _error(
            413,
            "fiscal.body_too_large",
            f"The body may be {MAX_BODY_BYTES // (1024 * 1024)} MB at most.",
        )
    return body


def _signed(request: HttpRequest, body: bytes) -> bool:
    """``accounts.signing.verify_request`` over ``body``, the bytes this view read."""
    return verify_signed(
        request.method,
        request.get_full_path(),
        body,
        request.headers,
        secrets=live_secrets(),
        now=int(time.time()),
        max_age=settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS,
    )


def _fields(error: pydantic.ValidationError) -> dict[str, str]:
    """One message per field path (the first), as ``live`` words a malformed live subscription."""
    fields: dict[str, str] = {}
    for problem in error.errors():
        fields.setdefault(".".join(str(part) for part in problem["loc"]) or "__all__", problem["msg"])
    return fields


@csrf_exempt
@never_cache
def representation(request: HttpRequest, hub_id: UUID) -> JsonResponse:
    refused = _not_allowed(request, "POST")
    if refused is not None:
        return refused
    # Its size before anything else: nothing beyond the ceiling is read, let alone verified.
    body = _body(request, hub_id)
    if isinstance(body, JsonResponse):
        return body
    if not _signed(request, body):
        return _unauthorized(request)
    try:
        payload = json.loads(body)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return _error(400, "invalid_request", "The body must be a JSON object.")
    # The v1 signature covers the body only: a body that names a business must name the one of the path.
    if payload.get("hub_id", str(hub_id)) != str(hub_id):
        return _error(400, "invalid_request", "The body names another business than the path.")
    language = translation.get_language_from_request(request)
    try:
        data = RepresentationSubmitIn.model_validate({**payload, "hub_id": hub_id})
    except pydantic.ValidationError as broken:
        return _error(422, "invalid_payload", "Invalid payload", fields=_fields(broken))
    ctx = replace(system_ctx_for(hub_id), language=language)
    try:
        result = services.representation_submit(ctx, data)
    except OperationError as refusal:
        logger.info("internal.fiscal.representation.refused hub=%s code=%s", hub_id, refusal.code)
        return JsonResponse(refusal.envelope(), status=refusal.status)
    logger.info("internal.fiscal.representation hub=%s version=%s", hub_id, result.version)
    return JsonResponse(result.model_dump(mode="json"), status=201)


@csrf_exempt
@never_cache
def representation_model(request: HttpRequest) -> HttpResponse:
    refused = _only(request, "GET")
    if refused is not None:
        return refused
    return FileResponse(
        MODEL.open("rb"),
        as_attachment=True,
        filename=MODEL_FILENAME,
        content_type="application/pdf",
    )
