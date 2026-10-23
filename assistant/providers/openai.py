"""The client of OpenAI's Chat Completions API (ASSISTANT-G37), and the base of every API compatible with it
(DeepSeek, a proxy): ``POST {base}/chat/completions`` streamed, ``GET {base}/models`` to list.

One tool per answer (``parallel_tool_calls: false``) and at most ``max_tokens`` of output: the models released after
September 2024 (``o1``, ``o3``, ``o4``, ``gpt-5``…) take it as ``max_completion_tokens`` and refuse a ``temperature``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from assistant.providers.base import (
    DiscoveredModel,
    Provider,
    ProviderEvent,
    TurnRequest,
    error_event,
    finish_event,
    redact,
    sse_events,
)

#: Families of OpenAI's list that are not chat models.
NOT_CHAT = ("embedding", "whisper", "tts", "dall-e", "moderation", "davinci", "babbage", "realtime", "transcribe", "image", "audio", "sora", "search")
FINISH_REASONS = {"stop": "stop", "tool_calls": "tool_use", "function_call": "tool_use", "length": "length", "content_filter": "content_filter"}
NEWER_MODELS = ("o1", "o3", "o4", "gpt-5")


class OpenAIProvider(Provider):
    kind = "openai"
    #: Whether the API takes ``parallel_tool_calls``.
    parallel_tool_calls_flag = True

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    @staticmethod
    def is_newer(model_id: str) -> bool:
        return model_id.lower().startswith(NEWER_MODELS)

    def chat_request(self, req: TurnRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        messages: list[dict] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend(req.messages)
        body: dict[str, Any] = {
            "model": req.model_id,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if self.is_newer(req.model_id):
            body["max_completion_tokens"] = req.max_tokens
        else:
            body["max_tokens"] = req.max_tokens
            if req.temperature is not None:
                body["temperature"] = req.temperature
        if req.tools:
            body["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in req.tools
            ]
            if self.parallel_tool_calls_flag:
                body["parallel_tool_calls"] = False
        return f"{self.base_url}/chat/completions", self.headers(), body

    async def parse_stream(self, response: httpx.Response, req: TurnRequest) -> AsyncIterator[ProviderEvent]:
        fragments: dict[int, dict[str, str]] = {}
        usage: dict[str, int] = {}
        reason = "stop"
        async for _, data in sse_events(response):
            if data.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if isinstance(chunk.get("error"), dict):
                message = redact(str(chunk["error"].get("message") or "error"), self.api_key)
                yield error_event(f"{self.kind}: {message}", retriable=True)
                yield finish_event("error")
                return
            if chunk.get("usage"):
                usage = {
                    "input_tokens": int(chunk["usage"].get("prompt_tokens") or 0),
                    "output_tokens": int(chunk["usage"].get("completion_tokens") or 0),
                }
            for choice in chunk.get("choices") or []:
                if choice.get("finish_reason"):
                    reason = FINISH_REASONS.get(choice["finish_reason"], "stop")
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    yield ProviderEvent("text_delta", {"text": delta["content"]})
                for piece in delta.get("tool_calls") or []:
                    fragment = fragments.setdefault(int(piece.get("index") or 0), {"id": "", "name": "", "arguments": ""})
                    fragment["id"] += piece.get("id") or ""
                    function = piece.get("function") or {}
                    fragment["name"] += function.get("name") or ""
                    fragment["arguments"] += function.get("arguments") or ""
        for index in sorted(fragments):
            fragment = fragments[index]
            yield ProviderEvent(
                "tool_call",
                {"call_id": fragment["id"], "name": fragment["name"], "arguments": self.normalize_tool_arguments(fragment["arguments"])},
            )
        if usage:
            yield ProviderEvent("usage", usage)
        if fragments and reason == "stop":
            reason = "tool_use"
        yield finish_event(reason)

    def is_chat_model(self, model_id: str) -> bool:
        lowered = model_id.lower()
        return not any(family in lowered for family in NOT_CHAT)

    async def list_models(self) -> list[DiscoveredModel]:
        listed = await self.get_json(f"{self.base_url}/models", self.headers())
        ids = sorted({str(item.get("id")) for item in (listed or {}).get("data") or [] if item.get("id")})
        return [DiscoveredModel(model_id=model_id, display_name=model_id) for model_id in ids if self.is_chat_model(model_id)]
