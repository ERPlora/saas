"""A turn through its route (ASSISTANT-G45): the models ``assistant.route.resolve`` gave, tried in order.

Each attempt first says which model answers (``model``). A provider that fails before answering anything passes the
turn to the next model (``fallback``, with the failure); once text or a tool call has come, a failure ends the turn
as it is (the person already saw the answer start). The last failure, or a route without models, ends the turn as an
``error``. Every turn ends with exactly one ``finish``, as each client's (``assistant.providers.base``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing

from assistant.providers.base import ProviderError, ProviderEvent, TurnRequest, error_event, finish_event
from assistant.providers.factory import get_provider
from assistant.schemas import RouteCandidate

#: The events that show the person the answer started: after one, there is no fallback.
ANSWERED = frozenset({"text_delta", "tool_call"})


def model_event(candidate: RouteCandidate) -> ProviderEvent:
    return ProviderEvent(
        "model",
        {
            "model": str(candidate.model),
            "model_id": candidate.model_id,
            "display_name": candidate.display_name,
            "provider": candidate.provider,
        },
    )


async def attempt(candidate: RouteCandidate, request: TurnRequest) -> AsyncIterator[ProviderEvent]:
    """The events of ``candidate``'s client for ``request``; a client that cannot be built is a failure too."""
    try:
        client = get_provider(
            kind=candidate.kind, api_key=candidate.api_key.get_secret_value(), base_url=candidate.base_url
        )
    except ProviderError as problem:
        yield error_event(problem.message, retriable=problem.retriable, status=problem.status)
        yield finish_event("error")
        return
    async with aclosing(client.stream_turn(request)) as events:
        async for event in events:
            yield event


async def stream(
    candidates: Sequence[RouteCandidate], build: Callable[[RouteCandidate], TurnRequest]
) -> AsyncIterator[ProviderEvent]:
    """The turn ``build`` makes for each of ``candidates``, in order, until one answers."""
    if not candidates:
        yield error_event("No model can answer.", retriable=False)
        yield finish_event("error")
        return
    for index, candidate in enumerate(candidates):
        following = candidates[index + 1] if index + 1 < len(candidates) else None
        yield model_event(candidate)
        answered = False
        failure: ProviderEvent | None = None
        async with aclosing(attempt(candidate, build(candidate))) as events:
            async for event in events:
                if event.type == "error" and not answered and following is not None:
                    failure = event
                    break
                answered = answered or event.type in ANSWERED
                yield event
        if failure is None:
            return
        yield ProviderEvent(
            "fallback",
            {
                "from": candidate.display_name,
                "to": following.display_name,
                "reason": failure.payload["message"],
                "status": failure.payload["status"],
            },
        )
