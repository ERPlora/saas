"""«Try a model»: one message to one model, its answer streamed to the page as server-sent events with its
tokens, time and cost (``assistant.route.resolve`` with the model, then ``assistant.routing.stream``). The run is an
asynchronous view (the provider's call never holds a thread), for the staff who may change the model that
answers, at most ``ASSISTANT_TRY_RATELIMIT`` per person; each one is recorded with ``assistant.model.try``."""

import json
import time
import uuid

from django.conf import settings
from django.http import StreamingHttpResponse
from django.utils.translation import gettext as _
from django_ratelimit.core import is_ratelimited
from live.context import OperationContext
from live.errors import OperationError

from assistant import queries, routing, services, usage_cost
from assistant.providers.base import ToolSpec, TurnRequest
from assistant.schemas import ModelTryIn, RouteCandidate, RouteIn
from assistant.usage_cost import Tokens

#: What trying a model needs: the permission that chooses which model answers (a try spends ERPlora's key).
TRY_PERMISSIONS = ("assistant.change_airoutingpolicy",)
#: The longest message a try sends.
TRY_PROMPT_MAX = 4000


def sse(kind: str, payload: dict | None = None) -> bytes:
    """One server-sent event of a try: ``data: {"type": kind, ...payload}``."""
    return f"data: {json.dumps({'type': kind, **(payload or {})}, ensure_ascii=False)}\n\n".encode()


def event_stream(chunks) -> StreamingHttpResponse:
    response = StreamingHttpResponse(chunks, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


async def refused_try(message: str):
    yield sse("error", {"message": message})
    yield sse("done")


def parse_tools(raw: str) -> list[ToolSpec] | None:
    """The tools typed (a JSON list of ``{"name", "description", "parameters"}``, or OpenAI's ``{"function": …}``);
    ``[]`` for none, ``None`` when it is not a list of named tools."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    tools = []
    for item in data:
        spec = item.get("function", item) if isinstance(item, dict) else None
        name = spec.get("name") if isinstance(spec, dict) else None
        if not isinstance(name, str) or not name.strip():
            return None
        parameters = spec.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(parameters, dict):
            return None
        tools.append(ToolSpec(name=name.strip(), description=str(spec.get("description") or ""), parameters=parameters))
    return tools


def too_many_tries(request) -> bool:
    """Count this try of the member of the staff; whether it went past ``ASSISTANT_TRY_RATELIMIT``."""
    return is_ratelimited(
        request,
        group="assistant.try_model",
        key=lambda group, request: f"user:{request.user.pk}",
        rate=settings.ASSISTANT_TRY_RATELIMIT,
        increment=True,
    )


def prepare_try(request, ctx: OperationContext) -> tuple[RouteCandidate, TurnRequest] | str:
    """The model and the turn of a try, recorded; or the message that refuses it (in the staff's language)."""
    try:
        model = uuid.UUID(request.POST.get("model") or "")
    except ValueError:
        return _("Choose the model to try from the list.")
    prompt = (request.POST.get("prompt") or "").strip()[:TRY_PROMPT_MAX]
    if not prompt:
        return _("Write the message to send.")
    tools = parse_tools(request.POST.get("tools", ""))
    if tools is None:
        return _("The tools are not well written: write a list of tools as in the example, each with its name.")
    try:
        [candidate] = queries.routing_policy.route_resolve(ctx, RouteIn(model=model)).candidates
        services.model_choice.model_try(ctx, ModelTryIn(model=model, prompt_chars=len(prompt), tools=len(tools)))
    except OperationError as refused:
        return refused.message
    return candidate, TurnRequest(model_id=candidate.model_id, messages=[{"role": "user", "content": prompt}], tools=tools)


async def try_events(candidate: RouteCandidate, turn: TurnRequest):
    """The events of the model's answer, then its ``metrics`` (tokens, milliseconds and USD) and ``done``."""
    started = time.monotonic()
    tokens = Tokens()
    async for event in routing.stream([candidate], lambda _candidate: turn):
        if event.type == "usage":
            tokens = Tokens.of(event.payload)
        yield sse(event.type, event.payload)
    cost = usage_cost.cost(candidate, tokens)
    latency_ms = int((time.monotonic() - started) * 1000)
    metrics = {"input_tokens": tokens.input, "output_tokens": tokens.output, "cost_usd": format(cost.normalize(), "f")}
    yield sse("metrics", {"latency_ms": latency_ms, **metrics})
    yield sse("done")
