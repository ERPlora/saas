"""The Hub's turn: the plan's messages and what each turn spent.

- ``assistant.message.claim`` / ``.release``: a message of the plan's monthly allowance (a demo's own few), taken
  before the model is called and given back if the turn failed before answering. An account's claim that reaches
  80 % of its month, or the last message, mails it once that month (``assistant.emails``).
- ``assistant.usage.record``: what a turn, an embedding or the voice spent (tokens, dictations, characters read
  aloud) and its cost in USD.
"""

import logging
from datetime import timedelta
from fractions import Fraction
from functools import partial

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from assistant import emails, events, queries
from assistant.models import AssistantUsage
from assistant.schemas import Caller, ClaimOut, MessageReleaseIn, UsageOut, UsageRecordIn

logger = logging.getLogger("assistant.services")


#: How long the row of a demo is kept after it started: a demo lives an hour, and its row is forgotten when a later
#: demo starts (no task needed).
DEMO_USAGE_KEPT = timedelta(days=1)


def _caller_payload(caller: Caller) -> dict:
    payload = {"hub": str(caller.hub_id) if caller.hub_id else None, "demo": caller.demo}
    if caller.user_id is not None:
        payload["user"] = str(caller.user_id)
    return payload


def _rows_of(caller: Caller, month):
    """The caller's rows that count ``month``: a business's or an account's of that month, a demo's only one."""
    if caller.demo:
        return AssistantUsage.objects.filter(demo=caller.demo)
    if caller.user_id is not None:
        return AssistantUsage.objects.filter(user_id=caller.user_id, month=month)
    return AssistantUsage.objects.filter(hub_id=caller.hub_id, month=month)


def _row_of(caller: Caller, now) -> AssistantUsage:
    """The caller's row of usage now (made the first time): a business's or an account's of this month, a demo's only
    one. A demo's first row forgets the rows of the demos that started more than a day ago."""
    if caller.demo:
        row, created = AssistantUsage.objects.get_or_create(demo=caller.demo, defaults={"month": queries.usage.month_of(now)})
        if created:
            AssistantUsage.objects.exclude(demo="").filter(created_at__lt=now - DEMO_USAGE_KEPT).delete()
        return row
    if caller.user_id is not None:
        return AssistantUsage.objects.get_or_create(user_id=caller.user_id, month=queries.usage.month_of(now))[0]
    return AssistantUsage.objects.get_or_create(hub_id=caller.hub_id, month=queries.usage.month_of(now))[0]


@operation(
    "assistant.message.claim",
    kind="command",
    permission="assistant.manage",
    input=Caller,
    output=ClaimOut,
    ai=INTERNAL,  # platform
)
def message_claim(ctx: OperationContext, data: Caller) -> dict:
    """Take a message of the caller's allowance for a turn, before the model is called (the platform only): one
    ``UPDATE … WHERE messages < limit``, which a concurrent claim waits on and then evaluates again, so two turns
    never pass the last message together. Without one left nothing is taken and ``claimed`` is false."""
    queries.gates.platform_only(ctx)
    now = timezone.now()
    limit = queries.usage.monthly_limit(data, now)
    row = _row_of(data, now)
    claimed = AssistantUsage.objects.filter(pk=row.pk, messages__lt=limit).update(
        messages=F("messages") + 1, updated_at=now
    )
    row.refresh_from_db(fields=["messages", "month"])
    if claimed:
        record_event(ctx, events.MESSAGE_CLAIMED, {**_caller_payload(data), "used": row.messages, "limit": limit})
    if data.user_id is not None:
        _warn_the_account(ctx, row, limit, now)
    return {
        "claimed": bool(claimed),
        "month": row.month,
        "used": row.messages,
        "limit": limit,
        "resets_at": None if data.demo else queries.usage.resets_at(row.month),
        "demo": bool(data.demo),
    }


#: From this share of the month's messages an account is mailed that they run out: where the panel's footer starts
#: saying it (``NOTE_FROM`` of ``usageNote`` in @erplora/ui), the 24th of 30.
NEAR_FROM = Fraction(4, 5)
#: The mark of each mail that the month's messages run out, on the account's row of the month.
WARNING_MARKS = {"near": "near_warned_at", "spent": "spent_warned_at"}


