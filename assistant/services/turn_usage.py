"""The Hub's turn: the plan's messages and what each turn spent.

- ``assistant.message.claim`` / ``.release``: a message of the plan's monthly allowance (a demo's own few), taken
  on the row of the model asked before it is called and given back there if the turn failed before answering; the
  allowance adds the messages of every model. An account's claim that reaches 80 % of its month, or the last message,
  mails it once that month (``assistant.emails``).
- ``assistant.usage.record``: what a turn, an embedding or the voice spent with a model (tokens, dictations,
  characters read aloud) and its cost in USD, on the row of that model.
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
from assistant.schemas import Caller, ClaimIn, ClaimOut, MessageReleaseIn, UsageOut, UsageRecordIn

logger = logging.getLogger("assistant.services")


#: How long the row of a demo is kept after it started: a demo lives an hour, and its row is forgotten when a later
#: demo starts (no task needed).
DEMO_USAGE_KEPT = timedelta(days=1)


def _caller_payload(caller: Caller) -> dict:
    payload = {"hub": str(caller.hub_id) if caller.hub_id else None, "demo": caller.demo}
    if caller.user_id is not None:
        payload["user"] = str(caller.user_id)
    return payload


def _row_of(caller: Caller, model: str, now) -> AssistantUsage:
    """The caller's row of usage of ``model`` now (made the first time): a business's or an account's of this month, a
    demo's of its whole life. A demo's first row forgets the rows of the demos that started more than a day ago."""
    month = queries.usage.month_of(now)
    if caller.demo:
        row, created = AssistantUsage.objects.get_or_create(demo=caller.demo, model=model, defaults={"month": month})
        if created:
            AssistantUsage.objects.exclude(demo="").filter(created_at__lt=now - DEMO_USAGE_KEPT).delete()
        return row
    if caller.user_id is not None:
        return AssistantUsage.objects.get_or_create(user_id=caller.user_id, month=month, model=model)[0]
    return AssistantUsage.objects.get_or_create(hub_id=caller.hub_id, month=month, model=model)[0]


@operation(
    "assistant.message.claim",
    kind="command",
    permission="assistant.manage",
    input=ClaimIn,
    output=ClaimOut,
    ai=INTERNAL,  # platform
)
def message_claim(ctx: OperationContext, data: ClaimIn) -> dict:
    """Take a message of the caller's allowance for a turn that asks ``data.model``, before it is called (the platform
    only), on the row of that model. The caller's rows of every model are locked first, so a concurrent claim waits
    for this one and then counts what it took; the row of the model is one ``UPDATE … WHERE messages < limit - the
    other models' messages``, which a concurrent claim on the same new row evaluates again, so two turns never pass
    the last message together. Without one left nothing is taken (nor a row made) and ``claimed`` is false."""
    queries.gates.platform_only(ctx)
    caller, now = data.caller, timezone.now()
    limit = queries.usage.monthly_limit(caller, now)
    month = queries.usage.month_of(now)
    rows = queries.usage.rows_of(caller, month)
    list(rows.select_for_update().order_by("pk").values_list("pk", flat=True))
    elsewhere = queries.usage.messages_of(rows.exclude(model=data.model))
    claimed = 0
    if elsewhere < limit:
        row = _row_of(caller, data.model, now)
        claimed = AssistantUsage.objects.filter(pk=row.pk, messages__lt=limit - elsewhere).update(
            messages=F("messages") + 1, updated_at=now
        )
    used = queries.usage.messages_of(rows)
    if claimed:
        record_event(ctx, events.MESSAGE_CLAIMED, {**_caller_payload(caller), "used": used, "limit": limit})
    if caller.user_id is not None:
        _warn_the_account(ctx, rows, data.model, limit, now)
    return {
        "claimed": bool(claimed),
        "month": month,
        "model": data.model,
        "used": used,
        "limit": limit,
        "resets_at": None if caller.demo else queries.usage.resets_at(month),
        "demo": bool(caller.demo),
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


def _warn_the_account(ctx: OperationContext, rows, model: str, limit: int, now) -> None:
    """Take the month's mark of the mail the account's ``rows`` of the month reach, on the row of ``model`` (or its
    first row, when the claim was refused before making one), unless one of them has it already: the claim locked
    them, so a concurrent turn waits and then finds it taken, and each mail leaves once a month whatever model
    answers. Record it, and send the mail after the COMMIT. Also when the claim was refused, so a last mail that could
    not leave is tried again with the next message the person writes."""
    used = queries.usage.messages_of(rows)
    warning = _warning_due(used, limit)
    if warning is None:
        return
    mark = WARNING_MARKS[warning]
    if rows.filter(**{f"{mark}__isnull": False}).exists():
        return
    row = rows.filter(model=model).first() or rows.order_by("pk").first()
    AssistantUsage.objects.filter(pk=row.pk).update(**{mark: now})
    record_event(ctx, events.USAGE_WARNED, {"user": str(row.user_id), "warning": warning, "used": used, "limit": limit})
    transaction.on_commit(partial(_mail_the_warning, row.pk, mark, now, used, limit), robust=True)


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
    """Give back the message a turn took in ``month`` on ``model``, when it failed before answering anything (the
    platform only): the person saw no answer, so it is not spent. Never below zero."""
    queries.gates.platform_only(ctx)
    caller = data.caller
    rows = queries.usage.rows_of(caller, data.month)
    if rows.filter(model=data.model, messages__gt=0).update(messages=F("messages") - 1, updated_at=timezone.now()):
        record_event(ctx, events.MESSAGE_RELEASED, {**_caller_payload(caller), "used": queries.usage.messages_of(rows)})
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
    """Add what a turn, an embedding or the voice spent to the caller's row of its model now (the platform only):
    tokens, dictations, characters read aloud and their cost in USD. Never a message: those are claimed."""
    queries.gates.platform_only(ctx)
    now = timezone.now()
    row = _row_of(data.caller, data.model, now)
    spent = data.model_dump(exclude={"caller", "model"})
    AssistantUsage.objects.filter(pk=row.pk).update(
        **{field: F(field) + value for field, value in spent.items()}, updated_at=now
    )
    record_event(ctx, events.USAGE_RECORDED, {**_caller_payload(data.caller), **{k: str(v) for k, v in spent.items()}})
    return queries.usage.usage_of(data.caller, now)
