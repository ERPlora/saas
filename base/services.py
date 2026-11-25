"""Write operations of base: the turn and the report of the panel's own assistant, with the Hub's names
(``base.assistant.turn``, ``base.assistant.report``) so the shared panel of ``@erplora/ui`` is configured the same in
both.

Neither touches the ORM here: the tools run as the account, each by its own operation; the report and the allowance
are the gateway's (``assistant.services``), called as the platform for the session's account.
"""

import json
import logging

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import OperationError, Unauthorized
from live.operations import INTERNAL, operation

from assistant import media as gateway_media
from assistant import services as gateway_services
from assistant import turn as gateway
from assistant.schemas import Caller, ReportSendIn
from base import assistant
from base.schemas import (
    AssistantReportIn,
    AssistantReportOut,
    AssistantSpeakIn,
    AssistantSpeakOut,
    AssistantTranscribeIn,
    AssistantTranscribeOut,
    AssistantTurnIn,
    AssistantTurnOut,
)

logger = logging.getLogger(__name__)

#: Every account asks the panel's assistant (``assistant.apps``: the role ``account``).
ASK = "assistant.ask"

#: What the model hears of a tool that did not run (in English, as its instructions).
#: The person said no to a card: what the model hears, and what stops it asking again (saas#193).
NOT_CONFIRMED_CODE = "base.assistant_not_confirmed"
NOT_CONFIRMED = (
    "The person said no on the card and the card is closed: nothing was done. Say it was not done, and do not tell them "
    "to confirm it."
)
ASKED_AGAIN = (
    "The person already said no to this and has not written since: nothing was done. Do not ask again: say it was not "
    "done, and they will write if they want something else."
)
NOT_AVAILABLE = "This tool is not available to this person here: nothing was done."
NOT_FROM_THE_CHAT = "This cannot be done from the chat (it names no record): nothing was done. Say where it is done."