def _warning_due(used: int, limit: int) -> str | None:
    """The mail ``used`` of ``limit`` reaches: ``"spent"`` at the last one (then never how many are left), ``"near"``
    from ``NEAR_FROM``, none before it nor without an allowance."""
    if limit <= 0:
        return None
    if used >= limit:
        return "spent"
    return "near" if Fraction(used, limit) >= NEAR_FROM else None


def _warn_the_account(ctx: OperationContext, row: AssistantUsage, limit: int, now) -> None:
    """Take the month's mark of the mail the account's ``row`` reaches — one ``UPDATE … WHERE <mark> IS
    NULL``, which a concurrent turn waits on and then finds taken, so each mail leaves once a month —, record it, and
    send the mail after the COMMIT. Also when the claim was refused, so a last mail that could not leave is tried
    again with the next message the person writes."""
    warning = _warning_due(row.messages, limit)
    if warning is None:
        return
    mark = WARNING_MARKS[warning]
    if not AssistantUsage.objects.filter(pk=row.pk, **{f"{mark}__isnull": True}).update(**{mark: now}):
        return
    record_event(
        ctx, events.USAGE_WARNED, {"user": str(row.user_id), "warning": warning, "used": row.messages, "limit": limit}
    )
    transaction.on_commit(partial(_mail_the_warning, row.pk, mark, now, row.messages, limit), robust=True)


def _mail_the_warning(row_id, mark: str, taken_at, used: int, limit: int) -> None:
    """After the COMMIT: the mail of ``mark`` to the account of the row. One that cannot leave frees the mark it took
    (only its own), so the next message of the month tries again with the figures of that moment."""
    row = AssistantUsage.objects.select_related("user").filter(pk=row_id).first()
    if row is None:
        logger.warning("assistant.mail.no_account usage=%s: the account went away before its mail", row_id)
        return
    resets_on = queries.usage.resets_at(row.month).date()
    if mark == WARNING_MARKS["spent"]:
        sent = emails.send_messages_spent(row.user, limit=limit, resets_on=resets_on)
    else:
        sent = emails.send_messages_near(row.user, used=used, limit=limit, resets_on=resets_on)
    if not sent:
        AssistantUsage.objects.filter(pk=row_id, **{mark: taken_at}).update(**{mark: None})


@operation(
    "assistant.message.release",
    kind="command",
    permission="assistant.manage",
    input=MessageReleaseIn,
    output=UsageOut,
    ai=INTERNAL,  # platform
)
def message_release(ctx: OperationContext, data: MessageReleaseIn) -> dict:
    """Give back the message a turn took in ``month``, when it failed before answering anything (the platform only):
    the person saw no answer, so it is not spent. Never below zero."""
    queries.gates.platform_only(ctx)
    caller = data.caller
    rows = _rows_of(caller, data.month)
    if rows.filter(messages__gt=0).update(messages=F("messages") - 1, updated_at=timezone.now()):
        record_event(
            ctx,
            events.MESSAGE_RELEASED,
            {**_caller_payload(caller), "used": rows.values_list("messages", flat=True).first() or 0},
        )
    return queries.usage.usage_of(caller, timezone.now())


@operation(
    "assistant.usage.record",
    kind="command",
    permission="assistant.manage",
    input=UsageRecordIn,
    output=UsageOut,
    ai=INTERNAL,  # platform
)
def usage_record(ctx: OperationContext, data: UsageRecordIn) -> dict:
    """Add what a turn, an embedding or the voice spent to the caller's row of now (the platform only): tokens,
    dictations, characters read aloud and their cost in USD. Never a message: those are claimed."""
    queries.gates.platform_only(ctx)
    now = timezone.now()
    row = _row_of(data.caller, now)
    spent = data.model_dump(exclude={"caller"})
    AssistantUsage.objects.filter(pk=row.pk).update(
        **{field: F(field) + value for field, value in spent.items()}, updated_at=now
    )
    record_event(ctx, events.USAGE_RECORDED, {**_caller_payload(data.caller), **{k: str(v) for k, v in spent.items()}})
    return queries.usage.usage_of(data.caller, now)
