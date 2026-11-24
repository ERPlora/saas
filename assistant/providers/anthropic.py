"""The client of Anthropic's Messages API: ``POST {base}/v1/messages`` streamed, ``GET
{base}/v1/models`` page by page to list.

The instructions go apart (``system``), tool results are ``tool_result`` blocks of a user turn, the assistant's tool
calls ``tool_use`` blocks, images ``image`` blocks and PDFs ``document`` blocks; user and assistant alternate
(consecutive turns of one role are merged). One tool per answer (``disable_parallel_tool_use``).

Each call asks Anthropic to cache what it sent, in the order Anthropic reads it: the tools up to the last one, the
instructions, and the conversation up to its last message. The next call of the same request sends the same start
and Anthropic reads it from its cache instead of processing it again; one that changes the instructions still reads
the tools. Its usage says the whole input, of which what the cache read and wrote.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import httpx

from assistant.providers.base import (
    DiscoveredModel,
    Provider,
    ProviderEvent,
    TurnRequest,
    error_event,
    finish_event,
    is_retriable_status,
    redact,
    sse_events,
)

API_VERSION = "2023-06-01"
FINISH_REASONS = {"end_turn": "stop", "stop_sequence": "stop", "tool_use": "tool_use", "max_tokens": "length", "refusal": "content_filter", "pause_turn": "stop"}
#: Anthropic's error types and the status they stand for, to tell whether another attempt can clear them.
ERROR_STATUS = {"overloaded_error": 529, "api_error": 500, "rate_limit_error": 429, "timeout_error": 504, "invalid_request_error": 400, "authentication_error": 401, "permission_error": 403, "not_found_error": 404}


#: Where a call asks Anthropic to cache what it sent: five minutes from its last read, as every call of a request reads.
CACHED = {"type": "ephemeral"}
#: The counts of Anthropic's usage: the input after its last cache point, what its cache read and wrote, the output.
COUNTS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")


def _event_of(data: str) -> dict:
    """A streamed event, or nothing for what is not one."""
    try:
        event = json.loads(data)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def arguments_of(tool: dict[str, str]) -> str:
    return Provider.normalize_tool_arguments(tool["arguments"])


class Answer:
    """What a streamed answer said so far: the tools it is writing, its counts and why it stopped."""

    def __init__(self) -> None:
        self.tools: dict[int, dict[str, str]] = {}
        self.counts: dict[str, int] = {}
        self.counted = False
        self.reason = "stop"

    def read(self, event: dict) -> str:
        """Take ``event`` in; the text it adds to the answer (``""`` for none)."""
        kind = event.get("type")
        if kind == "message_start":
            self.counted = True
            self.count((event.get("message") or {}).get("usage") or {})
        elif kind == "content_block_start":
            self.start(event)
        elif kind == "content_block_delta":
            return self.write(event)
        elif kind == "message_delta":
            stop = (event.get("delta") or {}).get("stop_reason")
            self.reason = FINISH_REASONS.get(stop, "stop") if stop else self.reason
            self.count(event.get("usage") or {})
        return ""

    def count(self, usage: dict) -> None:
        """Anthropic's counts add up as the answer goes: a later one replaces the earlier."""
        for name in COUNTS:
            if name in usage:
                self.counts[name] = int(usage[name] or 0)
                self.counted = True

    def start(self, event: dict) -> None:
        block = event.get("content_block") or {}
        if block.get("type") == "tool_use":
            tool = {"id": block.get("id", ""), "name": block.get("name", ""), "arguments": ""}
            self.tools[int(event.get("index") or 0)] = tool

    def write(self, event: dict) -> str:
        delta = event.get("delta") or {}
        if delta.get("type") == "text_delta":
            return delta.get("text") or ""
        tool = self.tools.get(int(event.get("index") or 0))
        if delta.get("type") == "input_json_delta" and tool is not None:
            tool["arguments"] += delta.get("partial_json") or ""
        return ""

    def usage(self) -> dict[str, int]:
        """The ``usage`` event: all of the input (Anthropic counts what its cache read and wrote apart from the rest),
        of which what the cache read and wrote, and the output."""
        read = self.counts.get("cache_read_input_tokens", 0)
        written = self.counts.get("cache_creation_input_tokens", 0)
        return {
            "input_tokens": self.counts.get("input_tokens", 0) + read + written,
            "output_tokens": self.counts.get("output_tokens", 0),
            "cache_read_tokens": read,
            "cache_write_tokens": written,
        }

    def closing(self) -> list[ProviderEvent]:
        """The events after the stream: each tool asked for, whole, its usage if it said any, and its end."""
        events = [
            ProviderEvent("tool_call", {"call_id": tool["id"], "name": tool["name"], "arguments": arguments_of(tool)})
            for _, tool in sorted(self.tools.items())
        ]
        if self.counted:
            events.append(ProviderEvent("usage", self.usage()))
        events.append(finish_event("tool_use" if self.tools and self.reason == "stop" else self.reason))
        return events