def _words(content) -> str:
    """The words of a person's message, to choose its tools: a message that brings files comes as a list of parts,
    and only its text parts are words."""
    if isinstance(content, str):
        return content
    parts = content if isinstance(content, list) else []
    texts = (part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text")
    return "\n".join(str(text) for text in texts)


def _asked(messages: list[dict]) -> list[str]:
    """What the person wrote, message by message. A file alone says nothing: the words written before it still count."""
    said = (_words(m.get("content")) for m in messages if m.get("role") == "user")
    return [words for words in said if words]


def _ran(ctx: OperationContext, tools: dict, call, outcome: assistant.ToolOutcome) -> dict:
    """What ran, or was refused, by its name: a write this account was not offered is named too."""
    op = assistant.shared.operation_of(call.name, tools) or assistant.shared.named(call.name)
    if op is None:
        named = {"name": call.name, "app": "", "app_name": "", "screen": "", "kind": ""}
    else:
        with translation.override(ctx.language):
            screen = assistant.screen(op)
            app_name = assistant.screen_name(screen)
        named = {"name": op.name, "app": op.app_label, "app_name": app_name, "screen": screen, "kind": op.kind}
    return {"call_id": call.call_id, **named, "outcome": outcome.outcome, "code": outcome.code}


def _calls_in(message: dict) -> dict[str, str]:
    """The calls of a model's ``message``, id → tool's name; what the browser kept in another shape is none."""
    calls = message.get("tool_calls")
    named = {}
    for call in calls if isinstance(calls, list) else []:
        function = call.get("function") if isinstance(call, dict) else None
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            named[str(call.get("id"))] = function["name"]
    return named


def _declined_before(messages: list[dict], call_id: str) -> set[str]:
    """The tools the person said no to since they last wrote, in a round before ``call_id``'s: a no stands until they
    write again, whatever the model decides (saas#193). A call of ``call_id``'s own round is another question, which
    nobody has answered yet."""
    noes: set[str] = set()
    declined: set[str] = set()
    for message in reversed(messages):
        role = message.get("role")
        if role == "user":
            break
        if role == "tool" and NOT_CONFIRMED_CODE in str(message.get("content")):
            noes.add(str(message.get("tool_call_id")))
        elif role == "assistant":
            named = _calls_in(message)
            if call_id not in named:
                declined.update(name for called, name in named.items() if called in noes)
    return declined


def _declined(card: dict, decision) -> assistant.ToolOutcome | None:
    """What the person's ``decision`` on ``card`` leaves undone, or ``None`` when it is a yes to run. A no is told in
    the panel's own words (``live.assistant.declined`` tells it in the Hub's)."""
    if card["blocked"]:
        return assistant.shared.refusal("cancelled", "base.assistant_not_from_chat", NOT_FROM_THE_CHAT)
    if decision.stop:
        return assistant.shared.stopped()
    if not decision.accepted or not assistant.shared.confirmed(card, decision.typed):
        return assistant.shared.refusal("cancelled", NOT_CONFIRMED_CODE, NOT_CONFIRMED)
    return None


def _waiting(ctx: OperationContext, op, arguments: dict, card: dict):
    """``(outcome, card)`` of a write nobody has answered: its card, with what it will do; one whose preview cannot be
    read gets no card and tells the model why."""
    if card["blocked"]:
        return None, card
    failure, preview = assistant.shared.preview(ctx, op, arguments)
    if failure is not None:
        return failure, None
    return None, {**card, "preview": preview}


def _answer_write(ctx: OperationContext, op, call, arguments: dict, decision):
    """``(outcome, card)`` of the write ``call``, which runs only with the person's yes to its card. No card for data
    the write would refuse: the model hears which (``invalid_payload``) and asks again with them corrected, in the same
    turn."""
    refused = assistant.shared.invalid_arguments(op, arguments)
    if refused is not None:
        return refused, None
    card = assistant.card(op, arguments, ctx)
    if decision is None or decision.call_id != call.call_id:
        return _waiting(ctx, op, arguments, card)
    declined = _declined(card, decision)
    if declined is not None:
        return declined, None
    return assistant.shared.run_tool(ctx, op, call.arguments), None


def _answer(ctx: OperationContext, tools: dict, call, decision, *, stopped: bool):
    """Run one pending ``call`` (a read alone; a write with the person's yes, ``_answer_write``) → ``(outcome, card)``:
    the card when the write still waits for its answer."""
    op = assistant.shared.operation_of(call.name, tools)
    if op is None:
        return assistant.shared.refusal("refused", "not_available", NOT_AVAILABLE), None
    if stopped:
        return assistant.shared.stopped(), None
    try:
        arguments = None if op.kind == "query" else json.loads(call.arguments or "{}")
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        return assistant.shared.run_tool(ctx, op, call.arguments), None
    return _answer_write(ctx, op, call, arguments, decision)


@operation(
    "base.assistant.turn",
    kind="command",
    permission=ASK,
    input=AssistantTurnIn,
    output=AssistantTurnOut,
    ai=INTERNAL,  # panel
    # Not ``database=False``: the tools it runs are operations of their own that read and write (live refuses any SQL
    # inside an operation without a database). The model answers after it, in the stream (``turn_response``), with no
    # transaction open.
)
def assistant_turn(ctx: OperationContext, data: AssistantTurnIn) -> dict:
    """A turn of the panel's assistant made ready: the reads the model asked for run as the account; a write shows its
    card and runs only with the person's yes (``decision``; «Cancel all» = ``stop``); a tool this account was not
    offered never runs. Then what goes to the gateway: the tools of what was asked, by relevance, and the
    instructions. Past ``MAX_ROUNDS`` rounds of tools it goes no further (``stop``). The route streams it
    (``base.assistant.turn_response``)."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to talk to the assistant."))
    tools = assistant.catalog(ctx)
    pending = list(data.pending)
    decision = data.decision
    stopped = False
    append: list[dict] = []
    executed: list[dict] = []
    card = None
    while pending:
        call = pending[0]
        if call.name in _declined_before(data.messages, call.call_id):
            # No card and no receipt: the person answered once, and only the model asks again.
            content = assistant.shared.error_content(NOT_CONFIRMED_CODE, ASKED_AGAIN)
            append.append({"role": "tool", "tool_call_id": call.call_id, "content": content})
            pending.pop(0)
            continue
        outcome, card = _answer(ctx, tools, call, decision, stopped=stopped)
        if outcome is None:
            break
        if decision is not None and decision.call_id == call.call_id:
            stopped = decision.stop
            decision = None
        append.append({"role": "tool", "tool_call_id": call.call_id, "content": outcome.content})
        executed.append(_ran(ctx, tools, call, outcome))
        pending.pop(0)
    messages = [*data.messages, *append]
    asked = _asked(data.messages)
    if card is not None:
        card["money"] = {"currency": "EUR", "decimals": 2}
    text = assistant.instructions(
        language=ctx.language,
        account=assistant.account_label(ctx.actor),
        screens=assistant.screens(ctx),
        docs="assistant.docs.search" in tools,
        sells=not assistant.sells_nothing(getattr(ctx, "request", None)),
    )
    stop = ""
    if card is None and not stopped and assistant.shared.rounds(messages) >= assistant.MAX_ROUNDS:
        stop = "assistant.too_many_steps"
    return {
        "messages": messages,
        "append": append,
        "executed": executed,
        "confirm": card,
        "pending": [p.model_dump() for p in pending],
        "tools": [assistant.tool_spec(op) for op in assistant.relevant(tools, asked[-2:], ctx.language)],
        "instructions": text,
        "continuation": data.continuation,
        "stop": stop,
    }


@operation(
    "base.assistant.report",
    kind="command",
    permission=ASK,
    input=AssistantReportIn,
    output=AssistantReportOut,
    ai=INTERNAL,  # panel
)
def assistant_report(ctx: OperationContext, data: AssistantReportIn) -> dict:
    """Send ERPlora's team an answer of the panel's assistant the account reports, with the question that led to it
    (``assistant.report.send``: the same answer within a day mails nothing again), within the account's budget of
    the Hub's ``report`` door (``ASSISTANT_REPORT_RATELIMIT``; past it, 429 ``rate_limited`` and nothing is mailed).
    503 ``base.assistant_report_not_sent`` when the mail cannot leave."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to talk to the assistant."))
    caller = Caller(user_id=ctx.actor.pk)
    try:
        # The budget of the Hub's ``report`` door, per account: a new ``message_id`` each time never floods support.
        gateway.spend(getattr(ctx, "request", None), "report", settings.ASSISTANT_REPORT_RATELIMIT, caller)
    except gateway.Refused:
        with translation.override(ctx.language):
            raise OperationError(
                gettext("Too many reports in a short time: wait a moment and try again."),
                code="rate_limited",
                status=429,
            ) from None
    report = ReportSendIn(caller=caller, **data.model_dump())
    try:
        sent = gateway_services.answer_reports.report_send(gateway_services.platform_actor.platform_context(), report)
    except OperationError as failed:
        if failed.code != "assistant.report_not_sent":
            raise
        with translation.override(ctx.language):
            raise OperationError(
                gettext("The report could not be sent: try again in a moment."),
                code="base.assistant_report_not_sent",
                status=503,
            ) from None
    return sent.model_dump()


