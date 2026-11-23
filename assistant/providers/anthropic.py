"""The client of Anthropic's Messages API: ``POST {base}/v1/messages`` streamed, ``GET
{base}/v1/models`` page by page to list.

The instructions go apart (``system``), tool results are ``tool_result`` blocks of a user turn, the assistant's tool
calls ``tool_use`` blocks, images ``image`` blocks and PDFs ``document`` blocks; user and assistant alternate
(consecutive turns of one role are merged). One tool per answer (``disable_parallel_tool_use``).

A request with a reasoning effort asks for adaptive thinking at that effort (``output_config.effort``), with room for
the thinking in ``max_tokens``, which counts it. Thinking is never text: an answer that thought comes out whole as
``reasoning`` and goes back exactly as it came in the tool rounds of its turn, as Anthropic requires.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import httpx

from assistant.providers.base import (
    REASONING,
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
#: The least ``max_tokens`` of a request that asks for thinking (the size of Anthropic's own adaptive thinking examples).
REASONING_MAX_TOKENS = 16000
THINKING_BLOCKS = frozenset({"thinking", "redacted_thinking"})
#: The field of its block each streamed delta adds to.
DELTA_FIELDS = {"text_delta": "text", "thinking_delta": "thinking", "signature_delta": "signature"}


class StreamedAnswer:
    """A streamed answer as it arrives: its blocks by their index, its usage and how it ended."""

    def __init__(self):
        self.blocks: dict[int, dict] = {}
        self.arguments: dict[int, str] = {}
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.seen_usage = False
        self.reason = "stop"

    def take(self, event: dict) -> str:
        """Read one event of the stream; the text it adds to the answer."""
        kind = event.get("type")
        if kind == "message_start":
            self.started((event.get("message") or {}).get("usage") or {})
        elif kind == "content_block_start":
            self.block_started(int(event.get("index") or 0), dict(event.get("content_block") or {}))
        elif kind == "content_block_delta":
            return self.block_grew(int(event.get("index") or 0), event.get("delta") or {})
        elif kind == "message_delta":
            self.ended((event.get("delta") or {}).get("stop_reason"), event.get("usage") or {})
        return ""

    def started(self, usage: dict) -> None:
        self.usage = {"input_tokens": int(usage.get("input_tokens") or 0), "output_tokens": int(usage.get("output_tokens") or 0)}
        self.seen_usage = True

    def block_started(self, index: int, block: dict) -> None:
        self.blocks[index] = block
        if block.get("type") == "tool_use":
            self.arguments[index] = ""

    def block_grew(self, index: int, delta: dict) -> str:
        kind = delta.get("type")
        if kind == "input_json_delta":
            if index in self.arguments:
                self.arguments[index] += delta.get("partial_json") or ""
            return ""
        field = DELTA_FIELDS.get(kind)
        piece = str(delta.get(field) or "") if field else ""
        if piece and index in self.blocks:
            self.blocks[index][field] = self.blocks[index].get(field, "") + piece
        return piece if kind == "text_delta" else ""

    def ended(self, stop: str | None, usage: dict) -> None:
        if stop:
            self.reason = FINISH_REASONS.get(stop, "stop")
        if "output_tokens" in usage:
            self.usage["output_tokens"] = int(usage["output_tokens"] or 0)
            self.seen_usage = True

    def events(self) -> list[ProviderEvent]:
        """What the answer gave once it ended: itself whole if it thought, its tool calls, its usage and its end."""
        arguments = {index: Provider.normalize_tool_arguments(raw) for index, raw in sorted(self.arguments.items())}
        for index, raw in arguments.items():
            self.blocks[index]["input"] = json.loads(raw)
        blocks = [self.blocks[index] for index in sorted(self.blocks)]
        events = []
        if any(block.get("type") in THINKING_BLOCKS for block in blocks):
            events.append(ProviderEvent("reasoning", {"blocks": blocks}))
        for index, raw in arguments.items():
            call = {"call_id": self.blocks[index].get("id", ""), "name": self.blocks[index].get("name", ""), "arguments": raw}
            events.append(ProviderEvent("tool_call", call))
        if self.seen_usage:
            events.append(ProviderEvent("usage", self.usage))
        events.append(finish_event("tool_use" if arguments and self.reason == "stop" else self.reason))
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

    def user_turn(self, content: Any) -> dict:
        if isinstance(content, list):
            blocks = [block for block in map(self.user_block, content) if block is not None]
            return {"role": "user", "content": blocks or content}
        return {"role": "user", "content": content}

    @staticmethod
    def tool_use(call: dict) -> dict:
        function = call.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except (TypeError, ValueError):
            arguments = {}
        return {"type": "tool_use", "id": call.get("id", ""), "name": function.get("name", ""), "input": arguments}

    def assistant_turn(self, message: dict) -> dict:
        """An answer of the model: exactly as it came when it kept its reasoning, else its text and its tool calls."""
        if message.get(REASONING):
            return {"role": "assistant", "content": message[REASONING]}
        content = message.get("content", "")
        blocks = [{"type": "text", "text": content}] if content else []
        blocks += [self.tool_use(call) for call in message.get("tool_calls") or []]
        return {"role": "assistant", "content": blocks or content}

    def to_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system, rest = self.split_system_messages(messages)
        translated: list[dict] = []
        for message in rest:
            role = message.get("role")
            if role == "user":
                translated.append(self.user_turn(message.get("content", "")))
            elif role == "assistant":
                translated.append(self.assistant_turn(message))
            elif role == "tool":
                result = {"type": "tool_result", "tool_use_id": message.get("tool_call_id", ""), "content": message.get("content", "")}
                translated.append({"role": "user", "content": [result]})
        return system, self.merge_consecutive_same_role(translated)

    def chat_request(self, req: TurnRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        system, messages = self.to_messages(req.messages)
        if req.system:
            system = f"{system}\n\n{req.system}" if system else req.system
        body: dict[str, Any] = {"model": req.model_id, "max_tokens": req.max_tokens, "messages": messages, "stream": True}
        if system:
            body["system"] = system
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.reasoning_effort:
            body["thinking"] = {"type": "adaptive"}
            body["output_config"] = {"effort": req.reasoning_effort}
            body["max_tokens"] = max(req.max_tokens, REASONING_MAX_TOKENS)
        if req.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in req.tools]
            body["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}
        return f"{self.base_url}/v1/messages", self.headers(), body

    def stream_error(self, event: dict) -> ProviderEvent:
        error = event.get("error") or {}
        status = ERROR_STATUS.get(error.get("type"))
        message = redact(str(error.get("message") or "error"), self.api_key)
        return error_event(f"{self.kind}: {message}", retriable=is_retriable_status(status))

    async def parse_stream(self, response: httpx.Response, req: TurnRequest) -> AsyncIterator[ProviderEvent]:
        answer = StreamedAnswer()
        async for _, data in sse_events(response):
            try:
                event = json.loads(data)
            except ValueError:
                continue
            if event.get("type") == "error":
                yield self.stream_error(event)
                yield finish_event("error")
                return
            if text := answer.take(event):
                yield ProviderEvent("text_delta", {"text": text})
        for event in answer.events():
            yield event

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
