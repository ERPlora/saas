"""The refusals several commands of hubs share: a deleted business, ERPlora's own and a plan with no seat left."""

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.errors import Conflict

from hubs.models import Hub
from hubs.queries import access_control

PLATFORM_BUSINESS = gettext_lazy(
    "ERPlora's own business has no plan or payments, and it cannot be changed, deleted or recovered here."
)


def business_deleted() -> Conflict:
    return Conflict(_("This business was deleted."), code="hubs.business_deleted")


def refuse_platform_business(hub: Hub) -> None:
    """409 ``hubs.platform_business`` for ERPlora's own business: erplora.com keeps it only for its people."""
    if hub.is_platform:
        raise Conflict(str(PLATFORM_BUSINESS), code="hubs.platform_business")


def refuse_to_change(hub: Hub) -> None:
    """409 for a business that takes no change nor payment: ERPlora's own or a deleted one."""
    refuse_platform_business(hub)
    if not access_control.is_writable(hub):
        raise business_deleted()


class SeatLimitReached(Conflict):
    """409 ``hubs.seat_limit``: the plan has no seat for one more person.

    Its envelope also says how many people the plan covers (``limit``) and how many seats are taken
    (``used``, as ``hubs.member.list`` counts them), so the panel offers the plan change with the
    numbers instead of parsing the message.
    """

    def __init__(self, message: str, *, limit: int, used: int) -> None:
        super().__init__(message, code="hubs.seat_limit")
        self.limit = limit
        self.used = used

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"].update(limit=self.limit, used=self.used)
        return envelope
