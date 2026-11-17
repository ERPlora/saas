"""The state version of a business and its push to the Hub after the COMMIT, with what each answer records."""

import logging
from functools import partial
from uuid import UUID

from django.db import transaction
from django.db.models import F

from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub
from hubs.queries import hub_sync
from hubs.schemas import HubErrorIn
from hubs.services.hub_callbacks import PROVISION_FAILED, business_record_hub_error, system_ctx_for

logger = logging.getLogger(__name__)


LIVE_STATUSES = [Hub.Status.PREPARING, Hub.Status.ACTIVE, Hub.Status.PAST_DUE, Hub.Status.SUSPENDED]


Call = Hub.HubCall


def bump_state(hub_id: UUID) -> None:
    """The snapshot of the business changed: its next push carries a newer version."""
    Hub.objects.filter(pk=hub_id).update(state_version=F("state_version") + 1)


def push_after_commit(hub_id: UUID) -> None:
    """Push the business to the Hub once this transaction commits (never inside it)."""
    transaction.on_commit(partial(_sync_quietly, hub_id), robust=True)


def _sync_quietly(hub_id: UUID) -> None:
    try:
        sync_hub(hub_id)
    except Exception:  # noqa: BLE001 - after the COMMIT nothing may undo the write; it stays owed
        logger.exception("hubs.sync.crashed hub=%s", hub_id)


#: What one push of a business came to: everything acknowledged, the Hub away (retried, the run
#: fails), or the Hub refusing (recorded on the business, retried, the run fails).
DELIVERED, UNREACHABLE, REFUSED = "delivered", "unreachable", "refused"


def sync_hub(hub_id: UUID) -> bool:
    """Bring the Hub to what the SaaS knows of ``hub_id``; ``True`` when nothing stays owed."""
    return sync_outcome(hub_id) == DELIVERED


def sync_outcome(hub_id: UUID) -> str:  # noqa: C901, PLR0911
    """Push ``hub_id`` to the Hub: the deletion it owes (and nothing else), the restoration, the
    registry, then the snapshot if the Hub's version is behind.

    Each acknowledgement is recorded as it comes and clears a refusal recorded before. The first
    failure stops: the Hub being away leaves the rest owed (``unreachable``); the Hub refusing (4xx)
    also records its code on the business (``last_hub_error``, through ``hubs.business.record_hub_error``
    and its event), so the panel shows an error instead of
    waiting for ever (``refused``).
    """
    hub = Hub.objects.filter(pk=hub_id).first()
    if hub is None:
        return UNREACHABLE
    call = hub.pending_hub_call
    try:
        if call == Call.DELETE:
            _delete(hub)
            return DELIVERED
        if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
            return DELIVERED
        if call == Call.RESTORE:
            call = _restore(hub)
            if call is None:
                return DELIVERED
        if call == Call.PUT:
            version = hub.registry_version
            hub_client.put_hub(hub_sync.hub_registry(hub.id))
            record_registry_answered(hub.id, version)
        hub.refresh_from_db(fields=["state_version", "pushed_state_version"])
        if hub.pushed_state_version < hub.state_version:
            # The registry is acknowledged by now: a refusal from here on is the snapshot's (a ``whatsapp`` block
            # out of the Hub's schema refuses it whole), and the log has to say which.
            call = "state"
            snapshot = hub_sync.hub_snapshot(hub.id)
            hub_client.put_state(str(hub.id), snapshot)
            record_state_pushed(hub.id, snapshot["version"])
    except HubUnavailable as failed:
        logger.warning("hubs.sync.owed hub=%s call=%s: %s", hub_id, call or "state", failed)
        return UNREACHABLE
    except HubRefused as refused:
        logger.error("hubs.sync.refused hub=%s call=%s: %s", hub_id, call or "state", refused)
        _record_hub_error(hub_id, refused.code[:64])
        return REFUSED
    if Hub.objects.filter(pk=hub_id).exclude(last_hub_error__in=["", PROVISION_FAILED]).exists():
        # A delivered call clears the Hub's last refusal, not a preparation it still owes (``ready`` clears that one).
        _record_hub_error(hub_id, None)
    return DELIVERED


def _record_hub_error(hub_id: UUID, code: str | None) -> None:
    """Record (or clear) the Hub's refusal through its command, so the panel hears of it at once."""
    business_record_hub_error(system_ctx_for(hub_id), HubErrorIn(id=hub_id, hub_error=code))


def _delete(hub: Hub) -> None:
    """Send the deletion; a Hub that never had the business (404) has nothing to delete either."""
    try:
        hub_client.delete_hub(str(hub.id))
    except HubRefused as refused:
        if refused.status != 404:
            raise
    record_call_answered(hub.id, Call.DELETE)


def _restore(hub: Hub) -> str | None:
    """Send the restoration; the next call owed (``put`` if the Hub never had it), ``None`` if purged."""
    try:
        hub_client.restore_hub(str(hub.id))
    except HubRefused as refused:
        if refused.code == "hub_purged":
            Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.DELETED, pending_hub_call="")
            logger.warning("hubs.sync.purged hub=%s", hub.id)
            return None
        if refused.status != 404:
            raise
        Hub.objects.filter(pk=hub.pk, pending_hub_call=Call.RESTORE).update(pending_hub_call=Call.PUT)
        return Call.PUT
    record_call_answered(hub.id, Call.RESTORE)
    return ""


def record_call_answered(hub_id: UUID, call: str) -> None:
    """The Hub acknowledged ``call``: clear it, unless another call was owed meanwhile."""
    Hub.objects.filter(pk=hub_id, pending_hub_call=call).update(pending_hub_call="")


def record_registry_answered(hub_id: UUID, version: int) -> None:
    """The Hub has the registry ``version``: clear it, unless a newer one is owed (a rename meanwhile)."""
    Hub.objects.filter(pk=hub_id, pending_hub_call=Call.PUT, registry_version=version).update(pending_hub_call="")


def record_state_pushed(hub_id: UUID, version: int) -> None:
    """The Hub has the snapshot ``version``: never moves the pushed version back."""
    Hub.objects.filter(pk=hub_id, pushed_state_version__lt=version, state_version__gte=version).update(
        pushed_state_version=version
    )
