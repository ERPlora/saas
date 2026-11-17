"""Telling the owner, the admins and the accounts concerned of a change of the people of a business."""

from uuid import UUID

from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from hubs.queries import membership
from hubs.schemas import NotifyPeopleIn, NotifyPeopleOut


@operation(
    "hubs.business.notify_people",
    kind="command",
    permission="hubs.manage",
    input=NotifyPeopleIn,
    output=NotifyPeopleOut,
    ai=INTERNAL,  # only the platform runs it
)
def business_notify_people(ctx: OperationContext, data: NotifyPeopleIn) -> dict:
    """A change of the people of the business, recorded on this context's channel, so the lists of that
    account re-run at once (``events.PEOPLE``). Only the platform runs it, from ``notify_people``."""
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform tells the people of a business."), code="internal_command")
    record_event(ctx, data.event, {"business_id": str(data.id)})
    return {"id": data.id}


def notify_people(ctx: OperationContext, event: str, hub_id: UUID, *also) -> None:
    """Tell the owner, the admins and the accounts in ``also`` of a change of the business's people, each on
    its own channel (``hubs.business.notify_people``), but the actor, whose own event already re-runs its
    lists. Called inside the command: it leaves after the COMMIT, and nothing leaves if it rolls back."""
    actor = getattr(ctx.actor, "pk", None)
    for user_id in membership.people_to_tell(hub_id, also):
        if user_id != actor:
            business_notify_people(system_context(Scope("user", str(user_id))), NotifyPeopleIn(id=hub_id, event=event))
