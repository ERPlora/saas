"""Entering a business: the start of the jump to its Hub."""

from django.utils import timezone
from django.utils.translation import gettext_lazy
from live.context import OperationContext
from live.errors import Conflict
from live.operations import INTERNAL, operation
from live.outbox import record_event

from accounts.queries import hub_start_url
from hubs import events
from hubs.models import Hub, HubMember
from hubs.queries import access_control
from hubs.schemas import BusinessOpenIn, BusinessOpenOut


#: Why a business does not open, by status (a business with a payment pending still opens).
NOT_OPENING = {
    Hub.Status.PREPARING: ("hubs.business_preparing", gettext_lazy("This business is still being prepared.")),
    Hub.Status.SUSPENDED: (
        "hubs.business_suspended",
        gettext_lazy("This business is suspended until its payment is settled."),
    ),
    Hub.Status.DELETING: ("hubs.business_deleted", gettext_lazy("This business was deleted.")),
}


@operation(
    "hubs.business.open",
    kind="command",
    permission="hubs.manage",
    input=BusinessOpenIn,
    output=BusinessOpenOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=INTERNAL,  # the panel's «Open» button
)
def business_open(ctx: OperationContext, data: BusinessOpenIn) -> dict:
    """«Open», for every role: the Hub's start of the jump, ``url``.

    No code is minted here: the Hub binds the jump to the browser with a ``state`` of its own,
    so it starts at its ``/auth/login?next=``, which bounces to ``/hub-login/``; that door mints the
    code (and asks for the second factor of an account that has one). This checks the member and the
    business, and remembers it as the last opened (the launcher lists it first). From the installed app
    (``shell``), the jump carries ``shell=1``: the app links the till to the hub a navigation with that mark
    reaches when it leaves erplora.com (``ERPlora/app`` ``hub_link.rs``).
    """
    member = access_control.access(access_control.account_of(ctx), data.id)
    hub = member.hub
    if hub.status in NOT_OPENING:
        code, message = NOT_OPENING[hub.status]
        raise Conflict(str(message), code=code)
    HubMember.objects.filter(pk=member.pk).update(last_opened_at=timezone.now())
    record_event(ctx, events.BUSINESS_OPENED, {"id": str(hub.id)})
    url = hub_start_url(hub.slug, data.next)
    return {"url": f"{url}&shell=1" if data.shell else url}
