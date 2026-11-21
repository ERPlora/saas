"""The token of a continuation: when the model asks for tools of the Hub, the turn ends there with it
(``assistant.turn``), and the Hub sends it back with their results so that turn costs no message. The token is signed,
names the business and the calls, lasts ``CONTINUATION_SECONDS`` and serves once.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from django.core import signing
from django.core.cache import cache

from assistant.schemas import Caller

#: How long the Hub has to send back the results of the tools it was asked for, at no message.
CONTINUATION_SECONDS = 15 * 60
CONTINUATION_SALT = "assistant.continuation"


def caller_key(caller: Caller) -> str:
    """The caller as its budgets and continuations name it: ``hub:<id>``, ``demo:<address>`` or ``user:<id>``."""
    if caller.demo:
        return f"demo:{caller.demo}"
    if caller.user_id is not None:
        return f"user:{caller.user_id}"
    return f"hub:{caller.hub_id}"


def tool_budget(caller: Caller) -> str:
    """Whose budget a call of erplora.com's tools spends: the caller's, and one for every demo, since anybody can open
    another."""
    return "demo" if caller.demo else caller_key(caller)


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
