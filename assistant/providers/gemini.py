"""The client of Google's Gemini API (ASSISTANT-G36): ``POST {base}/v1beta/models/{model}:streamGenerateContent
?alt=sse``, ``GET {base}/v1beta/models`` page by page to list, the key in ``x-goog-api-key`` (never in the address).

The assistant's turns are ``model`` contents, tool results ``functionResponse`` parts of a user content (named after
the call they answer), images ``inlineData``; the instructions go in ``systemInstruction``. Gemini reads a subset of
JSON Schema, so a tool's parameters lose what it refuses (``sanitize_schema``). Gemini gives no stable id to a call:
one is made up per answer (``gemini_call_<n>``).
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

BLOCKED_KEYS = {"additionalProperties", "$defs", "definitions", "title", "$schema"}
FILTERED = ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY")
NOT_CHAT = ("embedding", "aqa", "imagen", "veo", "tts")


def sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """``schema`` with its ``$ref``s inlined and without the keys Gemini refuses."""
    definitions = schema.get("$defs") or schema.get("definitions") or {}

    def resolve(node: Any, depth: int = 0) -> Any:
        if isinstance(node, dict):
            reference = node.get("$ref")
            if isinstance(reference, str) and depth < 20:
                key = reference.removeprefix("#/$defs/").removeprefix("#/definitions/")
                if key != reference and key in definitions:
                    return resolve(definitions[key], depth + 1)
                return {k: v for k, v in node.items()}
            return {k: resolve(v, depth) for k, v in node.items() if k not in BLOCKED_KEYS}
        if isinstance(node, list):
            return [resolve(item, depth) for item in node]
        return node

    return resolve(schema)


def finish_reason(raw: str) -> str:
    raw = raw.upper()
    if raw == "MAX_TOKENS":
        return "length"
    if raw in FILTERED:
        return "content_filter"
    return "stop"


class GeminiProvider(Provider):
    kind = "gemini"

    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def to_contents(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system, rest = self.split_system_messages(messages)
        names: dict[str, str] = {}
        contents: list[dict] = []
        for message in rest:
            role = message.get("role")
            content = message.get("content", "")
            if role == "user":
                parts: list[dict] = []
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text":
                            parts.append({"text": part.get("text", "")})
                        elif part.get("type") == "image_url":
                            url = (part.get("image_url") or {}).get("url", "")
                            if url.startswith("data:") and "," in url:
                                mime_type = url.split(";")[0].split(":", 1)[1]
                                parts.append({"inlineData": {"mimeType": mime_type, "data": url.split(",", 1)[1]}})
                else:
                    parts.append({"text": content})
                contents.append({"role": "user", "parts": parts})
            elif role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content})
                for call in message.get("tool_calls") or []:
                    function = call.get("function") or {}
                    names[call.get("id", "")] = function.get("name", "")
                    try:
                        arguments = json.loads(function.get("arguments") or "{}")
                    except (TypeError, ValueError):
                        arguments = {}
                    parts.append({"functionCall": {"name": function.get("name", ""), "args": arguments}})
                contents.append({"role": "model", "parts": parts or [{"text": ""}]})
            elif role == "tool":
                name = message.get("name") or names.get(message.get("tool_call_id", ""), "")
                try:
                    response = json.loads(content) if isinstance(content, str) else content
                except ValueError:
                    response = {"result": content}
                if not isinstance(response, dict):
                    response = {"result": response}
                contents.append({"role": "user", "parts": [{"functionResponse": {"name": name, "response": response}}]})
        merged: list[dict] = []
        for item in contents:
            if merged and merged[-1]["role"] == item["role"]:
                merged[-1] = {"role": item["role"], "parts": merged[-1]["parts"] + item["parts"]}
            else:
                merged.append(item)
        return system, merged

    def chat_request(self, req: TurnRequest) -> tuple[str, dict[str, str], dict[str, Any]]:
        system, contents = self.to_contents(req.messages)
        if req.system:
            system = f"{system}\n\n{req.system}" if system else req.system
        config: dict[str, Any] = {"maxOutputTokens": req.max_tokens}
        if req.temperature is not None:
            config["temperature"] = req.temperature
        body: dict[str, Any] = {"contents": contents, "generationConfig": config}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if req.tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {"name": t.name, "description": t.description, "parameters": sanitize_schema(t.parameters)}
                        for t in req.tools
                    ]
                }
            ]
        url = f"{self.base_url}/v1beta/models/{quote(req.model_id, safe='-._')}:streamGenerateContent?alt=sse"
        return url, self.headers(), body

    async def parse_stream(self, response: httpx.Response, req: TurnRequest) -> AsyncIterator[ProviderEvent]:
        calls: list[dict[str, str]] = []
        usage: dict[str, int] = {}
        reason = "stop"
        async for _, data in sse_events(response):
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if isinstance(chunk.get("error"), dict):
                error = chunk["error"]
                status = error.get("code") if isinstance(error.get("code"), int) else None
                message = redact(str(error.get("message") or "error"), self.api_key)
                yield error_event(f"{self.kind}: {message}", retriable=is_retriable_status(status), status=status)
                yield finish_event("error")
                return
            for candidate in chunk.get("candidates") or []:
                if candidate.get("finishReason"):
                    reason = finish_reason(str(candidate["finishReason"]))
                for part in (candidate.get("content") or {}).get("parts") or []:
                    if part.get("text") and not part.get("thought"):
                        yield ProviderEvent("text_delta", {"text": part["text"]})
                    call = part.get("functionCall")
                    if call and call.get("name"):
                        calls.append(
                            {
                                "call_id": call.get("id") or f"gemini_call_{len(calls)}",
                                "name": call["name"],
                                "arguments": self.normalize_tool_arguments(call.get("args") or {}),
                            }
                        )
            metadata = chunk.get("usageMetadata")
            if metadata:
                usage = {
                    "input_tokens": int(metadata.get("promptTokenCount") or 0),
                    "output_tokens": int(metadata.get("candidatesTokenCount") or 0) + int(metadata.get("thoughtsTokenCount") or 0),
                }
        for call in calls:
            yield ProviderEvent("tool_call", call)
        if usage:
            yield ProviderEvent("usage", usage)
        if calls and reason == "stop":
            reason = "tool_use"
        yield finish_event(reason)

    async def list_models(self) -> list[DiscoveredModel]:
        found: dict[str, DiscoveredModel] = {}
        token = ""
        for _ in range(50):
            url = f"{self.base_url}/v1beta/models?pageSize=1000" + (f"&pageToken={quote(token)}" if token else "")
            page = await self.get_json(url, self.headers()) or {}
            for item in page.get("models") or []:
                model_id = str(item.get("name") or "").removeprefix("models/")
                if not model_id or "generateContent" not in (item.get("supportedGenerationMethods") or []):
                    continue
                if any(family in model_id.lower() for family in NOT_CHAT):
                    continue
                found[model_id] = DiscoveredModel(
                    model_id=model_id,
                    display_name=item.get("displayName") or model_id,
                    context_window=int(item.get("inputTokenLimit") or 0),
                )
            token = page.get("nextPageToken") or ""
            if not token:
                break
        return sorted(found.values(), key=lambda model: model.model_id)
