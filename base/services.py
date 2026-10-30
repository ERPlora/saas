"""Write operations of base: the turn and the report of the panel's own assistant (plan 2026-10-30-asistente-saas
§4, PLAN-SAAS §23), with the Hub's names (``base.assistant.turn``, ``base.assistant.report``) so the shared panel of
``@erplora/ui`` is configured the same in both.

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

from assistant import services as gateway_services
from assistant import turn as gateway
from assistant.schemas import Caller, ReportSendIn
from base import assistant
from base.schemas import (
    AssistantReportIn,
    AssistantReportOut,
    AssistantTurnIn,
    AssistantTurnOut,
)

logger = logging.getLogger(__name__)

#: Every account asks the panel's assistant (``assistant.apps``: the role ``account``).
ASK = "assistant.ask"

#: What the model hears of a tool that did not run (in English, as its instructions).
NOT_CONFIRMED = "Not confirmed by the person: nothing was done."
STOPPED = "The person stopped this request: nothing more was done."
NOT_AVAILABLE = "This tool is not available to this person here: nothing was done."
NOT_FROM_THE_CHAT = "This cannot be done from the chat (it names no record): nothing was done. Say where it is done."


def _refused(outcome: str, code: str, message: str) -> assistant.ToolOutcome:
    """A tool that did not run, told to the model in the same envelope as an operation's error."""
    return assistant.ToolOutcome(outcome, code, assistant.shared.error_content(code, message))


def _answer(ctx: OperationContext, tools: dict, call, decision, *, stopped: bool):
    """Run one pending ``call`` (a read alone; a write with the person's yes) → ``(outcome, card)``: the card when the
    write still waits for its answer."""
    op = assistant.shared.operation_of(call.name, tools)
    if op is None:
        return _refused("refused", "not_available", NOT_AVAILABLE), None
    if stopped:
        return _refused("cancelled", "base.assistant_stopped", STOPPED), None
    if op.kind == "query":
        return assistant.shared.run_tool(ctx, op, call.arguments), None
    try:
        arguments = json.loads(call.arguments or "{}")
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        return assistant.shared.run_tool(ctx, op, call.arguments), None
    card = assistant.card(op, arguments, ctx)
    if decision is None or decision.call_id != call.call_id:
        if card["blocked"]:
            return None, card
        failure, preview = assistant.shared.preview(ctx, op, arguments)
        if failure is not None:
            return failure, None
        return None, {**card, "preview": preview}
    if card["blocked"]:
        return _refused("cancelled", "base.assistant_not_from_chat", NOT_FROM_THE_CHAT), None
    if decision.stop:
        return _refused("cancelled", "base.assistant_stopped", STOPPED), None
    if not decision.accepted or not assistant.shared.confirmed(card, decision.typed):
        return _refused("cancelled", "base.assistant_not_confirmed", NOT_CONFIRMED), None
    return assistant.shared.run_tool(ctx, op, call.arguments), None


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
        outcome, card = _answer(ctx, tools, call, decision, stopped=stopped)
        if outcome is None:
            break
        if decision is not None and decision.call_id == call.call_id:
            stopped = decision.stop
            decision = None
        # What ran, or was refused, by its name: a write this account was not offered is named too.
        op = assistant.shared.operation_of(call.name, tools) or assistant.shared.named(call.name)
        append.append({"role": "tool", "tool_call_id": call.call_id, "content": outcome.content})
        with translation.override(ctx.language):
            screen = assistant.screen(op) if op else ""
            app_name = assistant.screen_name(screen) if op else ""
        executed.append(
            {
                "call_id": call.call_id,
                "name": op.name if op else call.name,
                "app": op.app_label if op else "",
                "app_name": app_name,
                "screen": screen,
                "kind": op.kind if op else "",
                "outcome": outcome.outcome,
                "code": outcome.code,
            }
        )
        pending.pop(0)
    messages = [*data.messages, *append]
    asked = [
        str(m.get("content")) for m in data.messages if m.get("role") == "user" and isinstance(m.get("content"), str)
    ]
    if card is not None:
        card["money"] = {"currency": "EUR", "decimals": 2}
    text = assistant.instructions(
        language=ctx.language,
        account=assistant.account_label(ctx.actor),
        screens=assistant.screens(ctx),
        docs="assistant.docs.search" in tools,
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
        sent = gateway_services.report_send(gateway_services.platform_context(), report)
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
