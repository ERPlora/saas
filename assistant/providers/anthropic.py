"""The client of Anthropic's Messages API (ASSISTANT-G32): ``POST {base}/v1/messages`` streamed, ``GET
{base}/v1/models`` page by page to list.

The instructions go apart (``system``), tool results are ``tool_result`` blocks of a user turn, the assistant's tool
calls ``tool_use`` blocks, images ``image`` blocks; user and assistant alternate (consecutive turns of one role are
merged). One tool per answer (``disable_parallel_tool_use``).
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


class AnthropicProvider(Provider):
    kind = "anthropic"

    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": API_VERSION, "content-type": "application/json"}

    def to_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system, rest = self.split_system_messages(messages)
        translated: list[dict] = []
        for message in rest:
            role = message.get("role")
            content = message.get("content", "")
            if role == "user":
                if isinstance(content, list):
                    blocks: list[dict] = []
                    for part in content:
                        if part.get("type") == "text":
                            blocks.append({"type": "text", "text": part.get("text", "")})
                        elif part.get("type") == "image_url":
                            url = (part.get("image_url") or {}).get("url", "")
                            if url.startswith("data:") and "," in url:
                                media_type = url.split(";")[0].split(":", 1)[1]
                                blocks.append(
                                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": url.split(",", 1)[1]}}
                                )
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
        body: dict[str, Any] = {"model": req.model_id, "max_tokens": req.max_tokens, "messages": messages, "stream": True}
        if system:
            body["system"] = system
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in req.tools]
            body["tool_choice"] = {"type": "auto", "disable_parallel_tool_use": True}
        return f"{self.base_url}/v1/messages", self.headers(), body

    async def parse_stream(self, response: httpx.Response, req: TurnRequest) -> AsyncIterator[ProviderEvent]:
        tools: dict[int, dict[str, str]] = {}
        usage = {"input_tokens": 0, "output_tokens": 0}
        reason = "stop"
        seen_usage = False
        async for _, data in sse_events(response):
            try:
                event = json.loads(data)
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "message_start":
                started = (event.get("message") or {}).get("usage") or {}
                usage["input_tokens"] = int(started.get("input_tokens") or 0)
                usage["output_tokens"] = int(started.get("output_tokens") or 0)
                seen_usage = True
            elif kind == "content_block_start":
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    tools[int(event.get("index") or 0)] = {"id": block.get("id", ""), "name": block.get("name", ""), "arguments": ""}
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield ProviderEvent("text_delta", {"text": delta["text"]})
                elif delta.get("type") == "input_json_delta":
                    tool = tools.get(int(event.get("index") or 0))
                    if tool is not None:
                        tool["arguments"] += delta.get("partial_json") or ""
            elif kind == "message_delta":
                stop = (event.get("delta") or {}).get("stop_reason")
                if stop:
                    reason = FINISH_REASONS.get(stop, "stop")
                if "output_tokens" in (event.get("usage") or {}):
                    usage["output_tokens"] = int(event["usage"]["output_tokens"] or 0)
                    seen_usage = True
            elif kind == "error":
                error = event.get("error") or {}
                status = ERROR_STATUS.get(error.get("type"))
                message = redact(str(error.get("message") or "error"), self.api_key)
                yield error_event(f"{self.kind}: {message}", retriable=is_retriable_status(status))
                yield finish_event("error")
                return
        for index in sorted(tools):
            tool = tools[index]
            yield ProviderEvent(
                "tool_call",
                {"call_id": tool["id"], "name": tool["name"], "arguments": self.normalize_tool_arguments(tool["arguments"])},
            )
        if seen_usage:
            yield ProviderEvent("usage", usage)
        if tools and reason == "stop":
            reason = "tool_use"
        yield finish_event(reason)

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