class AnthropicProvider(Provider):
    kind = "anthropic"

    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": API_VERSION, "content-type": "application/json"}

    def user_block(self, part: dict) -> dict | None:
        """A part of a person's message as Anthropic's block: its text, an image or a PDF; ``None`` for any other."""
        if part.get("type") == "text":
            return {"type": "text", "text": part.get("text", "")}
        inline = self.inline_data(part)
        if inline is None:
            return None
        media_type, data = inline
        kind = "document" if part.get("type") == "file" else "image"
        return {"type": kind, "source": {"type": "base64", "media_type": media_type, "data": data}}

    def to_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system, rest = self.split_system_messages(messages)
        translated: list[dict] = []
        for message in rest:
            role = message.get("role")
            content = message.get("content", "")
            if role == "user":
                if isinstance(content, list):
                    blocks = [block for block in map(self.user_block, content) if block is not None]
                    translated.append({"role": "user", "content": blocks or content})
                else:
                    translated.append({"role": "user", "content": content})
            elif role == "assistant":
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except (TypeError, ValueError):
                        arguments = {}
                    blocks.append({"type": "tool_use", "id": call.get("id", ""), "name": function.get("name", ""), "input": arguments})
                translated.append({"role": "assistant", "content": blocks or content})
            elif role == "tool":
                translated.append(
                    {
                        "role": "user",
                        "content": [{"type": "tool_result", "tool_use_id": message.get("tool_call_id", ""), "content": content}],
                    }
                )
        return system, self.merge_consecutive_same_role(translated)

    def chat_request(self, req: TurnRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        system, messages = self.to_messages(req.messages)
        if req.system:
            system = f"{system}\n\n{req.system}" if system else req.system
        body: dict[str, Any] = {
            "model": req.model_id,
            "max_tokens": req.max_tokens,
            "messages": messages,
            "stream": True,
            "cache_control": CACHED,
        }
        if system:
            body["system"] = [{"type": "text", "text": system, "cache_control": CACHED}]
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.tools:
            tools = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in req.tools]
            tools[-1]["cache_control"] = CACHED
            body["tools"] = tools
            body["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}
        return f"{self.base_url}/v1/messages", self.headers(), body

    async def parse_stream(self, response: httpx.Response, req: TurnRequest) -> AsyncIterator[ProviderEvent]:
        answer = Answer()
        async for _, data in sse_events(response):
            event = _event_of(data)
            if event.get("type") == "error":
                yield self.stream_error(event.get("error") or {})
                yield finish_event("error")
                return
            text = answer.read(event)
            if text:
                yield ProviderEvent("text_delta", {"text": text})
        for event in answer.closing():
            yield event

    def stream_error(self, error: dict) -> ProviderEvent:
        """The ``error`` event of a failure the stream announced, retriable as its type says."""
        status = ERROR_STATUS.get(error.get("type"))
        message = redact(str(error.get("message") or "error"), self.api_key)
        return error_event(f"{self.kind}: {message}", retriable=is_retriable_status(status))

    async def list_models(self) -> list[DiscoveredModel]:
        found: dict[str, DiscoveredModel] = {}
        after = ""
        for _ in range(50):
            url = f"{self.base_url}/v1/models?limit=1000" + (f"&after_id={quote(after)}" if after else "")
            page = await self.get_json(url, self.headers()) or {}
            for item in page.get("data") or []:
                if item.get("id"):
                    found[item["id"]] = DiscoveredModel(model_id=item["id"], display_name=item.get("display_name") or item["id"])
            if not page.get("has_more") or not page.get("last_id"):
                break
            after = page["last_id"]
        return sorted(found.values(), key=lambda model: model.model_id)
