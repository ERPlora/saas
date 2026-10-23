"""A turn of the Hub's assistant through the gateway (ASSISTANT-G43, G31, G46): the conversation made ready for the
model, the tools offered, the answer streamed as the Hub's frames, and what it spent.

The conversation is the Hub's (the person's browser owns it, ADR-0149 of the old product): erplora.com uses it for
the call and forgets it. ``prepare`` refuses what is too big (never cuts it), drops the client's system messages for
the Hub's ``instructions``, drops a tool result whose call is not there and keeps the last ``MAX_MESSAGES``. ``run``
streams the turn through its route (``assistant.routing.stream``: the model that answers, then its fallback if the
provider fails before answering) and yields the frames the Hub reads:

    {"type": "text_delta", "text": str}
    {"type": "function_call", "name": str, "call_id": str, "arguments": str}     # a tool of the Hub, for it to run
    {"type": "error", "code": str, "message": str, "retriable": bool}

``Outcome`` keeps what the door needs after the stream: the text, the Hub's tool calls, the tokens and their cost
(with the prices of the model that answered), whether anything was answered and the error. The provider's own words
of a failure reach neither the Hub nor a log (they may quote the conversation): the Hub gets a code and a plain
sentence, the log the status.

When the model asks for tools of the Hub, the turn ends there with a ``continuation`` token: the Hub runs them and
sends the conversation back with their results and that token, and that turn costs no message (it answers the same
request of the person). The token is signed, names the business and the calls, lasts ``CONTINUATION_SECONDS`` and
serves once.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.core import signing
from django.core.cache import cache

from assistant import routing
from assistant.models import estimate_cost
from assistant.providers.base import ToolSpec, TurnRequest
from assistant.schemas import Caller, RouteCandidate

logger = logging.getLogger(__name__)

#: The messages of a conversation the model sees: the last ones (the system message apart).
MAX_MESSAGES = 100
#: The text of a conversation (its attachments apart, ``attachments``): over it the turn is refused, never cut.
MAX_TEXT_BYTES = 1_000_000
#: The longest answer of one call to the model, in tokens.
MAX_OUTPUT_TOKENS = 4096
#: How long the Hub has to send back the results of the tools it was asked for, at no message.
CONTINUATION_SECONDS = 15 * 60
CONTINUATION_SALT = "assistant.continuation"
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


def prepare(messages: list[dict], instructions: str) -> list[dict]:
    """The conversation the model sees, or ``TurnRefused``: 422 for a message of an unknown role, 413 for a text
    over ``MAX_TEXT_BYTES`` or an attachment over its limit (``attachments.check``). Its documents are turned into
    their text (``attachments.expand``): CPU work, which the door runs off its event loop."""
    from assistant import attachments

    check_roles(messages)
    attachments.check(messages)
    if text_bytes(messages) > MAX_TEXT_BYTES:
        raise TurnRefused(413, "payload_too_large", f"The conversation's text exceeds {MAX_TEXT_BYTES} bytes.")
    client = [message for message in messages if message["role"] != "system"]
    conversation = sanitized(client)[-(MAX_MESSAGES - 1) :]
    while conversation and conversation[0]["role"] == "tool":
        conversation = conversation[1:]
    return [{"role": "system", "content": instructions or ""}, *attachments.expand(conversation)]


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


# --- The token of a continuation ---------------------------------------------------------------------------------


def caller_key(caller: Caller) -> str:
    return f"demo:{caller.demo}" if caller.demo else f"hub:{caller.hub_id}"


def continuation_token(caller: Caller, call_ids: Sequence[str]) -> str:
    """The token the Hub sends back with the results of ``call_ids``, for that turn to cost no message."""
    return signing.dumps({"c": caller_key(caller), "t": sorted(call_ids)}, salt=CONTINUATION_SALT, compress=True)


def answered_calls(messages: list[dict]) -> set[str]:
    """The calls whose results end the conversation (after its last assistant message), or none."""
    ids: set[str] = set()
    for message in reversed(messages):
        if message.get("role") != "tool":
            break
        ids.add(str(message.get("tool_call_id") or ""))
    return ids


def is_continuation(caller: Caller, token: str | None, messages: list[dict]) -> bool:
    """Whether this turn answers the tools ``token`` asked for, of this caller, in time and for the first time."""
    if not token:
        return False
    try:
        claimed = signing.loads(token, salt=CONTINUATION_SALT, max_age=CONTINUATION_SECONDS)
    except signing.BadSignature:
        return False
    if not isinstance(claimed, dict) or claimed.get("c") != caller_key(caller):
        return False
    if set(claimed.get("t") or []) != answered_calls(messages) or not claimed.get("t"):
        return False
    used = f"assistant:continuation:{hashlib.sha256(token.encode()).hexdigest()}"
    return cache.add(used, 1, CONTINUATION_SECONDS)


# --- The turn ----------------------------------------------------------------------------------------------------


@dataclass
class Outcome:
    """What a turn produced, for the door to answer and record after it."""

    text: str = ""
    calls: list[dict] = field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    cost: Decimal = Decimal("0")
    answered: bool = False
    error: dict | None = None

    def output(self) -> list[dict]:
        items: list[dict] = []
        if self.text:
            items.append({"type": "message", "content": [{"type": "output_text", "text": self.text}]})
        items.extend({"type": "function_call", **call} for call in self.calls)
        return items


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


async def run(
    candidates: Sequence[RouteCandidate], messages: list[dict], tools: list[ToolSpec], outcome: Outcome
) -> AsyncIterator[dict]:
    """Stream the turn: the frames of the answer as they come; ``outcome`` filled as it goes. The tools erplora.com
    runs itself (``server_tools``) are run here and the model is asked again, at most ``server_tools.MAX_ROUNDS``
    times; on the last round they are not offered, so the model answers. A tool of the Hub named as one of ours is
    ours."""
    from assistant import attachments, server_tools

    conversation = list(messages)
    theirs_offered = [tool for tool in tools if not server_tools.is_server_tool(tool.name)]
    remaining = list(candidates)
    rounds = 0
    while True:
        offered = theirs_offered + (server_tools.specs() if rounds < server_tools.MAX_ROUNDS else [])
        text, calls, failed, answering = "", [], None, remaining[0]

        def build(candidate: RouteCandidate) -> TurnRequest:
            return TurnRequest(
                model_id=candidate.model_id,
                messages=attachments.for_model(conversation, vision=candidate.supports_vision),
                tools=offered,
                max_tokens=MAX_OUTPUT_TOKENS,
            )

        async for event in routing.stream(remaining, build):
            payload = event.payload
            if event.type == "model":
                answering = next(candidate for candidate in remaining if candidate.model == _uuid(payload["model"]))
            elif event.type == "fallback":
                logger.warning("assistant.turn.fallback from=%s to=%s status=%s", payload["from"], payload["to"], payload["status"])
            elif event.type == "text_delta":
                text += payload["text"]
                outcome.text += payload["text"]
                outcome.answered = True
                yield {"type": "text_delta", "text": payload["text"]}
            elif event.type == "tool_call":
                calls.append({"name": payload["name"], "call_id": payload["call_id"], "arguments": payload["arguments"]})
            elif event.type == "usage":
                spent_in, spent_out = int(payload["input_tokens"]), int(payload["output_tokens"])
                outcome.tokens_input += spent_in
                outcome.tokens_output += spent_out
                outcome.cost += estimate_cost(
                    answering.price_input_per_1m, answering.price_output_per_1m, spent_in, spent_out
                )
            elif event.type == "error":
                failed = payload
        if failed is not None:
            # The status only: the provider's words may quote what the person wrote (ASSISTANT-G49).
            logger.warning("assistant.turn.provider_failed status=%s retriable=%s", failed.get("status"), failed.get("retriable"))
            outcome.error = failure(failed)
            yield outcome.error
            return
        remaining = remaining[remaining.index(answering) :]
        mine = [call for call in calls if server_tools.is_server_tool(call["name"])]
        theirs = [call for call in calls if not server_tools.is_server_tool(call["name"])]
        if mine and not theirs and rounds < server_tools.MAX_ROUNDS:
            conversation.append(assistant_message(text, mine))
            for call in mine:
                result = await server_tools.run(call["name"], call["arguments"])
                conversation.append({"role": "tool", "tool_call_id": call["call_id"], "content": result})
            rounds += 1
            continue
        for call in theirs:
            outcome.calls.append(call)
            outcome.answered = True
            yield {"type": "function_call", **call}
        return


def _uuid(value: Any):
    from uuid import UUID

    return value if isinstance(value, UUID) else UUID(str(value))
