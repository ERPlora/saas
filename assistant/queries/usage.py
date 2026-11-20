"""What a caller spent of its allowance.

- ``assistant.usage.show``: what a business (or a demo) spent of its allowance: the plan's monthly
  messages (a demo, its own few for its whole life).
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone

from django.conf import settings
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation

from assistant.models import AssistantUsage
from assistant.queries.gates import staff_with
from assistant.schemas import Caller, UsageOut
from hubs.queries import plan_catalog


def month_of(now: datetime) -> date:
    """The first day of ``now``'s calendar month in UTC: the window of the allowance."""
    return now.astimezone(dt_timezone.utc).date().replace(day=1)


def resets_at(month: date) -> datetime:
    """When the allowance of ``month`` comes back: 00:00 UTC on the first day of the next month."""
    year, following = (month.year + 1, 1) if month.month == 12 else (month.year, month.month + 1)
    return datetime(year, following, 1, tzinfo=dt_timezone.utc)


def monthly_limit(caller: Caller, now: datetime) -> int:
    """The messages the caller may send: a demo, its own few for its whole life; an account, the panel's fixed ones
    this month (``ASSISTANT_ACCOUNT_MESSAGES``, whatever the plans of its businesses); a business, its plan's this
    month (``Plan.assistant_messages_per_month`` of the plan whose rights it has now, its trial's included; 0 = none)."""
    if caller.demo:
        return settings.ASSISTANT_DEMO_MESSAGES
    if caller.user_id is not None:
        return settings.ASSISTANT_ACCOUNT_MESSAGES
    plan = plan_catalog.effective_plan(caller.hub_id, now)
    return plan.assistant_messages_per_month if plan is not None else 0


def usage_row(caller: Caller, now: datetime):
    """The caller's row of usage now (a business's or an account's this month, a demo's only one), or ``None`` before
    its first use."""
    if caller.demo:
        return AssistantUsage.objects.filter(demo=caller.demo).first()
    if caller.user_id is not None:
        return AssistantUsage.objects.filter(user_id=caller.user_id, month=month_of(now)).first()
    return AssistantUsage.objects.filter(hub_id=caller.hub_id, month=month_of(now)).first()


def usage_of(caller: Caller, now: datetime) -> dict:
    row = usage_row(caller, now)
    return {
        "used": row.messages if row is not None else 0,
        "limit": monthly_limit(caller, now),
        "resets_at": None if caller.demo else resets_at(month_of(now)),
        "demo": bool(caller.demo),
    }


@operation(
    "assistant.usage.show",
    kind="query",
    permission="assistant.manage",
    input=Caller,
    output=UsageOut,
    ai=INTERNAL,  # platform
)
def usage_show(ctx: OperationContext, data: Caller) -> dict:
    """What the caller spent of its allowance now (the platform: the Hub's ``usage`` door and every turn's last
    frame; the staff: ``view_assistantusage``)."""
    if ctx.actor != "system":
        staff_with(ctx, "assistant.view_assistantusage")
    return usage_of(data, timezone.now())
