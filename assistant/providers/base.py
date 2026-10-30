"""What every provider's client shares (ASSISTANT-G33): the normalized events, the request of one turn, the reading
of a server-sent stream and the classification of upstream failures.

Each concrete client (``openai``, ``deepseek``, ``anthropic``, ``gemini``) translates the canonical conversation (the
Chat Completions shape: ``system`` / ``user`` / ``assistant`` with ``tool_calls`` / ``tool`` messages) into its API,
streams the answer over ``httpx`` and yields ``ProviderEvent``s:

    text_delta  {"text": str}
    tool_call   {"call_id": str, "name": str, "arguments": str}     # arguments as a JSON string
    usage       {"input_tokens": int, "output_tokens": int}
    error       {"message": str, "retriable": bool, "status": int | None}
    finish      {"reason": "stop" | "tool_use" | "length" | "content_filter" | "error"}

A turn always ends with exactly one ``finish``; an upstream failure is an ``error`` followed by ``finish`` ``error``,
never an exception, so the caller decides whether to try the fallback model (``retriable``). No message ever carries
the key (``redact``). Every client is made by ``open_client``: a server whose trusted certificates cannot be loaded
(``SSL_CERT_FILE`` naming a file that is not there, or that holds none) fails there, before it connects, even to an
``http://`` address, as a final failure that names the setting and its file, in the message and in the log.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: Connect, write and pool limits short; a read may wait for the model to think (a stream's pause between events).
TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
#: Listing a provider's models is a quick call.
LIST_TIMEOUT = httpx.Timeout(15.0)
# Upstream statuses a later attempt can clear: timeout, conflict, too early, rate limit; and every 5xx.
_RETRIABLE_CLIENT_STATUSES = frozenset({408, 409, 425, 429})


class ProviderError(Exception):
    """A provider's call that failed (listing its models)."""

    def __init__(self, message: str, *, retriable: bool = False, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.retriable = retriable
        self.status = status


class ProviderUnavailable(ProviderError):
    """The provider cannot be called: no key, an unknown API."""


class TrustStoreUnreadable(Exception):
    """The server's trusted certificates cannot be loaded: its configuration, so no attempt nor fallback clears it."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def open_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    """An ``httpx`` client, or ``TrustStoreUnreadable`` naming where its certificates were read from, logged."""
    try:
        return httpx.AsyncClient(timeout=timeout)
    except OSError as problem:  # FileNotFoundError, PermissionError, ssl.SSLError (a file with no certificate)
        path = os.environ.get("SSL_CERT_FILE")
        source = f"SSL_CERT_FILE={path}" if path else "the default certificates"
        message = f"the server's trusted certificates cannot be loaded from {source} ({problem.strerror or problem})"
        logger.error("assistant.provider.trust_store_unreadable %s", message)
        raise TrustStoreUnreadable(message) from None


def is_retriable_status(status: int | None) -> bool:
    """Whether another attempt can succeed after an upstream answer with ``status`` (``None``: no answer at all)."""
    if status is None:
        return True
    return not 400 <= status < 500 or status in _RETRIABLE_CLIENT_STATUSES


def redact(message: str, api_key: str) -> str:
    """``message`` without the key, should a provider repeat it."""
    return message.replace(api_key, "…") if api_key else message


@dataclass(frozen=True)
class ProviderEvent:
    type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    """A tool offered to the model; its JSON Schema in ``parameters``."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class TurnRequest:
    """One turn, in the canonical Chat Completions shape."""

    model_id: str
    messages: list[dict[str, Any]]
    tools: list[ToolSpec] = field(default_factory=list)
    system: str = ""
    max_tokens: int = 4096
    temperature: float | None = None


@dataclass(frozen=True)
class DiscoveredModel:
    """A chat model a provider's API lists (``context_window`` 0 when the API does not say it)."""

    model_id: str
    display_name: str
    context_window: int = 0


async def sse_events(response: httpx.Response) -> AsyncIterator[tuple[str | None, str]]:
    """``(event name, data)`` of each server-sent event of ``response``, however its bytes are split."""
    name: str | None = None
    data: list[str] = []
    buffer = ""
    async for text in response.aiter_text():
        buffer += text
        while True:
            cut = buffer.find("\n")
            if cut < 0:
                break
            line, buffer = buffer[:cut].rstrip("\r"), buffer[cut + 1 :]
            if line == "":
                if data:
                    yield name, "\n".join(data)
                name, data = None, []
            elif line.startswith(":"):
                continue
            elif line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data.append(line[len("data:") :].removeprefix(" "))
    line = buffer.rstrip("\r")
    if line.startswith("data:"):
        data.append(line[len("data:") :].removeprefix(" "))
    if data:
        yield name, "\n".join(data)


def error_event(message: str, *, retriable: bool, status: int | None = None) -> ProviderEvent:
    return ProviderEvent("error", {"message": message, "retriable": retriable, "status": status})


def finish_event(reason: str) -> ProviderEvent:
    return ProviderEvent("finish", {"reason": reason})


def upstream_message(body: bytes, status: int) -> str:
    """The provider's own words for a failed answer (``error.message`` in every API's envelope), else its status."""
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
        if parsed.get("message"):
            return str(parsed["message"])
    return f"HTTP {status}"


class Provider(ABC):
    """The client of one provider's API, with its key and its address (``AIProvider.api_base``)."""

    kind: str = ""

    def __init__(self, *, api_key: str, base_url: str):
        if not api_key:
            raise ProviderUnavailable(f"{self.kind}: no key")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.base_url}>"

    # --- What each API defines --------------------------------------------------------------------------

    @abstractmethod
    def chat_request(self, req: TurnRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        """``(url, headers, json body)`` of a streamed turn."""

    @abstractmethod
    def parse_stream(self, response: httpx.Response, req: TurnRequest) -> AsyncIterator[ProviderEvent]:
        """The events of a streamed answer that began well, ending with exactly one ``finish``."""

    @abstractmethod
    async def list_models(self) -> list[DiscoveredModel]:
        """The chat models the provider's API lists with this key; ``ProviderError`` if the call fails."""

    # --- Shared -----------------------------------------------------------------------------------------

    async def stream_turn(self, req: TurnRequest) -> AsyncIterator[ProviderEvent]:
        url, headers, body = self.chat_request(req)
        try:
            async with open_client(TIMEOUT) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code >= 400:
                        raw = await response.aread()
                        status = response.status_code
                        message = redact(upstream_message(raw, status), self.api_key)
                        yield error_event(f"{self.kind}: {message}", retriable=is_retriable_status(status), status=status)
                        yield finish_event("error")
                        return
                    async for event in self.parse_stream(response, req):
                        yield event
        except TrustStoreUnreadable as problem:
            yield error_event(redact(f"{self.kind}: {problem.message}", self.api_key), retriable=False)
            yield finish_event("error")
        except httpx.TimeoutException:
            yield error_event(f"{self.kind}: the provider took too long to answer", retriable=True)
            yield finish_event("error")
        except httpx.HTTPError as problem:
            yield error_event(f"{self.kind}: the provider could not be reached ({type(problem).__name__})", retriable=True)
            yield finish_event("error")

    async def get_json(self, url: str, headers: dict[str, str]) -> Any:
        """A listing call's JSON; ``ProviderError`` with the provider's words if it fails."""
        try:
            async with open_client(LIST_TIMEOUT) as client:
                response = await client.get(url, headers=headers)
        except TrustStoreUnreadable as problem:
            raise ProviderError(redact(f"{self.kind}: {problem.message}", self.api_key), retriable=False) from None
        except httpx.TimeoutException:
            raise ProviderError(f"{self.kind}: the provider took too long to answer", retriable=True) from None
        except httpx.HTTPError as problem:
            raise ProviderError(
                f"{self.kind}: the provider could not be reached ({type(problem).__name__})", retriable=True
            ) from None
        if response.status_code >= 400:
            status = response.status_code
            message = redact(upstream_message(response.content, status), self.api_key)
            raise ProviderError(f"{self.kind}: {message}", retriable=is_retriable_status(status), status=status)
        try:
            return response.json()
        except ValueError:
            raise ProviderError(f"{self.kind}: the provider's answer is not readable", retriable=True) from None

    @staticmethod
    def normalize_tool_arguments(raw: str | dict | None) -> str:
        """Tool arguments as a JSON string (OpenAI streams a string; Anthropic and Gemini give an object)."""
        if raw is None or raw == "":
            return "{}"
        if isinstance(raw, str):
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                return json.dumps({"_raw": raw})
            return raw
        return json.dumps(raw)

    @staticmethod
    def merge_consecutive_same_role(messages: list[dict]) -> list[dict]:
        """One message per turn of a role (Anthropic wants user and assistant to alternate)."""
        merged: list[dict] = []
        for message in messages:
            if merged and merged[-1].get("role") == message.get("role"):
                previous = merged[-1]
                before = (
                    previous["content"]
                    if isinstance(previous.get("content"), list)
                    else [{"type": "text", "text": str(previous.get("content", ""))}]
                )
                after = (
                    message["content"]
                    if isinstance(message.get("content"), list)
                    else [{"type": "text", "text": str(message.get("content", ""))}]
                )
                merged[-1] = {**previous, "content": before + after}
            else:
                merged.append(message)
        return merged

    @staticmethod
    def split_system_messages(messages: list[dict]) -> tuple[str, list[dict]]:
        """``(system text, the rest)``: Anthropic and Gemini take the instructions apart from the messages."""
        system: list[str] = []
        rest: list[dict] = []
        for message in messages:
            if message.get("role") == "system":
                content = message.get("content", "")
                if isinstance(content, str) and content.strip():
                    system.append(content)
            else:
                rest.append(message)
        return "\n\n".join(system), rest
