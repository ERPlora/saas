"""Access to a business: who may read or change it, by the account's role, and what each role may do."""

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied, Unauthorized

from accounts.queries.hub_links import hub_origin
from hubs.models import Hub, HubMember


Role = HubMember.Role
RANK = HubMember.RANK


#: Statuses a business is listed with; ``deleted`` (purged) is gone for good.
LISTED = [status for status in Hub.Status.values if status != Hub.Status.DELETED]
#: Why «Open» does not work, by status: a business with a payment pending still opens.
OPEN_BLOCKED = {
    Hub.Status.PREPARING: "preparing",
    Hub.Status.SUSPENDED: "suspended",
    Hub.Status.DELETING: "deleting",
    Hub.Status.DELETED: "deleting",
}


def account_of(ctx: OperationContext):
    """The signed-in account running ``ctx``; a visitor without one is refused."""
    if ctx.actor is None or isinstance(ctx.actor, str):
        raise Unauthorized(_("Sign in to see your businesses."))
    return ctx.actor


def not_found() -> NotFound:
    return NotFound(_("This business does not exist or you have no access to it."))


def access(
    user, hub_id: UUID, minimum: str = Role.EMPLOYEE, *, lock: bool = False
) -> HubMember:
    """``user``'s answered membership of the business ``hub_id``, with its hub.

    No business, no membership or an unanswered invitation: 404 (nobody learns a business exists).
    A role below ``minimum``: 403. ``lock`` takes the hub's row first (commands), so two writes on one
    business never interleave.
    """
    if lock:
        hub = Hub.objects.select_for_update().filter(pk=hub_id).first()
        if hub is None:
            raise not_found()
    member = (
        HubMember.objects.select_related("hub", "hub__business_type", "user")
        .filter(hub_id=hub_id, user=user, accepted_at__isnull=False)
        .exclude(hub__status=Hub.Status.DELETED)
        .first()
    )
    if member is None:
        raise not_found()
    if RANK[member.role] > RANK[minimum]:
        raise PermissionDenied(_("Your role in this business does not allow it."))
    return member


def open_blocked_reason(hub: Hub) -> str | None:
    """Why "Open" does not work: a business being prepared whose registry the Hub refused is an error."""
    reason = OPEN_BLOCKED.get(hub.status)
    if reason == "preparing" and hub.last_hub_error:
        return "error"
    return reason


def maintenance_of(hub: Hub) -> dict[str, Any] | None:
    """The Hub's provisioning pause of a sign-up still being prepared, else ``None``: a business deleted while paused
    keeps the stored pause (only the poll of a preparing one clears it), and its pill says its own state."""
    return hub.maintenance if hub.status == Hub.Status.PREPARING and hub.ready_at is None else None


def is_writable(hub: Hub) -> bool:
    """Whether the business takes changes: a deleted one answers every write with 409 until recovered."""
    return hub.status not in (Hub.Status.DELETING, Hub.Status.DELETED)


def is_restorable(hub: Hub, now: datetime) -> bool:
    """Deleted and still within its 90 days (``hubs.business.restore``)."""
    return (
        hub.status == Hub.Status.DELETING
        and hub.purge_after is not None
        and hub.purge_after > now
    )


def can(member: HubMember, now: datetime | None = None) -> dict[str, bool]:
    """What ``member`` may do on its business, by role and status, computed here so no page
    deduces it: the owner everything, an admin the team and the settings, a manager or an employee only
    «Open». «Open» while it serves; a deleted business takes no change, only «Recover» by its owner."""
    hub = member.hub
    now = now or timezone.now()
    is_owner = member.role == Role.OWNER
    manages_it = RANK[member.role] <= RANK[Role.ADMIN] and is_writable(hub)
    return {
        "open": hub.status not in OPEN_BLOCKED,
        "manage": manages_it,
        "manage_members": manages_it,
        "manage_settings": manages_it,
        "manage_billing": is_owner,
        "transfer": is_owner and is_writable(hub),
        "restore": is_owner and is_restorable(hub, now),
        "delete": is_owner and is_writable(hub),
        "change_address": is_owner and is_writable(hub),
        "download_data": is_owner,
    }


#: What a row of the Businesses page says its buttons do (``BusinessRowCanOut``).
ROW_CAN = ("open", "manage", "restore", "delete")


def host_of(slug: str) -> str:
    """``<slug>.erplora.com`` (locally ``<slug>.localhost:8000``)."""
    return urlsplit(hub_origin(slug)).netloc


def status_label(status: str) -> str:
    return str(Hub.Status(status).label)
