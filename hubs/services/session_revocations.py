"""Ending an account's sessions in the Hub: queued in the command, delivered after the COMMIT."""

import logging
from datetime import timedelta
from functools import partial
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub, SessionRevocation
from hubs.services.hub_push import DELIVERED, REFUSED, UNREACHABLE

logger = logging.getLogger(__name__)


def revoke_after_commit(user_id: UUID, hub_id: UUID | None = None) -> SessionRevocation:
    """End the account's sessions in the business (or in every one, ``hub_id`` empty).

    Queued in this transaction (``SessionRevocation``) and delivered once it commits; if the Hub is away
    or refuses it, ``reconcile_hub_states`` retries it (``deliver_revocation``). A removed member also
    leaves the next snapshot, the Hub's second way of learning it.
    """
    revocation = SessionRevocation.objects.create(user_id=user_id, hub_id=hub_id)
    transaction.on_commit(partial(_deliver_quietly, revocation.id), robust=True)
    return revocation


def _deliver_quietly(revocation_id: UUID) -> None:
    try:
        deliver_revocation(revocation_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the write; it stays queued
        logger.exception("hubs.revoke.crashed revocation=%s", revocation_id)


#: The wait before retrying a revocation the Hub did not take: 15 minutes (one ``reconcile_hub_states``
#: run) after the first failure, doubling with each one, never more than 6 hours.
REVOCATION_FIRST_WAIT = timedelta(minutes=15)
REVOCATION_LONGEST_WAIT = timedelta(hours=6)


def revocation_backoff(attempts: int) -> timedelta:
    """How long a revocation waits after its ``attempts``-th failed delivery."""
    return min(REVOCATION_FIRST_WAIT * 2 ** max(attempts - 1, 0), REVOCATION_LONGEST_WAIT)


def deliver_revocation(revocation_id: UUID) -> str:
    """Send a queued revocation to the Hub: ``DELIVERED`` (also when nothing was left to send), or
    ``UNREACHABLE``/``REFUSED`` with the error and the next wait recorded on the row.

    A purged business has no session left: delivered without a call. Idempotent: a delivered row is
    never sent again, and the Hub's revoke is idempotent if two deliveries race.
    """
    revocation = SessionRevocation.objects.select_related("hub").filter(pk=revocation_id, delivered_at__isnull=True).first()
    if revocation is None:
        return DELIVERED
    if revocation.hub is None or revocation.hub.status != Hub.Status.DELETED:
        try:
            hub_client.revoke_sessions(str(revocation.user_id), str(revocation.hub_id) if revocation.hub_id else None)
        except HubUnavailable as failed:
            _revocation_failed(revocation, str(failed))
            return UNREACHABLE
        except HubRefused as refused:
            _revocation_failed(revocation, str(refused))
            return REFUSED
    SessionRevocation.objects.filter(pk=revocation.pk, delivered_at__isnull=True).update(
        delivered_at=timezone.now(), attempts=F("attempts") + 1, last_error=""
    )
    return DELIVERED


def _revocation_failed(revocation: SessionRevocation, error: str) -> None:
    attempts = revocation.attempts + 1
    logger.warning("hubs.revoke.owed user=%s hub=%s attempt=%s: %s", revocation.user_id, revocation.hub_id, attempts, error)
    SessionRevocation.objects.filter(pk=revocation.pk, delivered_at__isnull=True).update(
        attempts=attempts,
        last_error=error[:255],
        next_attempt_at=timezone.now() + revocation_backoff(attempts),
    )
