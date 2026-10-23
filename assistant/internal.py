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
limit, before it is parsed; the server keeps none of it, ``config.asgi.BodiesInMemory``), 401 ``unauthorized`` (unsigned, stale or another secret), 422 ``invalid_payload`` (not JSON
or not the contract, with the failing ``fields``), 404 ``hub_unknown``, 403 ``hub_inactive`` and 429 ``rate_limited``
(with ``Retry-After``; the business's budget of the door, spent only once the signature and the business passed,
saas#2531). An operation's refusal is its envelope ``{"error": {"code", "message"}}``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.core import get_usage
from live.errors import OperationError
from pydantic import BaseModel, ValidationError

from accounts.signing import live_secrets, may_be_signed, verify_signed
from assistant import media, queries, services, turn
from assistant.schemas import (
    Caller,
    CallerIn,
    ClaimOut,
    EmbeddingsIn,
    MessageReleaseIn,
    NoInput,
    ReportIn,
    ReportSendIn,
    RouteIn,
    SynthesizeIn,
    TranscribeIn,
    TurnIn,
    UsageRecordIn,
)
from assistant.services import platform_context

logger = logging.getLogger(__name__)

#: The largest body of a door that carries no file: an allowance, a report or a batch of texts to embed.
SMALL_BODY_BYTES = 1024 * 1024
#: The largest body of a turn: its text (``turn.MAX_TEXT_BYTES``) and its attachments (``attachments``).
TURN_BODY_BYTES = 32 * 1024 * 1024


class Refused(Exception):
    """A door's refusal: its status, its code, its message (and the failing ``fields``, the ``Retry-After``, and what
    else its envelope says)."""

    def __init__(
        self, status: int, code: str, message: str, *, fields: dict | None = None, retry_after: int = 0, **extra
    ):
        super().__init__(message)
        self.status, self.code, self.message, self.fields, self.retry_after = status, code, message, fields, retry_after
        self.extra = extra

    def response(self) -> JsonResponse:
        return refusal(
            self.status, self.code, self.message, fields=self.fields, retry_after=self.retry_after, **self.extra
        )


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
    who = turn.caller_key(caller)
    usage = get_usage(request, group=f"assistant.{bucket}", key=lambda group, request: who, rate=rate, increment=True)
    if usage is not None and usage["should_limit"]:
        wait = max(1, math.ceil(usage["time_left"]))
        logger.warning("assistant.internal.rate_limited bucket=%s caller=%s", bucket, who)
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


# --- The turn (ASSISTANT-G43, G44, G47) --------------------------------------------------------------------------

#: The route's refusals, which the Hub reads as «the assistant cannot answer now» (nothing is counted).
ROUTE_REFUSALS = frozenset({"assistant.no_model", "assistant.provider_not_configured"})


@dataclass
class Turn:
    """A turn that may go to the model: its conversation, its tools, its route and the message it took."""

    caller: Caller
    messages: list[dict]
    tools: list
    candidates: list
    claim: ClaimOut | None


async def start(call: Call) -> Turn:
    """The checks before the model is called, each a refusal that counts nothing: the conversation (413, 422), the
    route (503 ``assistant.no_model`` or ``assistant.provider_not_configured``) and, unless it answers the tools the
    Hub was asked for, a message of the allowance (429 ``assistant.quota_exceeded``)."""
    data: TurnIn = call.data
    try:
        messages = await sync_to_async(turn.prepare, thread_sensitive=False)(data.messages, data.instructions)
    except turn.TurnRefused as refused:
        raise Refused(refused.status, refused.code, refused.message, fields=refused.fields, retriable=False) from None
    try:
        route = await sync_to_async(queries.route_resolve)(platform_context(), RouteIn())
    except OperationError as refused:
        if refused.code not in ROUTE_REFUSALS:
            raise
        logger.warning("assistant.turn.no_route code=%s", refused.code)
        raise Refused(503, refused.code, refused.message, retriable=False) from None
    claim = None
    if not turn.is_continuation(call.caller, data.continuation, messages):
        claim = await sync_to_async(services.message_claim)(platform_context(), call.caller)
        if not claim.claimed:
            raise Refused(
                429,
                "assistant.quota_exceeded",
                "The assistant's messages of this period are spent.",
                retriable=False,
                upgrade_required=True,
                used=claim.used,
                limit=claim.limit,
                resets_at=claim.resets_at.isoformat() if claim.resets_at else None,
                demo=claim.demo,
            )
    return Turn(call.caller, messages, turn.hub_tools(data.tools), list(route.candidates), claim)


def settle(started: Turn, outcome: turn.Outcome) -> dict:
    """After the turn: its message given back if nothing was answered, what it spent recorded; the usage after it."""
    if started.claim is not None and not outcome.answered:
        services.message_release(platform_context(), MessageReleaseIn(caller=started.caller, month=started.claim.month))
    if outcome.tokens_input or outcome.tokens_output:
        services.usage_record(
            platform_context(),
            UsageRecordIn(
                caller=started.caller,
                tokens_input=outcome.tokens_input,
                tokens_output=outcome.tokens_output,
                cost_usd=outcome.cost,
            ),
        )
    return queries.usage_show(platform_context(), started.caller).model_dump(mode="json")


def response_frame(started: Turn, outcome: turn.Outcome) -> dict:
    token = turn.continuation_token(started.caller, [call["call_id"] for call in outcome.calls]) if outcome.calls else None
    return {
        "type": "response",
        "output": outcome.output(),
        "usage": {"input_tokens": outcome.tokens_input, "output_tokens": outcome.tokens_output},
        "continuation": token,
    }


def sse(frame) -> str:
    return f"data: {frame if isinstance(frame, str) else json.dumps(frame, ensure_ascii=False)}\n\n"


INTERNAL_ERROR = {
    "type": "error",
    "code": "assistant.internal_error",
    "message": turn.MESSAGES["assistant.internal_error"],
    "retriable": True,
}


async def stream(started: Turn):
    """The frames of the turn, then ``response`` (unless it failed), ``usage`` and ``[DONE]``. Whatever ends it (the
    end, a failure, the Hub closing the service) settles the message and what it spent."""
    outcome = turn.Outcome()
    try:
        async for frame in turn.run(started.candidates, started.messages, started.tools, outcome):
            yield sse(frame)
        if outcome.error is None:
            yield sse(response_frame(started, outcome))
    except Exception:
        logger.exception("assistant.turn.failed")
        outcome.error = INTERNAL_ERROR
        yield sse(INTERNAL_ERROR)
    finally:
        usage = await asyncio.shield(sync_to_async(settle)(started, outcome))
    yield sse({"type": "usage", **usage})
    yield sse("[DONE]")


@door(TurnIn, bucket="turn", rate="ASSISTANT_TURN_RATELIMIT", max_bytes=TURN_BODY_BYTES)
async def chat_stream(call: Call) -> HttpResponse:
    """A turn answered live, ``text/event-stream``: ``text_delta`` as the text comes, a ``function_call`` per tool of
    the Hub, ``response`` (the whole output, its tokens and the ``continuation`` of the tools), ``usage`` (the
    allowance after the turn) and ``[DONE]``; a failure of the provider is an ``error`` frame (``code``,
    ``retriable``) before ``usage``."""
    started = await start(call)
    response = StreamingHttpResponse(stream(started), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@door(TurnIn, bucket="turn", rate="ASSISTANT_TURN_RATELIMIT", max_bytes=TURN_BODY_BYTES)
async def chat(call: Call) -> HttpResponse:
    """A turn answered at once: ``{output, usage, continuation, quota}``; a failure of the provider is a 502 with its
    ``code`` and ``retriable``, the allowance after it in ``quota``."""
    started = await start(call)
    outcome = turn.Outcome()
    try:
        async for _frame in turn.run(started.candidates, started.messages, started.tools, outcome):
            pass
    except Exception:
        logger.exception("assistant.turn.failed")
        outcome.error = INTERNAL_ERROR
    finally:
        usage = await asyncio.shield(sync_to_async(settle)(started, outcome))
    if outcome.error is not None:
        error = {key: value for key, value in outcome.error.items() if key != "type"}
        return refusal(502, error.pop("code"), error.pop("message"), quota=usage, **error)
    body = {key: value for key, value in response_frame(started, outcome).items() if key != "type"}
    return JsonResponse({**body, "quota": usage})


# --- Embeddings and voice (ASSISTANT-G54, G56, G57) --------------------------------------------------------------

#: The body of a batch of texts to embed (256 descriptions of the Hub's modules fit many times over).
EMBED_BODY_BYTES = 2 * 1024 * 1024
#: The body of a dictation: its audio in base64 and a little more.
TRANSCRIBE_BODY_BYTES = 4 * 1024 * 1024


async def services_connection():
    """The services' provider, or 503 ``assistant.provider_not_configured``."""
    try:
        return await sync_to_async(queries.service_connection)(platform_context(), NoInput())
    except OperationError as refused:
        if refused.code != "assistant.provider_not_configured":
            raise
        logger.warning("assistant.media.no_provider")
        raise Refused(503, refused.code, refused.message, retriable=False) from None


def media_failed(problem: media.MediaFailed) -> JsonResponse:
    return refusal(502, problem.code, turn.MESSAGES[problem.code], retriable=problem.retriable)


async def record(caller: Caller, **spent) -> None:
    await sync_to_async(services.usage_record)(platform_context(), UsageRecordIn(caller=caller, **spent))


@door(EmbeddingsIn, bucket="embed", rate="ASSISTANT_EMBED_RATELIMIT", max_bytes=EMBED_BODY_BYTES)
async def embeddings(call: Call) -> HttpResponse:
    """The fingerprints of ``texts`` for the Hub's index, in their order: ``{embeddings, model}``. The tokens and
    their cost go to the business's month; the allowance of messages is not looked at."""
    service = await services_connection()
    try:
        vectors, tokens = await media.embed(service, call.data.texts)
    except media.MediaFailed as problem:
        return media_failed(problem)
    await record(call.caller, tokens_embedding=tokens, cost_usd=media.embedding_cost(tokens))
    return JsonResponse({"embeddings": vectors, "model": media.EMBEDDING_MODEL})


@door(TranscribeIn, bucket="transcribe", rate="ASSISTANT_TRANSCRIBE_RATELIMIT", max_bytes=TRANSCRIBE_BODY_BYTES)
async def transcribe(call: Call) -> HttpResponse:
    """The text of a dictation: ``{text, language}`` (``language`` as asked, base code; empty: the model found it).
    413 over ``MAX_AUDIO_BYTES`` of audio."""
    try:
        audio = base64.b64decode(call.data.audio, validate=True)
    except (binascii.Error, ValueError):
        raise Refused(422, "invalid_payload", "The body is not the door's contract.", fields={"audio": "not valid base64"}) from None
    if not audio:
        raise Refused(422, "invalid_payload", "The body is not the door's contract.", fields={"audio": "empty"})
    if len(audio) > media.MAX_AUDIO_BYTES:
        raise Refused(413, "payload_too_large", f"The audio exceeds {media.MAX_AUDIO_BYTES} bytes.")
    service = await services_connection()
    language = media.base_language(call.data.language)
    try:
        text = await media.transcribe(service, audio, call.data.mime_type, language)
    except media.MediaFailed as problem:
        return media_failed(problem)
    await record(call.caller, transcriptions=1)
    return JsonResponse({"text": text, "language": language})


@door(SynthesizeIn, bucket="synthesize", rate="ASSISTANT_SYNTHESIZE_RATELIMIT")
async def synthesize(call: Call) -> HttpResponse:
    """``text`` spoken (cut to ``MAX_SPEECH_CHARS``), ``audio/mpeg``; an unknown ``voice`` is the default one."""
    service = await services_connection()
    text = media.speech_text(call.data.text)
    try:
        audio = await media.synthesize(service, text, media.voice_of(call.data.voice))
    except media.MediaFailed as problem:
        return media_failed(problem)
    await record(call.caller, speech_characters=len(text))
    return HttpResponse(audio, content_type="audio/mpeg")


# --- The report of an answer (ASSISTANT-G58) ----------------------------------------------------------------------


@door(ReportIn, bucket="report", rate="ASSISTANT_REPORT_RATELIMIT")
async def report(call: Call) -> HttpResponse:
    """The report of an answer, mailed to support: 202 ``{sent, duplicate}`` (the same answer within a day mails
    nothing again); 503 ``assistant.report_not_sent`` if the mail cannot leave."""
    fields = call.data.model_dump(exclude={"hub"})
    sent = await sync_to_async(services.report_send)(platform_context(), ReportSendIn(caller=call.caller, **fields))
    return JsonResponse(sent.model_dump(), status=202)
