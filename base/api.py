"""Ninja routes of base: each route calls exactly one operation and holds no logic."""

from live.ninja import bind, run_operation
from ninja import Router

from base import queries

router = Router(tags=["base"])


# auth=None: an anonymous visitor gets ``user: null`` (and the SPA sends it to the login).
@bind(router, "base.session.me", "/me", auth=None)
async def session_me(request):
    return await run_operation(request, queries.session_me)


# --- The panel's assistant (PLAN-SAAS §23): the Hub's paths and operations ----------------------------------------

from ninja.decorators import decorate_view  # noqa: E402 - the assistant's block keeps its imports with it

from assistant.internal import TURN_BODY_BYTES  # noqa: E402
from base import assistant, services  # noqa: E402
from base.request_body import accept_body_up_to  # noqa: E402
from base.schemas import AssistantReportIn, AssistantTurnIn  # noqa: E402


# The 200 is a stream (text/event-stream) of the turn's frames (``base.assistant.turn_frames``), not the JSON of its
# operation's output, which is what the stream is made of. Its body (the conversation and the attachments of its last
# question, in base64) may weigh as much as the gateway takes, and stays in memory (``config.asgi.IN_MEMORY_PATHS``).
@bind(router, "base.assistant.turn", "/assistant/turn")
@decorate_view(accept_body_up_to(TURN_BODY_BYTES))
async def assistant_turn(request, data: AssistantTurnIn):
    # The network wait of its tools (a documentation search's fingerprint) goes before the operation's transaction.
    await assistant.prepare(data)
    plan = await run_operation(request, services.assistant_turn, data)
    return assistant.turn_response(request, plan.model_dump(mode="json"))


@bind(router, "base.assistant.usage", "/assistant/usage")
async def assistant_usage(request):
    return await run_operation(request, queries.assistant_usage)


@bind(router, "base.assistant.report", "/assistant/report")
async def assistant_report(request, data: AssistantReportIn):
    return await run_operation(request, services.assistant_report, data)
