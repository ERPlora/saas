"""Usage: the nightly collection of what the Hub measured of each business, and its pruning."""

import logging
from collections import Counter
from datetime import UTC, date, timedelta

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import NotFound, PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event
from pydantic import ValidationError

from hubs import events, hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub, HubUsageDaily
from hubs.queries import access_control
from hubs.schemas.hub_usage import (
    HubUsageIn,
    HubUsagePageIn,
    UsagePruneIn,
    UsagePruneOut,
    UsageRecordIn,
    UsageRecordOut,
)
from hubs.services.people_notices import notify_people

logger = logging.getLogger(__name__)


#: The figures of a day of usage, as ``HubUsageDaily`` keeps them.
USAGE_FIGURES = (
    "s3_bytes",
    "db_bytes",
    "active_users_1d",
    "active_users_30d",
    "requests",
    "peak_connections",
    "busy_requests",
)
#: Counts that make ``collect_hub_usage`` end with an error, after its whole pass.
USAGE_FAILING_COUNTS = ("unreachable", "refused", "invalid", "failed")
#: Days a day of usage is kept: about 13 months, so that a day can be compared with the same day of the year before,
#: in the market's range for metrics (Grafana Cloud and New Relic keep 13 months, Google Analytics 14, CloudWatch and
#: Datadog 15). It has to outlast the longest window ``hubs.usage.series`` reads (``UsageSeriesIn``, 365 days), and a
#: test holds the two together.
USAGE_RETENTION_DAYS = 400


@operation(
    "hubs.usage.record",
    kind="command",
    permission="hubs.manage",
    input=UsageRecordIn,
    output=UsageRecordOut,
    ai=INTERNAL,  # only the platform runs it
)
def usage_record(ctx: OperationContext, data: UsageRecordIn) -> dict:
    """One day of a business's usage as the Hub measured it (``collect_hub_usage``); only the platform runs it.

    A day measured again replaces its figures. New or different figures are told to the owner and the admins
    (``hubs.business.usage_collected``), whose page re-runs; the same figures again write and tell nothing.
    """
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform records the usage of a business."), code="internal_command")
    if not Hub.objects.filter(pk=data.id).exists():
        raise access_control.not_found()
    figures = {name: getattr(data, name) for name in USAGE_FIGURES}
    sample, created = HubUsageDaily.objects.select_for_update().get_or_create(
        hub_id=data.id, day=data.day, defaults=figures
    )
    changed = created or any(getattr(sample, name) != value for name, value in figures.items())
    if changed:
        if not created:
            HubUsageDaily.objects.filter(pk=sample.pk).update(**figures, collected_at=timezone.now())
        notify_people(ctx, events.BUSINESS_USAGE_COLLECTED, data.id)
    return {"id": data.id, "day": data.day, "changed": changed}


@operation(
    "hubs.usage.prune",
    kind="command",
    permission="hubs.manage",
    input=UsagePruneIn,
    output=UsagePruneOut,
    ai=INTERNAL,  # only the nightly usage pass runs it
)
def usage_prune(ctx: OperationContext, data: UsagePruneIn) -> dict:
    """Forget the days of usage past ``USAGE_RETENTION_DAYS``, of every business (HUBS-F22; ``collect_hub_usage``, at
    the end of its pass); only the platform runs it. The day right on the limit stays, and with nothing to forget
    nothing is recorded."""
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform forgets the usage of a business."), code="internal_command")
    before = timezone.now().astimezone(UTC).date() - timedelta(days=USAGE_RETENTION_DAYS)
    deleted = HubUsageDaily.objects.filter(day__lt=before).delete()[0]
    if deleted:
        record_event(ctx, events.USAGE_PRUNED, {"before": before.isoformat(), "deleted": deleted})
    return {"before": before, "deleted": deleted}


def prune_usage() -> UsagePruneOut | None:
    """The end of a pass of ``collect_hub_usage``: ``hubs.usage.prune``, or ``None`` when it failed (logged). What the
    pass collected is already saved and said, so a failure here never takes its place: the run ends with an error
    after it."""
    try:
        return usage_prune(system_context(Scope("user", "system")), UsagePruneIn())
    except Exception:  # noqa: BLE001 - the collection is done; the run fails after saying it
        logger.exception("hubs.usage.prune_failed")
        return None


def usage_run_failed(counts: Counter) -> bool:
    """Whether a pass of ``collect_hub_usage`` met the Hub away or refusing, or an answer off the contract."""
    return any(counts[key] for key in USAGE_FAILING_COUNTS)


def collect_usage(day: date) -> Counter:
    """One pass of ``collect_hub_usage``: every page of ``GET /internal/usage?day=``, each business's day
    recorded on its own (one bad row, or one that fails, never stops the others).

    Counts: ``pages``; ``recorded`` (new or different) and ``unchanged``; ``unknown`` (a hub the SaaS never
    sold: the Hub's own, its templates; logged, not an error); ``invalid`` (a row, a page or a cursor off the
    contract); ``unreachable`` and ``refused`` (the Hub away, or its 4xx: the pass ends there, with what it
    had); ``failed`` (a row that crashed)."""
    keys = ("pages", "recorded", "unchanged", "unknown", "invalid", "unreachable", "refused", "failed")
    counts = Counter({key: 0 for key in keys})
    cursor, seen = None, set()
    while True:
        try:
            answer = hub_client.get_usage(day, cursor)
        except HubUnavailable as away:
            logger.error("hubs.usage.unreachable day=%s: %s", day, away)
            counts["unreachable"] += 1
            break
        except HubRefused as refused:
            logger.error("hubs.usage.refused day=%s: %s", day, refused)
            counts["refused"] += 1
            break
        try:
            page = HubUsagePageIn.model_validate(answer.body)
        except ValidationError as broken:
            logger.error("hubs.usage.invalid_page day=%s: %s", day, broken)
            counts["invalid"] += 1
            break
        if page.day != day:
            logger.error("hubs.usage.invalid_page day=%s: the Hub answered for %s", day, page.day)
            counts["invalid"] += 1
            break
        counts["pages"] += 1
        for row in page.hubs:
            _record_counted(day, row, counts)
        cursor = page.next_cursor
        if cursor is None:
            break
        if cursor in seen:
            logger.error("hubs.usage.invalid_page day=%s: the Hub sent the cursor %r again", day, cursor)
            counts["invalid"] += 1
            break
        seen.add(cursor)
    return counts


def _record_counted(day: date, row: dict, counts: Counter) -> None:
    try:
        measured = HubUsageIn.model_validate(row)
    except ValidationError as broken:
        logger.error("hubs.usage.invalid_row day=%s: %s", day, broken)
        counts["invalid"] += 1
        return
    try:
        recorded = usage_record(
            system_context(Scope("user", "system")), UsageRecordIn(**measured.model_dump(), day=day)
        )
    except NotFound:
        logger.warning("hubs.usage.unknown_hub day=%s hub=%s", day, measured.id)
        counts["unknown"] += 1
        return
    except Exception:  # noqa: BLE001 - one business never stops the pass; the run fails after it
        logger.exception("hubs.usage.crashed day=%s hub=%s", day, measured.id)
        counts["failed"] += 1
        return
    counts["recorded" if recorded.changed else "unchanged"] += 1
