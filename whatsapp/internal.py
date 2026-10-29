"""The WhatsApp doors erplora.com serves to the Hub, ``POST /internal/whatsapp/…`` (the Hub's WORKBOOK
``whatsapp_inbox``, «Contrato con el SaaS», doors 5–9; the Hub calls them from ``apps/whatsapp_inbox/gateway.py``),
and the proposed doors 10–12 of connecting a number (``config``, ``connect``, ``disconnect``; the whatsapp
WORKBOOK, «Contrato con el Hub»).

Server to server, signed as every ``/internal`` call (``accounts.signing``: v1 over the body, which the Hub signs
today, or v2; ±300 s; the current or the previous secret), so no CSRF token. Plain Django views, as
``fiscal_gateway.internal``, until the ``/internal`` ninja API. The contract is not renamed: same paths, fields,
codes and answers.

Every door: 401 ``unauthorized`` (unsigned, stale or another secret; decided by the headers before the body is
read when they already rule it out), 405 ``method_not_allowed``, 413 ``payload_too_large`` (over
``MAX_BODY_BYTES``; doors 5 and 8, which carry a header's file, over ``MAX_TEMPLATE_BODY_BYTES``), 422
``invalid_payload`` (not JSON or not the contract, with the failing ``fields``), 404
``hub_unknown`` (``hub`` names no business the SaaS knows, a demo included: saas#2599). The rest of each answer is
the door's (``gateway``).
"""

import json
import logging
import time

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from live.errors import OperationError
from pydantic import BaseModel, ValidationError

from accounts.signing import live_secrets, may_be_signed, verify_signed
from whatsapp import gateway
from whatsapp.schemas import ConfigIn, ConnectIn, DisconnectIn, EraseIn, SendIn, TemplateDeleteIn, TemplateIn
from whatsapp.templates import MAX_SAMPLE_BYTES

logger = logging.getLogger(__name__)

#: The largest body a door reads: a template with its examples and buttons fits many times over.
MAX_BODY_BYTES = 256 * 1024
#: Doors 5 and 8's: a template and the heaviest file of a header (``templates.MAX_SAMPLE_BYTES``) in base64.
MAX_TEMPLATE_BODY_BYTES = MAX_BODY_BYTES + 4 * -(-MAX_SAMPLE_BYTES // 3)
IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 255


class _Refused(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields

    def response(self) -> JsonResponse:
        error = {"code": self.code, "message": self.message, **({"fields": self.fields} if self.fields else {})}
        response = JsonResponse({"error": error}, status=self.status)
        if self.status == 405:
            response["Allow"] = "POST"
        return response


def _door(schema: type[BaseModel], *, keyed: bool = False, max_bytes: int = MAX_BODY_BYTES):
    """A signed door reading ``schema`` (and the ``Idempotency-Key`` when ``keyed``) from a body of ``max_bytes`` at
    most and answering ``answer``'s ``(status, body)``; an operation's refusal is its envelope."""

    def decorate(answer):
        @csrf_exempt
        @never_cache
        def view(request: HttpRequest) -> JsonResponse:
            try:
                data = _body(request, schema, max_bytes)
                args = (data, _key(request)) if keyed else (data,)
                status, body = answer(*args)
            except _Refused as refused:
                return refused.response()
            except OperationError as refused:
                return JsonResponse(refused.envelope(), status=refused.status)
            return JsonResponse(body, status=status)

        view.__name__ = answer.__name__
        view.__doc__ = answer.__doc__
        return view

    return decorate


def _body(request: HttpRequest, schema: type[BaseModel], max_bytes: int) -> BaseModel:
    if request.method != "POST":
        raise _Refused(405, "method_not_allowed", "Only POST is allowed.")
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > max_bytes:
        raise _too_large(max_bytes)
    now = int(time.time())
    max_age = settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS
    if not may_be_signed(request.headers, now=now, max_age=max_age):
        raise _unauthorized(request)
    raw = request.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise _too_large(max_bytes)
    signed = verify_signed(
        request.method, request.get_full_path(), raw, request.headers, secrets=live_secrets(), now=now, max_age=max_age
    )
    if not signed:
        raise _unauthorized(request)
    try:
        payload = json.loads(raw)
    except ValueError:
        raise _Refused(422, "invalid_payload", "The body is not JSON.") from None
    try:
        return schema.model_validate(payload)
    except ValidationError as invalid:
        fields = {
            ".".join(str(part) for part in error["loc"]) or "body": error["msg"]
            for error in invalid.errors(include_input=False, include_url=False)
        }
        raise _Refused(422, "invalid_payload", "The body is not the door's contract.", fields) from None


def _key(request: HttpRequest) -> str:
    key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    if not key or len(key) > MAX_KEY_LENGTH:
        raise _Refused(
            422,
            "invalid_payload",
            f"The {IDEMPOTENCY_HEADER} header (1 to {MAX_KEY_LENGTH} characters) is required.",
            {IDEMPOTENCY_HEADER: "required, 1 to 255 characters"},
        )
    return key


def _unauthorized(request: HttpRequest) -> _Refused:
    logger.warning("whatsapp.internal.unauthorized path=%s", request.path)
    return _Refused(401, "unauthorized", "Missing, stale or invalid signature.")


def _too_large(max_bytes: int) -> _Refused:
    return _Refused(413, "payload_too_large", f"The body exceeds {max_bytes} bytes.")


@_door(SendIn, keyed=True, max_bytes=MAX_TEMPLATE_BODY_BYTES)
def send(data: SendIn, key: str) -> tuple[int, dict]:
    """Door 5: send a text or a template for the business, once per ``Idempotency-Key``."""
    return gateway.send(data, key)


@_door(EraseIn)
def erase(data: EraseIn) -> tuple[int, dict]:
    """Door 6: forget what is kept of a customer's number for the business."""
    return gateway.erase(data)


@_door(TemplateIn, keyed=True, max_bytes=MAX_TEMPLATE_BODY_BYTES)
def templates(data: TemplateIn, key: str) -> tuple[int, dict]:
    """Door 8: register a template at Meta for the business (new, or an edit of its ``meta_id``), once per key; a
    header's file is uploaded to Meta first."""
    return gateway.submit_template(data, key)


@_door(TemplateDeleteIn)
def templates_delete(data: TemplateDeleteIn) -> tuple[int, dict]:
    """Door 9: delete that one template, in that language, at Meta."""
    return gateway.delete_template(data)


@_door(ConfigIn)
def config(data: ConfigIn) -> tuple[int, dict]:
    """Door 10: what the Hub's screen opens Meta's window (Embedded Signup) with."""
    return gateway.config(data)


@_door(ConnectIn)
def connect(data: ConnectIn) -> tuple[int, dict]:
    """Door 11: connect the number Meta's window chose, with its one-time code."""
    return gateway.connect(data)


@_door(DisconnectIn)
def disconnect(data: DisconnectIn) -> tuple[int, dict]:
    """Door 12: disconnect the business's number."""
    return gateway.disconnect(data)
