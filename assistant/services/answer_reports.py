"""The report of an answer.

- ``assistant.report.send``: the report of an answer, mailed to the support mailbox; nothing kept.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from assistant import events, queries, server_tools
from assistant.schemas import ReportOut, ReportSendIn
from assistant.services.turn_usage import _caller_payload
from hubs.models import Hub

logger = logging.getLogger("assistant.services")


#: The characters of each text a report mails (the question, the answer, the comment).
REPORT_TEXT_MAX = 4000
#: A report of the same answer within this time mails nothing again (a double tap, a retry of the Hub).
REPORT_ONCE_SECONDS = 24 * 60 * 60
#: What a report mails instead of an answer that may quote pages of the web (saas#287): section 3(b)(i) of Brave
#: Search's terms forbids keeping its results, in whole or in part, and a mailbox keeps; their addresses and titles are
#: part of them too.
REPORT_WEB_ANSWER = (
    "Left out: it may quote web search results, which Brave Search's terms (§3(b)(i)) do not let us keep. "
    "Ask the question again to see it."
)


@operation(
    "assistant.report.send",
    kind="command",
    permission="assistant.manage",
    input=ReportSendIn,
    output=ReportOut,
    ai=INTERNAL,  # platform
)
def report_send(ctx: OperationContext, data: ReportSendIn) -> dict:
    """Mail the report of an answer to the support mailbox (the platform only), in English (the team's mail), with
    the business (the demo, or the account of the panel's own assistant), the reason, the comment, the question and
    the answer, each cut to ``REPORT_TEXT_MAX``; nothing is kept nor logged. An answer whose turn brought pages from the
    web (``web``), or that does not say while the search is offered, is not mailed (``REPORT_WEB_ANSWER`` instead).
    The same answer (``message_id``) of the same business within a day is a ``duplicate``. A business
    that stopped working since the door resolved it gets the door's answer (404 ``hub_unknown``, 403 ``hub_inactive``)
    and nothing is mailed. 503 ``assistant.report_not_sent`` if the mail cannot leave. The event is written before the
    mail, so nothing that can undo the transaction comes after it: a mail that cannot leave undoes the event, and an
    event that cannot be written sends nothing. Whatever fails, the report can be sent again."""
    from django.core.cache import cache

    queries.platform_only(ctx)
    caller = data.caller
    if caller.demo:
        who, details = caller.demo, [("Demo", caller.demo)]
    elif caller.user_id is not None:
        email = get_user_model().objects.filter(pk=caller.user_id).values_list("email", flat=True).first()
        if email is None:
            raise NotFound(_("The account no longer exists."), code="assistant.account_unknown")
        who, details = email, [("Account", email)]
    else:
        hub = queries.working(Hub.objects.filter(pk=caller.hub_id).first())
        who, details = hub.name, [("Business", f"{hub.name} ({hub.slug}, {hub.id})")]
    key = f"demo:{caller.demo}" if caller.demo else f"user:{caller.user_id}" if caller.user_id else caller.hub_id
    once = f"assistant:report:{key}:{data.message_id}"
    if not cache.add(once, 1, REPORT_ONCE_SECONDS):
        return {"sent": False, "duplicate": True}
    try:
        record_event(ctx, events.REPORT_SENT, {**_caller_payload(caller), "reason": data.reason})
        _mail_report(ctx, who, details, data)
    except BaseException:
        cache.delete(once)
        raise
    return {"sent": True, "duplicate": False}


def _maybe_from_the_web(data: ReportSendIn) -> bool:
    """Whether the reported answer may quote pages of the web: its turn says so, or a caller that does not say (a Hub
    or a browser before the mark) while the search is offered."""
    return server_tools.searching() if data.web is None else data.web


def _mail_report(ctx: OperationContext, who: str, details: list[tuple[str, str]], data: ReportSendIn) -> None:
    """The report's mail to the support mailbox; 503 ``assistant.report_not_sent`` if it cannot leave."""
    from base.emails import branded_message

    lines = [
        *(f"{label}: {value}" for label, value in details),
        f"Reason: {data.reason}",
        f"Message: {data.message_id}",
        "",
        "Comment:",
        data.comment[:REPORT_TEXT_MAX] or "—",
        "",
        "Question:",
        data.question[:REPORT_TEXT_MAX] or "—",
        "",
        "Answer:",
        REPORT_WEB_ANSWER if _maybe_from_the_web(data) else data.answer[:REPORT_TEXT_MAX],
    ]
    try:
        branded_message(f"[Assistant report] {who} · {data.reason}", lines, [settings.SUPPORT_EMAIL], language="en").send()
    except Exception:  # noqa: BLE001 - any failure of the mail backend is answered, not raised
        logger.exception("assistant.report_mail_failed")
        with translation.override(ctx.language):
            raise OperationError(
                _("The report could not be sent: try again in a moment."), code="assistant.report_not_sent", status=503
            ) from None
