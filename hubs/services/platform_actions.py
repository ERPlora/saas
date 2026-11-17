"""The platform's actions in the admin (``hubs.admin``) and the nightly push of every snapshot."""

import logging
from collections import Counter

from django.db.models import F
from django.utils import timezone

from hubs.models import Hub
from hubs.services.hub_push import DELIVERED, LIVE_STATUSES, REFUSED, bump_state, sync_outcome
from hubs.services.session_revocations import deliver_revocation

logger = logging.getLogger(__name__)


def mark_for_internal_plans(hub_ids, allowed: bool) -> int:
    """«Let its owner buy the internal plans» (or stop it): the Store offers these businesses the internal plans
    (``Plan.objects.offered_to``). A plan already bought stays; how many businesses changed."""
    return Hub.objects.filter(pk__in=hub_ids).exclude(can_buy_internal_plans=allowed).update(
        can_buy_internal_plans=allowed, updated_at=timezone.now()
    )


def send_latest_state(hub_ids) -> Counter:
    """«Send the latest state to the Hub»: a newer snapshot of each live business, pushed now (with whatever
    else it owes). ``{delivered, owed}``; what stays owed, ``reconcile_hub_states`` retries."""
    for hub_id in Hub.objects.filter(pk__in=hub_ids, status__in=LIVE_STATUSES).values_list("id", flat=True):
        bump_state(hub_id)
    return retry_owed(hub_ids)


def retry_owed(hub_ids) -> Counter:
    """«Retry what the Hub still owes»: the pass of ``reconcile_hub_states`` on these businesses only (the
    registry, a deletion, a restoration, a snapshot behind). ``{delivered, owed}``."""
    counts = Counter(delivered=0, owed=0)
    for hub_id in hub_ids:
        try:
            outcome = sync_outcome(hub_id)
        except Exception:  # noqa: BLE001 - one business never stops the others; it stays owed
            logger.exception("hubs.admin.sync_crashed hub=%s", hub_id)
            outcome = None
        counts["delivered" if outcome == DELIVERED else "owed"] += 1
    return counts


def deliver_revocations(revocation_ids) -> Counter:
    """«End the sessions now»: deliver these revocations without waiting for their next attempt.
    ``{delivered, pending}``."""
    counts = Counter(delivered=0, pending=0)
    for revocation_id in revocation_ids:
        counts["delivered" if deliver_revocation(revocation_id) == DELIVERED else "pending"] += 1
    return counts


def push_snapshots(*, behind_only: bool = False) -> Counter:
    """One pass of ``push_hub_snapshots``: every live business, each with a newer version (the Hub ignores an
    equal one); with ``behind_only``, only the ones whose snapshot the Hub is behind on."""
    counts = Counter(pushed=0, owed=0, refused=0)
    live = Hub.objects.filter(status__in=LIVE_STATUSES)
    if not behind_only:
        live.update(state_version=F("state_version") + 1)
    for hub_id in live.filter(pushed_state_version__lt=F("state_version")).order_by("updated_at").values_list("id", flat=True):
        try:
            outcome = sync_outcome(hub_id)
        except Exception:  # noqa: BLE001 - one business never stops the batch
            logger.exception("hubs.push.crashed hub=%s", hub_id)
            outcome = None
        counts["pushed" if outcome == DELIVERED else "owed"] += 1
        counts[REFUSED] += outcome == REFUSED
    return counts
