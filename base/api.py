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

from assistant.internal import TRANSCRIBE_BODY_BYTES, TURN_BODY_BYTES  # noqa: E402
from base import assistant, services  # noqa: E402
from base.request_body import accept_body_up_to  # noqa: E402
from base.schemas import AssistantReportIn, AssistantSpeakIn, AssistantTranscribeIn, AssistantTurnIn  # noqa: E402


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


# Its body (the audio, in base64) stays in memory (``config.asgi.IN_MEMORY_PATHS``): a dictation never touches the disk.
@bind(router, "base.assistant.transcribe", "/assistant/transcribe")
@decorate_view(accept_body_up_to(TRANSCRIBE_BODY_BYTES))
async def assistant_transcribe(request, data: AssistantTranscribeIn):
    # The operation is the door; the wait on the provider goes after it, with no transaction open, as the turn's.
    ready = await run_operation(request, services.assistant_transcribe, data)
    return await assistant.transcribed(request, data, ready.language)


#: The 200 of a reading aloud: the mp3 itself, keyed by the int ``200`` as ninja keys its own (one response in the
#: OpenAPI, not two).
AUDIO_RESPONSE = {"responses": {200: {"content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}}}}


@bind(router, "base.assistant.speak", "/assistant/speak", openapi_extra=AUDIO_RESPONSE)
async def assistant_speak(request, data: AssistantSpeakIn):
    # The operation is the door; the wait on the engine goes after it, with no transaction open, as the dictation's.
    ready = await run_operation(request, services.assistant_speak, data)
    return await assistant.spoken(request, data, ready.language)
