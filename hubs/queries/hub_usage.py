"""The usage the Hub measures of a business each night, against the space its plan includes."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import AI, operation

from hubs.models import Hub, HubUsageDaily, Plan, Subscription
from hubs.queries.access_control import Role, access, account_of
from hubs.schemas import UsageGetIn, UsageOut, UsageSeriesIn, UsageSeriesOut


GIB = 1024**3
#: The space for files a plan includes, by its module tier (``Plan.included_level``). ``Plan`` has no size limits
#: and the customer sees a percentage of «the space of the plan», so the space follows the tier instead of a
#: column (``hubs/README.md``, «Uso»).
STORAGE_LIMIT_GIB = {
    Plan.IncludedLevel.FREE: 1,
    Plan.IncludedLevel.BASIC: 5,
    Plan.IncludedLevel.PRO: 20,
    Plan.IncludedLevel.ENTERPRISE: 50,
}


def storage_limit_bytes(plan: Plan | None) -> int | None:
    """The space for files ``plan`` includes, in bytes; ``None`` without a plan (or a tier not in the table)."""
    if plan is None or plan.included_level not in STORAGE_LIMIT_GIB:
        return None
    return STORAGE_LIMIT_GIB[plan.included_level] * GIB


def usage_percent(used: int, limit: int | None) -> int | None:
    """How full, rounded to the nearest whole (half up); over 100 past the limit; ``None`` without one."""
    if not limit:
        return None
    return (used * 100 + limit // 2) // limit


def last_measured_day(now: datetime) -> date:
    """The day a nightly collection measures: yesterday, in UTC (``collect_hub_usage``)."""
    return now.astimezone(UTC).date() - timedelta(days=1)


def usage_point(sample: HubUsageDaily, limit: int | None) -> dict[str, Any]:
    return {
        "day": sample.day,
        # The files only (S3): the database is the admin's.
        "storage": {
            "used_bytes": sample.s3_bytes,
            "limit_bytes": limit,
            "percent": usage_percent(sample.s3_bytes, limit),
        },
        "active_users": {"on_day": sample.active_users_1d, "last_30_days": sample.active_users_30d},
    }


def usage_of(hub: Hub, plan: Plan | None, now: datetime) -> dict[str, Any] | None:
    """The last day measured of ``hub`` against the space of ``plan`` (the one in force); ``None`` before
    the first night."""
    sample = HubUsageDaily.objects.filter(hub=hub).order_by("-day").first()
    if sample is None:
        return None
    return {
        **usage_point(sample, storage_limit_bytes(plan)),
        "stale": sample.day < last_measured_day(now),
    }


def plan_in_force(hub: Hub, now: datetime) -> Plan | None:
    subscription = Subscription.objects.select_related("plan", "trial_plan").filter(hub=hub).first()
    return subscription.effective_plan(now) if subscription else None


@operation(
    "hubs.usage.get",
    kind="query",
    permission="hubs.view",
    input=UsageGetIn,
    output=UsageOut,
    expose_api=True,
    ai=AI(
        description="The last day measured of one business's usage (its storage and its active users) against what "
                    "its plan includes; its owner and administrators.",
        asks={
            "en": (
                "how much storage is the bar using?",
                "am I close to my plan's limit?",
                "how many active users does the salon have?",
            ),
            "es": (
                "¿cuánto espacio ocupa el bar?",
                "¿me estoy pasando del límite del plan?",
                "¿cuánta gente usa la peluquería?",
            ),
        },
    ),
)
def usage_get(ctx: OperationContext, data: UsageGetIn) -> dict[str, Any]:
    """The last day the Hub measured of a business (the «Usage» card of its Summary): its owner and admins."""
    user = account_of(ctx)
    hub = access(user, data.business_id, Role.ADMIN).hub
    now = timezone.now()
    usage = usage_of(hub, plan_in_force(hub, now), now)
    if usage is None:
        raise NotFound(
            _("No usage of this business has been measured yet: the first figures arrive the night after it is created."),
            code="hubs.usage_not_collected",
        )
    return usage


@operation(
    "hubs.usage.series",
    kind="query",
    permission="hubs.view",
    input=UsageSeriesIn,
    output=UsageSeriesOut,
    expose_api=True,
    ai=AI(
        description="One business's usage (its storage and its active users) day by day over the last days, against "
                    "what its plan includes.",
        asks={
            "en": (
                "show the bar's usage over the last month",
                "how has my usage gone day by day?",
                "usage of the salon this week",
            ),
            "es": (
                "¿cómo ha ido el consumo del bar este mes?",
                "uso día a día de la peluquería",
                "gráfica de uso de la última semana",
            ),
        },
    ),
)
def usage_series(ctx: OperationContext, data: UsageSeriesIn) -> dict[str, Any]:
    """The days measured of a business in the last ``days`` up to yesterday, oldest first, against the space
    its plan includes today (for a chart): its owner and admins."""
    user = account_of(ctx)
    hub = access(user, data.business_id, Role.ADMIN).hub
    now = timezone.now()
    limit = storage_limit_bytes(plan_in_force(hub, now))
    first = last_measured_day(now) - timedelta(days=data.days - 1)
    samples = HubUsageDaily.objects.filter(hub=hub, day__gte=first).order_by("day")
    return {
        "business_id": hub.id,
        "limit_bytes": limit,
        "points": [usage_point(sample, limit) for sample in samples],
    }
