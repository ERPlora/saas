"""The owner and the admins of a business hear of a change of its authorisation, each on their own channel."""

from uuid import UUID

from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from fiscal import events
from fiscal.schemas import NotifyIn, NotifyOut
from hubs.queries import membership


# --- The owner and the admins of the business hear of it ----------------------------------------------


@operation(
    "fiscal.representation.notify",
    kind="command",
    permission="fiscal.manage",
    input=NotifyIn,
    output=NotifyOut,
    ai=INTERNAL,  # platform
)
def representation_notify(ctx: OperationContext, data: NotifyIn) -> dict:
    """A change of the business's authorisation, recorded on this context's channel so that account's page
    re-runs at once. Only the platform runs it, from ``tell_the_business``."""
    if ctx.actor != "system":
        raise PermissionDenied(
            _("Only the platform tells a business of its authorisation."),
            code="internal_command",
        )
    record_event(ctx, events.REPRESENTATION_CHANGED, {"hub_id": str(data.id)})
    return {"id": data.id}


def tell_the_business(ctx: OperationContext, hub_id: UUID) -> None:
    """Tell the owner and the admins of the business (who read its authorisation), each on its own channel,
    but the channel ``ctx`` already notifies. Called inside the command: nothing leaves if it rolls back."""
    for user_id in membership.people_to_tell(hub_id):
        scope = Scope("user", str(user_id))
        if scope != ctx.scope:
            representation_notify(system_context(scope), NotifyIn(id=hub_id))
