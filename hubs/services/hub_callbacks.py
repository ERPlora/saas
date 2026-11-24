"""What the Hub reports of a business (ready, its last refusal, a provisioning pause, the maintenance scheduled for
its night), as the platform."""

from functools import partial
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from hubs import emails, events
from hubs.models import Hub, HubMember
from hubs.queries import access_control, membership
from hubs.queries.access_control import Role
from hubs.schemas.hub_callbacks import HubErrorIn, HubMaintenanceIn, HubScheduledMoveIn, HubStatusOut, MarkReadyIn


#: The Hub's last error recorded on a business it says it could not prepare (``failed``): the panel shows «We could not
#: prepare it. We keep retrying» (the Hub retries on its own and calls ``ready`` once it can), never «preparing» for ever.
PROVISION_FAILED = "hubs.provision_failed"


def system_ctx_for(hub_id: UUID) -> OperationContext:
    """The platform acting on a business, in its owner's channel (its live lists re-run)."""
    owner = membership.owner_id(hub_id)
    return system_context(Scope("user", str(owner) if owner else "system"))


@operation(
    "hubs.business.mark_ready",
    kind="command",
    permission="hubs.manage",
    input=MarkReadyIn,
    output=HubStatusOut,
    ai=INTERNAL,  # only the Hub calls it
)
def business_mark_ready(ctx: OperationContext, data: MarkReadyIn) -> dict:
    """The Hub's ``POST /internal/hubs/{id}/ready``: the business's database is ready.

    Only the platform calls it (``hubs.internal``). A business being prepared becomes active, and its owner
    hears it by mail after the COMMIT (once: the next call finds it active); one that was suspended or
    deleted meanwhile keeps its status and no mail. Idempotent.
    """
    if ctx.actor != "system":
        raise PermissionDenied(
            _("Only the Hub reports a business ready."), code="internal_command"
        )
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    if hub is None:
        raise access_control.not_found()
    changed = []
    if hub.ready_at is None:
        hub.ready_at = timezone.now()
        changed.append("ready_at")
    opens = hub.status == Hub.Status.PREPARING
    if opens:
        hub.status = Hub.Status.ACTIVE
        changed.append("status")
    if hub.last_hub_error == PROVISION_FAILED:
        # Ready after the Hub's own retry: the preparation it reported failed is no longer owed.
        hub.last_hub_error, hub.hub_error_at = "", None
        changed += ["last_hub_error", "hub_error_at"]
    if hub.maintenance is not None:
        hub.maintenance = None
        changed.append("maintenance")
    if changed:
        hub.save(update_fields=[*changed, "updated_at"])
        record_event(ctx, events.BUSINESS_READY, {"id": str(hub.id)})
    owner = (
        HubMember.objects.filter(hub=hub, role=Role.OWNER).select_related("user").first()
        if opens
        else None
    )
    if owner is not None:
        transaction.on_commit(
            partial(emails.send_ready, hub, owner.user, base_url=emails.base_url(ctx.request)),
            robust=True,
        )
    return {"id": hub.id, "status": hub.status, "ready_at": hub.ready_at}


def _system_hub(ctx: OperationContext, data: HubErrorIn | HubMaintenanceIn | HubScheduledMoveIn) -> Hub:
    """The business a platform answer changes, after refusing any caller that is not the platform."""
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform records the Hub's answers."), code="internal_command")
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    if hub is None:
        raise access_control.not_found()
    return hub


@operation(
    "hubs.business.record_hub_error",
    kind="command",
    permission="hubs.manage",
    input=HubErrorIn,
    output=HubStatusOut,
    ai=INTERNAL,  # only the push to the Hub writes it
)
def business_record_hub_error(ctx: OperationContext, data: HubErrorIn) -> dict:
    """The Hub's last refusal of a call about the business (its error code), or ``None`` once a call
    succeeds; only the push writes it (``sync_outcome``, after a COMMIT or in ``saas-cron``).

    A command, so the change has its event: on the owner's channel (``system_ctx_for``, as the Hub's
    ``ready``) the list and the page of the business re-run at once, and «Preparing» turns into «Error»
    (and back) without waiting for the 300 s safety re-run. The same answer again records nothing.
    """
    hub = _system_hub(ctx, data)
    code = data.hub_error or ""
    if hub.last_hub_error != code:
        hub.last_hub_error = code
        hub.hub_error_at = timezone.now() if code else None
        hub.save(update_fields=["last_hub_error", "hub_error_at", "updated_at"])
        record_event(ctx, events.BUSINESS_HUB_ERROR_CHANGED, {"id": str(hub.id), "hub_error": code or None})
    return {"id": hub.id, "status": hub.status, "ready_at": hub.ready_at}


@operation(
    "hubs.business.record_maintenance",
    kind="command",
    permission="hubs.manage",
    input=HubMaintenanceIn,
    output=HubStatusOut,
    ai=INTERNAL,
)
def business_record_maintenance(ctx: OperationContext, data: HubMaintenanceIn) -> dict:
    """Persist the Hub's real provisioning pause, or clear it after the lift, and notify the owner at once."""
    hub = _system_hub(ctx, data)
    maintenance = (
        data.maintenance.model_dump(mode="json")
        if data.maintenance is not None and hub.status == Hub.Status.PREPARING and hub.ready_at is None
        else None
    )
    if hub.maintenance != maintenance:
        hub.maintenance = maintenance
        hub.save(update_fields=["maintenance", "updated_at"])
        record_event(ctx, events.BUSINESS_MAINTENANCE_CHANGED, {"id": str(hub.id), "maintenance": maintenance})
    return {"id": hub.id, "status": hub.status, "ready_at": hub.ready_at}


@operation(
    "hubs.business.record_scheduled_move",
    kind="command",
    permission="hubs.manage",
    input=HubScheduledMoveIn,
    output=HubStatusOut,
    ai=INTERNAL,
)
def business_record_scheduled_move(ctx: OperationContext, data: HubScheduledMoveIn) -> dict:
    """Persist when the Hub's move of the business, asked for its night, starts (or that none is ahead) and tell the
    owner's live pages; the same answer again records nothing. Not part of the snapshot: ``state_version`` stays."""
    hub = _system_hub(ctx, data)
    if hub.move_scheduled_for != data.move_scheduled_for:
        hub.move_scheduled_for = data.move_scheduled_for
        hub.save(update_fields=["move_scheduled_for", "updated_at"])
        at = None if data.move_scheduled_for is None else data.move_scheduled_for.isoformat()
        record_event(ctx, events.BUSINESS_MOVE_SCHEDULED_CHANGED, {"id": str(hub.id), "move_scheduled_for": at})
    return {"id": hub.id, "status": hub.status, "ready_at": hub.ready_at}
