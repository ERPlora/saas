"""A turn of the Hub's assistant through the gateway: the conversation made ready for the
model, the tools offered, the answer streamed as the Hub's frames, and what it spent.

The conversation is the Hub's (the person's browser owns it): erplora.com uses it for
the call and forgets it. ``prepare`` refuses what is too big (never cuts it), drops the client's system messages for
the Hub's ``instructions``, drops a tool result whose call is not there and keeps the last ``MAX_MESSAGES``. ``run``
streams the turn through its route (``assistant.routing.stream``: the model that answers, then its fallback if the
provider fails before answering) and yields the frames the Hub reads:

    {"type": "text_delta", "text": str}
    {"type": "function_call", "name": str, "call_id": str, "arguments": str}     # a tool of the Hub, for it to run
    {"type": "error", "code": str, "message": str, "retriable": bool}
    {"type": "web"}     # once, when a search brought pages: the caller keeps the mark with the answer (saas#287)

The mark goes back with a report of the answer, whose text is then not mailed: section 3(b)(i) of Brave Search's
terms forbids keeping its results, and a mailbox keeps.

``Outcome`` keeps what the door needs after the stream: the text, the Hub's tool calls, the tokens and their cost
of each model that answered (with its prices), whether anything was answered, whether it brought pages from the web
and the error. The provider's own words of a failure reach neither the Hub nor a log (they may quote the
conversation): the Hub gets a code and a plain sentence, the log the status.

When the model asks for tools of the Hub, the turn ends there with a ``continuation`` token
(``assistant.continuation``): the Hub runs them and sends the conversation back with their results and that token, and
that turn costs no message (it answers the same request of the person).

The turn as a door serves it (``start``, ``stream``, ``settle``, ``spend``) is the same for the Hub's doors
(``assistant.internal``, signed) and for the assistant of erplora.com's own panel (``base.assistant``, in process, for
the signed-in account): the checks before the model, each a ``Refused`` that counts nothing; the frames; and, whatever
ends it, the message given back if nothing was answered and what it spent recorded.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse
from django_ratelimit.core import get_usage
from live.errors import OperationError

from assistant import queries, routing, services
from assistant.continuation import caller_key, continuation_token, is_continuation, tool_budget
from assistant.providers.base import ToolSpec, TurnRequest
from assistant.schemas import Caller, ClaimIn, ClaimOut, MessageReleaseIn, RouteCandidate, RouteIn, UsageRecordIn
from assistant.services.platform_actor import platform_context
from assistant.turn_outcome import Outcome

logger = logging.getLogger(__name__)

#: The messages of a conversation the model sees: the last ones (the system message apart).
MAX_MESSAGES = 100
#: The text of a conversation (its attachments apart, ``attachments``): over it the turn is refused, never cut.
MAX_TEXT_BYTES = 1_000_000
#: The longest answer of one call to the model, in tokens.
MAX_OUTPUT_TOKENS = 4096
ROLES = frozenset({"system", "user", "assistant", "tool"})

#: The plain sentence of each failure the Hub may show (its own text by ``code`` is better).
MESSAGES = {
    "assistant.provider_rejected": "The AI provider refused the request.",
    "assistant.provider_unavailable": "The AI provider is not answering now: try again in a moment.",
    "assistant.internal_error": "The assistant failed: try again in a moment.",
}


class TurnRefused(Exception):
    """A turn that is not sent to the model: its status, its code and its plain sentence."""

    def __init__(self, status: int, code: str, message: str, *, fields: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields


# --- The conversation --------------------------------------------------------------------------------------------


def text_bytes(messages: list[dict]) -> int:
    """The size of the conversation's text, its attachments' data left out (they have their own limit)."""
    from assistant import attachments

    return len(json.dumps(attachments.without_data(messages), ensure_ascii=False, default=str).encode())


def check_roles(messages: list[dict]) -> None:
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") not in ROLES:
            raise TurnRefused(
                422,
                "invalid_payload",
                "The body is not the door's contract.",
                fields={f"messages.{index}.role": "one of system, user, assistant, tool"},
            )


def sanitized(messages: list[dict]) -> list[dict]:
    """``messages`` with an empty content for a missing one, and without a tool result whose call is not in the
    assistant message right before it (a provider refuses an orphan result)."""
    cleaned: list[dict] = []
    pending: set[str] = set()
    for message in messages:
        message = {**message, "content": "" if message.get("content") is None else message["content"]}
        role = message["role"]
        if role == "assistant":
            pending = {call.get("id") for call in message.get("tool_calls") or [] if isinstance(call, dict) and call.get("id")}
            cleaned.append(message)
        elif role == "tool":
            if message.get("tool_call_id") in pending:
                pending.discard(message["tool_call_id"])
                cleaned.append(message)
        else:
            pending = set()
            cleaned.append(message)
    return cleaned


def prepare(messages: list[dict], instructions: str, *, answer_kept: bool = False) -> list[dict]:
    """The conversation the model sees, or ``TurnRefused``: 422 for a message of an unknown role, 413 for a text
    over ``MAX_TEXT_BYTES`` or an attachment over its limit (``attachments.check``). Its documents are turned into
    their text (``attachments.expand``): CPU work, which the door runs off its event loop. The system message is the
    caller's instructions and what erplora.com's own tools need of the model (``server_tools.rules``)."""
    from assistant import attachments, server_tools

    check_roles(messages)
    attachments.check(messages)
    if text_bytes(messages) > MAX_TEXT_BYTES:
        raise TurnRefused(413, "payload_too_large", f"The conversation's text exceeds {MAX_TEXT_BYTES} bytes.")
    client = [message for message in messages if message["role"] != "system"]
    conversation = sanitized(client)[-(MAX_MESSAGES - 1) :]
    while conversation and conversation[0]["role"] == "tool":
        conversation = conversation[1:]
    system = "\n\n".join(part for part in (instructions, server_tools.rules(answer_kept=answer_kept)) if part)
    return [{"role": "system", "content": system}, *attachments.expand(conversation)]


def hub_tools(tools: Sequence[dict]) -> list[ToolSpec]:
    """The tools the Hub offers, plain (``{"name", "parameters"}``) or nested (``{"function": {…}}``); one without a
    name is left out."""
    specs: list[ToolSpec] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool["function"] if isinstance(tool.get("function"), dict) else tool
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        parameters = function.get("parameters") if isinstance(function.get("parameters"), dict) else None
        specs.append(
            ToolSpec(
                name=name,
                description=str(function.get("description") or ""),
                parameters=parameters or {"type": "object", "properties": {}},
            )
        )
    return specs


# --- The turn ----------------------------------------------------------------------------------------------------


def failure(payload: dict) -> dict:
    """The Hub's frame of a provider's failure: retriable or not, never the provider's words."""
    code = "assistant.provider_unavailable" if payload.get("retriable") else "assistant.provider_rejected"
    return {"type": "error", "code": code, "message": MESSAGES[code], "retriable": bool(payload.get("retriable"))}


