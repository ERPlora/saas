"""The refusals several commands of hubs share: a deleted business and a plan with no seat left."""

from django.utils.translation import gettext as _
from live.errors import Conflict


def business_deleted() -> Conflict:
    return Conflict(_("This business was deleted."), code="hubs.business_deleted")


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
