"""The assistant's doors erplora.com serves to the Hub (PLAN-SAAS §1.1): ``POST /internal/assistant/…`` (the turn,
live or at once, the allowance, the embeddings, the report of an answer) and ``POST /internal/speech/…`` (the
dictation and the reading aloud). The Hub never speaks to a provider: it calls these, and erplora.com keeps the
provider's key, chooses the model, counts the plan's messages and forgets the conversation.

Server to server, signed as every ``/internal`` call (``accounts.signing``: v1 over the body or v2 over the method,
the path and the body; ±300 s; the current or the previous secret), so no CSRF token. Plain Django views, as
``whatsapp.internal`` and ``fiscal_gateway.internal``, until the ``/internal`` ninja API; async, so a turn that waits
for its model holds no thread. Each one names the business in ``hub`` (its address or its id; a demo, its ``demo-…``
address).

Every door, before its own answer: 405 ``method_not_allowed``, 413 ``payload_too_large`` (a declared body over its
limit, before it is read), 401 ``unauthorized`` (unsigned, stale or another secret), 422 ``invalid_payload`` (not JSON
or not the contract, with the failing ``fields``), 404 ``hub_unknown``, 403 ``hub_inactive`` and 429 ``rate_limited``
(with ``Retry-After``; the business's budget of the door, spent only once the signature and the business passed,
saas#2531). An operation's refusal is its envelope ``{"error": {"code", "message"}}``.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.core import get_usage
from live.errors import OperationError
from pydantic import BaseModel, ValidationError

from accounts.signing import live_secrets, may_be_signed, verify_signed
from assistant import queries
from assistant.schemas import Caller, CallerIn
from assistant.services import platform_context

logger = logging.getLogger(__name__)

#: The largest body of a door that carries no file: an allowance, a report or a batch of texts to embed.
SMALL_BODY_BYTES = 1024 * 1024


class Refused(Exception):
    """A door's refusal: its status, its code, its message (and the failing ``fields``, the ``Retry-After``)."""

    def __init__(self, status: int, code: str, message: str, *, fields: dict | None = None, retry_after: int = 0):
        super().__init__(message)
        self.status, self.code, self.message, self.fields, self.retry_after = status, code, message, fields, retry_after

    def response(self) -> JsonResponse:
        return refusal(self.status, self.code, self.message, fields=self.fields, retry_after=self.retry_after)


def refusal(status: int, code: str, message: str, *, fields: dict | None = None, retry_after: int = 0, **extra):
    """The envelope of a refusal, ``{"error": {"code", "message", "fields"?, …}}``."""
    error = {"code": code, "message": message, **({"fields": fields} if fields else {}), **extra}
    response = JsonResponse({"error": error}, status=status)
    if status == 405:
        response["Allow"] = "POST"
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


@dataclass(frozen=True)
class Call:
    """A door's call once it passed: what it carries and who it is for."""

    data: BaseModel
    caller: Caller


def door(schema: type[BaseModel], *, bucket: str, rate: str, max_bytes: int = SMALL_BODY_BYTES):
    """A signed door reading ``schema`` (whose ``hub`` names the caller), limited per caller to the setting ``rate``
    in the budget ``bucket``, answering with ``answer(call)``."""

    def decorate(answer: Callable[[Call], Awaitable[HttpResponse]]):
        @csrf_exempt
        @never_cache
        async def view(request: HttpRequest) -> HttpResponse:
            try:
                data = read(request, schema, max_bytes)
                caller = await sync_to_async(resolve)(data.hub)
                await sync_to_async(spend)(request, bucket, getattr(settings, rate), caller)
                return await answer(Call(data=data, caller=caller))
            except Refused as refused:
                return refused.response()
            except OperationError as refused:
                return JsonResponse(refused.envelope(), status=refused.status)

        view.__name__ = answer.__name__
        view.__doc__ = answer.__doc__
        return view

    return decorate


def read(request: HttpRequest, schema: type[BaseModel], max_bytes: int) -> BaseModel:
    """``schema`` of a signed call's body, or a refusal: what the headers already rule out, before the body."""
    if request.method != "POST":
        raise Refused(405, "method_not_allowed", "Only POST is allowed.")
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > max_bytes:
        raise too_large(max_bytes)
    now = int(time.time())
    max_age = settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS
    if not may_be_signed(request.headers, now=now, max_age=max_age):
        raise unauthorized(request)
    raw = request.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise too_large(max_bytes)
    if not verify_signed(
        request.method, request.get_full_path(), raw, request.headers, secrets=live_secrets(), now=now, max_age=max_age
    ):
        raise unauthorized(request)
    try:
        payload = json.loads(raw)
    except ValueError:
        raise Refused(422, "invalid_payload", "The body is not JSON.") from None
    try:
        return schema.model_validate(payload)
    except ValidationError as invalid:
        fields = {
            ".".join(str(part) for part in error["loc"]) or "body": error["msg"]
            for error in invalid.errors(include_input=False, include_url=False)
        }
        raise Refused(422, "invalid_payload", "The body is not the door's contract.", fields=fields) from None


def resolve(hub: str) -> Caller:
    return queries.caller_resolve(platform_context(), CallerIn(hub=hub))


def spend(request: HttpRequest, bucket: str, rate: str, caller: Caller) -> None:
    """One call of ``caller``'s budget ``bucket``; over ``rate``, 429 ``rate_limited`` with the seconds left."""
    key = f"demo:{caller.demo}" if caller.demo else f"hub:{caller.hub_id}"
    usage = get_usage(request, group=f"assistant.{bucket}", key=lambda group, request: key, rate=rate, increment=True)
    if usage is not None and usage["should_limit"]:
        wait = max(1, math.ceil(usage["time_left"]))
        logger.warning("assistant.internal.rate_limited bucket=%s caller=%s", bucket, key)
        raise Refused(
            429, "rate_limited", "Too many requests of this business: wait a moment and try again.", retry_after=wait
        )


def unauthorized(request: HttpRequest) -> Refused:
    logger.warning("assistant.internal.unauthorized path=%s", request.path)
    return Refused(401, "unauthorized", "Missing, stale or invalid signature.")


def too_large(max_bytes: int) -> Refused:
    return Refused(413, "payload_too_large", f"The body exceeds {max_bytes} bytes.")


# --- The doors -------------------------------------------------------------------------------------------------


@door(CallerIn, bucket="turn", rate="ASSISTANT_TURN_RATELIMIT")
async def usage(call: Call) -> HttpResponse:
    """What the business spent of its plan's monthly messages (a demo, of its own few): ``{used, limit, resets_at,
    demo}``. The same figures close every turn."""
    shown = await sync_to_async(queries.usage_show)(platform_context(), call.caller)
    return JsonResponse(shown.model_dump(mode="json"))