def assistant_message(text: str, calls: list[dict]) -> dict:
    return {
        "role": "assistant",
        "content": text,
        "tool_calls": [
            {"id": call["call_id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
            for call in calls
        ],
    }


@dataclass
class Round:
    """One call to the model in a turn: the candidate that answered it, its text, its tools asked for and its failure."""

    answering: RouteCandidate
    text: str = ""
    calls: list[dict] = field(default_factory=list)
    failed: dict | None = None


async def ask(asked: Round, remaining: list, build, outcome: Outcome) -> AsyncIterator[dict]:
    """Stream one round through the route: the frames of its text as they come; ``asked`` and ``outcome`` filled."""
    async for event in routing.stream(remaining, build):
        payload = event.payload
        if event.type == "model":
            asked.answering = next(candidate for candidate in remaining if candidate.model == _uuid(payload["model"]))
        elif event.type == "fallback":
            logger.warning("assistant.turn.fallback from=%s to=%s status=%s", payload["from"], payload["to"], payload["status"])
        elif event.type == "text_delta":
            asked.text += payload["text"]
            outcome.text += payload["text"]
            outcome.answered = True
            yield {"type": "text_delta", "text": payload["text"]}
        elif event.type == "tool_call":
            asked.calls.append({"name": payload["name"], "call_id": payload["call_id"], "arguments": payload["arguments"]})
        elif event.type == "usage":
            outcome.add_usage(asked.answering, int(payload["input_tokens"]), int(payload["output_tokens"]))
        elif event.type == "error":
            asked.failed = payload


async def run_ours(started: Turn, conversation: list, asked: Round, mine: list, outcome: Outcome) -> AsyncIterator[dict]:
    """Run erplora.com's own tools the round asked for, on the caller's budget, and add their results to the
    conversation; the ``web`` frame once, when one brought pages that may not be kept."""
    from assistant import server_tools

    conversation.append(assistant_message(asked.text, mine))
    for call in mine:
        result = await server_tools.run(
            call["name"], call["arguments"], tool_budget(started.caller), answer_kept=started.answer_kept
        )
        outcome.sources += server_tools.sources_of(result)
        if not outcome.web and server_tools.not_to_keep(call["name"], result):
            outcome.web = True
            yield {"type": "web"}
        conversation.append({"role": "tool", "tool_call_id": call["call_id"], "content": result})


def closing_frames(outcome: Outcome, theirs: list) -> list[dict]:
    """The last frames of a turn: the line of its sources, when the answer names none of them, and the Hub's tools."""
    from assistant import server_tools

    frames: list[dict] = []
    line = server_tools.source_line(outcome.text, outcome.sources)
    if line:
        outcome.text += line
        frames.append({"type": "text_delta", "text": line})
    for call in theirs:
        outcome.calls.append(call)
        outcome.answered = True
        frames.append({"type": "function_call", **call})
    return frames


async def run(started: Turn, outcome: Outcome) -> AsyncIterator[dict]:
    """Stream the turn: the frames of the answer as they come; ``outcome`` filled as it goes. The tools erplora.com
    runs itself (``server_tools``) are run here, on the caller's budget, and the model is asked again, at most
    ``server_tools.MAX_ROUNDS`` times; on the last round they are not offered, so the model answers. A tool of the Hub
    named as one of ours is ours. An answer that names none of the sources they gave gets them written below it."""
    from assistant import attachments, server_tools

    conversation = list(started.messages)
    theirs_offered = [tool for tool in started.tools if not server_tools.is_server_tool(tool.name)]
    remaining = list(started.candidates)
    ours = server_tools.specs(answer_kept=started.answer_kept)
    rounds = 0
    while True:
        offered = theirs_offered + (ours if rounds < server_tools.MAX_ROUNDS else [])

        def build(candidate: RouteCandidate) -> TurnRequest:
            return TurnRequest(
                model_id=candidate.model_id,
                messages=attachments.for_model(conversation, vision=candidate.supports_vision),
                tools=offered,
                max_tokens=MAX_OUTPUT_TOKENS,
            )

        asked = Round(remaining[0])
        async for frame in ask(asked, remaining, build, outcome):
            yield frame
        if asked.failed is not None:
            # The status only: the provider's words may quote what the person wrote.
            logger.warning("assistant.turn.provider_failed status=%s retriable=%s", asked.failed.get("status"), asked.failed.get("retriable"))
            outcome.error = failure(asked.failed)
            yield outcome.error
            return
        remaining = remaining[remaining.index(asked.answering) :]
        mine = [call for call in asked.calls if server_tools.is_server_tool(call["name"])]
        theirs = [call for call in asked.calls if not server_tools.is_server_tool(call["name"])]
        if mine and not theirs and rounds < server_tools.MAX_ROUNDS:
            async for frame in run_ours(started, conversation, asked, mine, outcome):
                yield frame
            rounds += 1
            continue
        for frame in closing_frames(outcome, theirs):
            yield frame
        return


def _uuid(value: Any):
    from uuid import UUID

    return value if isinstance(value, UUID) else UUID(str(value))


# --- The turn as a door serves it -------------------------------------------------


class Refused(Exception):
    """A refusal before the model is called: its status, its code, its message (and the failing ``fields``, the
    ``Retry-After``, and what else its envelope says)."""

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


def spend(request: HttpRequest, bucket: str, rate: str, caller: Caller) -> None:
    """One call of ``caller``'s budget ``bucket``; over ``rate``, 429 ``rate_limited`` with the seconds left."""
    who = caller_key(caller)
    usage = get_usage(request, group=f"assistant.{bucket}", key=lambda group, request: who, rate=rate, increment=True)
    if usage is not None and usage["should_limit"]:
        wait = max(1, math.ceil(usage["time_left"]))
        logger.warning("assistant.internal.rate_limited bucket=%s caller=%s", bucket, who)
        raise Refused(
            429, "rate_limited", "Too many requests of this business: wait a moment and try again.", retry_after=wait
        )


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
    #: Whether the caller keeps what this turn answers (``server_tools``: what may not be kept is not used).
    answer_kept: bool


async def start(caller: Caller, data: Any, *, answer_kept: bool) -> Turn:
    """The checks before the model is called, each a refusal that counts nothing: the conversation (413, 422), the
    route (503 ``assistant.no_model`` or ``assistant.provider_not_configured``) and, unless it answers the tools the
    caller was asked for, a message of the allowance (429 ``assistant.quota_exceeded``). ``data`` carries the turn's
    ``messages``, ``instructions``, ``tools`` and ``continuation`` (``assistant.schemas.TurnIn``, or the panel's);
    ``answer_kept``, which every door has to say: whether its caller keeps what the turn answers."""
    try:
        messages = await sync_to_async(prepare, thread_sensitive=False)(
            data.messages, data.instructions, answer_kept=answer_kept
        )
    except TurnRefused as refused:
        raise Refused(refused.status, refused.code, refused.message, fields=refused.fields, retriable=False) from None
    try:
        route = await sync_to_async(queries.routing_policy.route_resolve)(platform_context(), RouteIn())
    except OperationError as refused:
        if refused.code not in ROUTE_REFUSALS:
            raise
        logger.warning("assistant.turn.no_route code=%s", refused.code)
        raise Refused(503, refused.code, refused.message, retriable=False) from None
    claim = None
    if not is_continuation(caller, data.continuation, messages):
        asked = ClaimIn(caller=caller, model=route.candidates[0].model_id)
        claim = await sync_to_async(services.turn_usage.message_claim)(platform_context(), asked)
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
    return Turn(caller, messages, hub_tools(data.tools), list(route.candidates), claim, answer_kept)


def settle(started: Turn, outcome: Outcome) -> dict:
    """After the turn: its message given back if nothing was answered, what each model spent recorded on its row; the
    usage after it."""
    claim = started.claim
    if claim is not None and not outcome.answered:
        given_back = MessageReleaseIn(caller=started.caller, month=claim.month, model=claim.model)
        services.turn_usage.message_release(platform_context(), given_back)
    for model, spent in outcome.spent.items():
        if spent.tokens_input or spent.tokens_output:
            services.turn_usage.usage_record(
                platform_context(),
                UsageRecordIn(
                    caller=started.caller,
                    model=model,
                    tokens_input=spent.tokens_input,
                    tokens_output=spent.tokens_output,
                    cost_usd=spent.cost,
                ),
            )
    return queries.usage.usage_show(platform_context(), started.caller).model_dump(mode="json")


def response_frame(started: Turn, outcome: Outcome) -> dict:
    token = continuation_token(started.caller, [call["call_id"] for call in outcome.calls]) if outcome.calls else None
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
    "message": MESSAGES["assistant.internal_error"],
    "retriable": True,
}


async def frames(started: Turn) -> AsyncIterator[dict | str]:
    """The frames of the turn, then ``response`` (unless it failed), ``usage`` and ``"[DONE]"``. Whatever ends it (the
    end, a failure, the caller closing the stream) settles the message and what it spent."""
    outcome = Outcome()
    try:
        async for frame in run(started, outcome):
            yield frame
        if outcome.error is None:
            yield response_frame(started, outcome)
    except Exception:
        logger.exception("assistant.turn.failed")
        outcome.error = INTERNAL_ERROR
        yield INTERNAL_ERROR
    finally:
        usage = await asyncio.shield(sync_to_async(settle)(started, outcome))
    yield {"type": "usage", **usage}
    yield "[DONE]"


async def stream(started: Turn) -> AsyncIterator[str]:
    """``frames`` as server-sent events, as the Hub's door sends them; closed with them, so a caller that hangs up
    settles the turn at once."""
    async with aclosing(frames(started)) as framed:
        async for frame in framed:
            yield sse(frame)
