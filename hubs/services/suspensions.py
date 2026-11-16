"""The clock of a suspended business (HUBS-F20): its notices and its deletion."""

import logging
from collections import Counter
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import PermissionDenied
from live.operations import INTERNAL, operation

from hubs import emails
from hubs.models import Hub, HubMember
from hubs.queries.access_control import Role
from hubs.schemas import ByIdIn, SuspensionStepOut
from hubs.services.deletion import _delete_business
from hubs.services.hub_callbacks import system_ctx_for

logger = logging.getLogger(__name__)


#: Days after the suspension of an unpaid plan: the first notice, the last one, and the deletion.
SUSPENDED_WARN_DAYS = 30
SUSPENDED_FINAL_NOTICE_DAYS = 150
SUSPENDED_DELETE_DAYS = 180

#: What a pass of the clock counts (``billing.services.sweep_unpaid`` adds them to its own).
AGE_COUNTS = ("warned", "final_notice", "expired", "undated", "mail_failed", "errors")


def age_suspended() -> Counter:
    """One pass of the clock over every suspended business (HUBS-F20), each in its own transaction: one that
    fails is logged and counted, never stops the others. Run hourly by ``billing.services.sweep_unpaid``."""
    counts = Counter({key: 0 for key in AGE_COUNTS})
    suspended = Hub.objects.filter(status=Hub.Status.SUSPENDED).order_by("pk").values_list("pk", flat=True)
    for hub_id in list(suspended):
        try:
            outcome = business_age_suspension(system_ctx_for(hub_id), ByIdIn(id=hub_id)).outcome
        except Exception:  # noqa: BLE001 - one business never stops the pass; it is retried on the next one
            logger.exception("hubs.suspension.failed hub=%s", hub_id)
            counts["errors"] += 1
            continue
        if outcome:
            counts[outcome] += 1
    return counts


@operation(
    "hubs.business.age_suspension",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=SuspensionStepOut,
    ai=INTERNAL,  # only the hourly pass runs it
)
def business_age_suspension(ctx: OperationContext, data: ByIdIn) -> dict:
    """The step of the clock that is due for one suspended business (HUBS-F20), platform only: the first notice
    (day 30), the last one (day 150, also when a late pass finds both due), or the deletion (day 180, only after
    the last notice went out), each once. A notice is marked sent only if its mail left (a failed one goes again
    on the next pass). A suspension nobody dated is never deleted: it is logged for a person."""
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform ages a suspension."), code="internal_command")
    hub = Hub.objects.select_for_update().filter(pk=data.id, status=Hub.Status.SUSPENDED).first()
    if hub is None:
        return {"id": data.id, "outcome": ""}
    if hub.suspended_at is None:
        logger.error("hubs.suspension.undated hub=%s: a person has to look at it", hub.id)
        return {"id": hub.id, "outcome": "undated"}
    now = timezone.now()
    days = (now - hub.suspended_at).days
    owner = HubMember.objects.select_related("user").filter(hub=hub, role=Role.OWNER).first()
    delete_on = hub.suspended_at + timedelta(days=SUSPENDED_DELETE_DAYS)
    base_url = emails.base_url(None)
    if days >= SUSPENDED_DELETE_DAYS and hub.suspension_final_notice_at is not None:
        _delete_business(ctx, hub, owner.user if owner else None, base_url=base_url, unpaid=True)
        logger.info("hubs.suspension.expired hub=%s", hub.id)
        return {"id": hub.id, "outcome": "expired"}
    if days >= SUSPENDED_FINAL_NOTICE_DAYS and hub.suspension_final_notice_at is None:
        field, outcome, final = "suspension_final_notice_at", "final_notice", True
    elif days >= SUSPENDED_WARN_DAYS and hub.suspension_warned_at is None and hub.suspension_final_notice_at is None:
        field, outcome, final = "suspension_warned_at", "warned", False
    else:
        return {"id": hub.id, "outcome": ""}
    if owner is None or not emails.send_suspension_notice(
        hub, owner.user, base_url=base_url, delete_on=delete_on, final=final
    ):
        return {"id": hub.id, "outcome": "mail_failed"}
    Hub.objects.filter(pk=hub.pk).update(**{field: now})
    return {"id": hub.id, "outcome": outcome}
