"""The ``saas-worker``'s pass that asks the Hub about the maintenance scheduled for each ready business's night.

When ERPlora's staff asks the Hub to move a business to another server in its night, its signed status poll
(``GET /internal/hubs/{id}``) says when that starts, ``move_scheduled_for`` (UTC; ``null`` without one, once started or
cancelled). The Hub tells nobody: the SaaS asks at each round (``base.worker``), never on a person's request, and keeps
the answer for the list and the page of the business (``hubs.business.record_scheduled_move``).
"""

import logging
from collections import Counter
from collections.abc import Callable
from uuid import UUID

from django.db.models import F

from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub
from hubs.schemas.hub_callbacks import HubScheduledMoveIn
from hubs.services.exclusive_runs import run_exclusively
from hubs.services.hub_callbacks import business_record_scheduled_move, system_ctx_for

logger = logging.getLogger(__name__)

#: The pass's name in the worker's log lines, and its lock's.
PASS = "check_scheduled_moves"
#: The ready businesses that still live: one being prepared has nothing to move yet, a deleted one is never asked.
ASKED_STATUSES = (Hub.Status.ACTIVE, Hub.Status.PAST_DUE, Hub.Status.SUSPENDED)
#: Counts that make a pass end with an error.
FAILING_COUNTS = ("unreachable", "failed")


def run_failed(counts: Counter) -> bool:
    """Whether the Hub could not be asked about a business, or answered off the contract."""
    return any(counts[key] for key in FAILING_COUNTS)


def check_scheduled_moves_exclusively(go_on: Callable[[], bool] | None = None) -> Counter | None:
    """One pass under its lock: its counts, or ``None`` when another run holds the lock (and this one did nothing)."""
    with run_exclusively(PASS) as mine:
        return check_scheduled_moves(go_on=go_on) if mine else None


def check_scheduled_moves(go_on: Callable[[], bool] | None = None) -> Counter:
    """Ask the Hub about every ready business; ``go_on`` is asked before each call, and once it says no the rest
    waits for the next round (``cut_short``)."""
    counts = Counter(dict.fromkeys(("checked", "scheduled", "unreachable", "failed", "cut_short"), 0))
    asked = Hub.objects.filter(status__in=ASKED_STATUSES)
    # The ones with a move ahead go first, so a pass cut short still says its start or its cancellation.
    for hub_id in asked.order_by(F("move_scheduled_for").asc(nulls_last=True), "id").values_list("id", flat=True):
        if go_on is not None and not go_on():
            counts["cut_short"] = 1
            break
        try:
            _check(hub_id, counts)
        except Exception:  # one business never stops the pass
            logger.exception("hubs.scheduled_move.crashed hub=%s", hub_id)
            counts["failed"] += 1
    return counts


def _check(hub_id: UUID, counts: Counter) -> None:
    try:
        answer = hub_client.get_hub(str(hub_id))
    except (HubRefused, HubUnavailable):
        counts["unreachable"] += 1
        return
    if not isinstance(answer.body, dict):
        raise ValueError("the Hub's status poll is not an object")
    data = HubScheduledMoveIn(id=hub_id, move_scheduled_for=answer.body.get("move_scheduled_for"))
    business_record_scheduled_move(system_ctx_for(hub_id), data)
    counts["checked"] += 1
    counts["scheduled"] += data.move_scheduled_for is not None
