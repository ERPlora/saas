"""The client of Google's Gemini API: ``POST {base}/v1beta/models/{model}:streamGenerateContent
?alt=sse``, ``GET {base}/v1beta/models`` page by page to list, the key in ``x-goog-api-key`` (never in the address).

The assistant's turns are ``model`` contents, tool results ``functionResponse`` parts of a user content (named after
the call they answer), images and PDFs ``inlineData``; the instructions go in ``systemInstruction``. Gemini reads a
subset of JSON Schema, so a tool's parameters lose what it refuses (``sanitize_schema``). Gemini gives no stable id to
a call: one is made up per answer (``gemini_call_<n>``).
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
    closing_events,
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


def merge_turns(contents: list[dict]) -> list[dict]:
    """One content per turn: consecutive contents of one role become one with all their parts."""
    merged: list[dict] = []
    for item in contents:
        if merged and merged[-1]["role"] == item["role"]:
            merged[-1] = {"role": item["role"], "parts": merged[-1]["parts"] + item["parts"]}
        else:
            merged.append(item)
    return merged


def response_of(content: Any) -> dict:
    """A tool's result as the object of a ``functionResponse``: its JSON if that is an object, else ``{"result": …}``."""
    try:
        response = json.loads(content) if isinstance(content, str) else content
    except ValueError:
        response = {"result": content}
    return response if isinstance(response, dict) else {"result": response}


def chat_model(item: dict) -> DiscoveredModel | None:
    """A model of Gemini's list, if it generates content and is of no family that does not chat (``NOT_CHAT``)."""
    model_id = str(item.get("name") or "").removeprefix("models/")
    if not model_id or "generateContent" not in (item.get("supportedGenerationMethods") or []):
        return None
    if any(family in model_id.lower() for family in NOT_CHAT):
        return None
    return DiscoveredModel(
        model_id=model_id,
        display_name=item.get("displayName") or model_id,
        context_window=int(item.get("inputTokenLimit") or 0),
    )


class Answer:
    """What a streamed answer said so far: the tools it asked for, its counts and why it stopped."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.usage: dict[str, int] = {}
        self.reason = "stop"

    def read(self, chunk: dict) -> list[str]:
        """Take ``chunk`` in; the pieces of text it adds to the answer."""
        texts = []
        for candidate in chunk.get("candidates") or []:
            if candidate.get("finishReason"):
                self.reason = finish_reason(str(candidate["finishReason"]))
            for part in (candidate.get("content") or {}).get("parts") or []:
                if text := self.take(part):
                    texts.append(text)
        self.count(chunk.get("usageMetadata"))
        return texts

    def take(self, part: dict) -> str:
        """The text of ``part``, none for a thought; the tool call it carries is kept for the end."""
        call = part.get("functionCall")
        if call and call.get("name"):
            self.calls.append(
                {
                    "call_id": call.get("id") or f"gemini_call_{len(self.calls)}",
                    "name": call["name"],
                    "arguments": Provider.normalize_tool_arguments(call.get("args") or {}),
                }
            )
        return "" if part.get("thought") else part.get("text") or ""

    def count(self, metadata: dict | None) -> None:
        """Gemini's counts so far: a later one replaces the earlier, and the output includes its thoughts."""
        if metadata:
            self.usage = {
                "input_tokens": int(metadata.get("promptTokenCount") or 0),
                "output_tokens": int(metadata.get("candidatesTokenCount") or 0) + int(metadata.get("thoughtsTokenCount") or 0),
            }


class GeminiProvider(Provider):
    kind = "gemini"

    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def user_part(self, part: dict) -> dict | None:
        """A part of a person's message as Gemini's part: its text, an image or a PDF; ``None`` for any other."""
        if part.get("type") == "text":
            return {"text": part.get("text", "")}
        inline = self.inline_data(part)
        return None if inline is None else {"inlineData": {"mimeType": inline[0], "data": inline[1]}}

    def to_contents(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system, rest = self.split_system_messages(messages)
        names: dict[str, str] = {}
        contents: list[dict] = []
        for message in rest:
            role = message.get("role")
            if role == "user":
                contents.append(self.user_content(message.get("content", "")))
            elif role == "assistant":
                contents.append(self.model_content(message, names))
            elif role == "tool":
                contents.append(self.tool_content(message, names))
        return system, merge_turns(contents)

    def user_content(self, content: str | list) -> dict:
        if isinstance(content, list):
            return {"role": "user", "parts": [piece for piece in map(self.user_part, content) if piece is not None]}
        return {"role": "user", "parts": [{"text": content}]}

    def model_content(self, message: dict, names: dict[str, str]) -> dict:
        """What the assistant said and the tools it called; ``names`` learns the tool of each call."""
        parts: list[dict] = [{"text": message["content"]}] if message.get("content") else []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            names[call.get("id", "")] = function.get("name", "")
            parts.append({"functionCall": {"name": function.get("name", ""), "args": self.loaded_arguments(function)}})
        return {"role": "model", "parts": parts or [{"text": ""}]}

    @staticmethod
    def tool_content(message: dict, names: dict[str, str]) -> dict:
        """A tool's result, named after the tool of the call it answers."""
        name = message.get("name") or names.get(message.get("tool_call_id", ""), "")
        response = response_of(message.get("content", ""))
        return {"role": "user", "parts": [{"functionResponse": {"name": name, "response": response}}]}

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
        answer = Answer()
        async for _, data in sse_events(response):
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            if isinstance(chunk.get("error"), dict):
                yield self.stream_error(chunk["error"])
                yield finish_event("error")
                return
            for text in answer.read(chunk):
                yield ProviderEvent("text_delta", {"text": text})
        for event in closing_events(answer.calls, answer.usage, answer.reason):
            yield event

    def stream_error(self, error: dict) -> ProviderEvent:
        """The ``error`` event of a failure the stream announced, with its status when it gives one."""
        status = error.get("code") if isinstance(error.get("code"), int) else None
        message = redact(str(error.get("message") or "error"), self.api_key)
        return error_event(f"{self.kind}: {message}", retriable=is_retriable_status(status), status=status)

    async def list_models(self) -> list[DiscoveredModel]:
        found: dict[str, DiscoveredModel] = {}
        token = ""
        for _ in range(50):
            url = f"{self.base_url}/v1beta/models?pageSize=1000" + (f"&pageToken={quote(token)}" if token else "")
            page = await self.get_json(url, self.headers()) or {}
            for model in filter(None, map(chat_model, page.get("models") or [])):
                found[model.model_id] = model
            token = page.get("nextPageToken") or ""
            if not token:
                break
        return sorted(found.values(), key=lambda model: model.model_id)