@operation(
    "base.assistant.transcribe",
    kind="command",
    permission=ASK,
    input=AssistantTranscribeIn,
    output=AssistantTranscribeOut,
    ai=INTERNAL,  # panel
    # The door, with no transaction open: the route waits on the provider after it (``assistant.transcribed``), and a
    # connection never waits on the provider inside a transaction.
    database=False,
)
def assistant_transcribe(ctx: OperationContext, data: AssistantTranscribeIn) -> dict:
    """A dictation of the panel made ready, as a turn is: the session's account, its permission, its budget of the Hub's
    ``transcribe`` door (``ASSISTANT_TRANSCRIBE_RATELIMIT``, 429 ``rate_limited``) and the language it goes in (as asked,
    else the account's). The words come from the route (``base.assistant.transcribed``), to the box and never sent by
    themselves; nothing else is ever written of them."""
    try:
        gateway.spend(getattr(ctx, "request", None), "transcribe", settings.ASSISTANT_TRANSCRIBE_RATELIMIT, Caller(user_id=ctx.actor.pk))
    except gateway.Refused:
        with translation.override(ctx.language):
            raise OperationError(
                gettext("Too many dictations in a short time: wait a moment and try again."),
                code="rate_limited",
                status=429,
            ) from None
    return {"text": "", "language": gateway_media.base_language(data.language or ctx.language)}


@operation(
    "base.assistant.speak",
    kind="command",
    permission=ASK,
    input=AssistantSpeakIn,
    output=AssistantSpeakOut,
    ai=INTERNAL,  # panel
    # The door, with no transaction open: the route waits on the engine after it (``assistant.spoken``), and a connection
    # never waits on it inside a transaction.
    database=False,
)
def assistant_speak(ctx: OperationContext, data: AssistantSpeakIn) -> dict:
    """A reading aloud of the panel made ready, as a dictation is: the session's account, its permission, its budget
    of the Hub's ``synthesize`` door (``ASSISTANT_SYNTHESIZE_RATELIMIT``, 429 ``rate_limited``) and the language it is
    read in (as asked, else the account's; English for a language without voices). The audio comes from the route
    (``base.assistant.spoken``); nothing is written of what is read."""
    try:
        gateway.spend(getattr(ctx, "request", None), "synthesize", settings.ASSISTANT_SYNTHESIZE_RATELIMIT, Caller(user_id=ctx.actor.pk))
    except gateway.Refused:
        with translation.override(ctx.language):
            raise OperationError(
                gettext("Too many readings aloud in a short time: wait a moment and try again."),
                code="rate_limited",
                status=429,
            ) from None
    language = data.language or gateway_media.base_language(ctx.language)
    return {"language": language if language in gateway_media.SPEECH_LANGUAGES else "en"}
