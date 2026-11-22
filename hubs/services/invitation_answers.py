"""The invited account's answer to an invitation: accepting it, within the plan's seats, or declining it."""

from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import AI, operation
from live.outbox import record_event

from accounts.queries import ways_in
from hubs import events
from hubs.models import Hub, HubMember
from hubs.queries import access_control, businesses, membership, signup
from hubs.schemas.businesses import BusinessRowOut
from hubs.schemas.common import ByIdIn
from hubs.schemas.membership import RemovedOut
from hubs.services.hub_push import bump_state, push_after_commit
from hubs.services.people_notices import notify_people
from hubs.services.refusals import SeatLimitReached


def _check_seat_to_enter(member: HubMember, now) -> None:
    """The plan still has a seat beside the people already inside: an invitation sent while nothing
    capped it (the Starter trial) and answered once the plan covers fewer people is first come, first
    served. Within the cap it always passes, because the invitation already holds its seat; a role that
    takes no seat always enters."""
    if not membership.takes_seat(member.role):
        return
    hub = member.hub
    limit = membership.seat_limit_of(hub, now)
    if limit is not None and membership.people_inside(hub) >= limit:
        raise SeatLimitReached(
            _("This business has no seat left on its plan. Ask whoever invited you to free one or to change the plan."),
            limit=limit,
            used=membership.seats_of(hub, now)["used"],
        )


def _my_invitation(ctx: OperationContext, member_id: UUID) -> HubMember:
    """The account's own unanswered invitation ``member_id``, locked after its hub; 404 otherwise.

    The security boundary of answering: nothing that is not the caller's own pending row can be
    reached, so no poked id, replay or foreign invitation grants anything.
    """
    user = access_control.account_of(ctx)
    hub_id = (
        HubMember.objects.filter(pk=member_id, user=user, accepted_at__isnull=True).values_list("hub_id", flat=True).first()
    )
    hub = Hub.objects.select_for_update().filter(pk=hub_id).first() if hub_id else None
    member = (
        HubMember.objects.select_for_update().filter(pk=member_id, user=user, accepted_at__isnull=True).first()
        if hub is not None and hub.status not in (Hub.Status.DELETING, Hub.Status.DELETED)
        else None
    )
    if member is None:
        raise NotFound(_("This invitation does not exist or is no longer yours to answer."))
    member.hub = hub
    return member


@operation(
    "hubs.invitation.accept",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=BusinessRowOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Accepts an invitation of this account to a business, within its 7 days.",
        asks={
            "en": ("accept the invitation from Bar Manolo", "yes, I'll join the salon's team", "accept Marta's invite"),
            "es": (
                "acepta la invitación del Bar Manolo",
                "vale, me uno al equipo de la peluquería",
                "acepto la invitación de Marta",
            ),
        },
    ),
)
def invitation_accept(ctx: OperationContext, data: ByIdIn) -> dict:
    """Accept an invitation within its 7 days: the account enters with the role it says, if the plan
    still has a seat beside the people already inside (``_check_seat_to_enter``). An account that never
    proved its address confirms it first (403 ``hubs.email_unverified``)."""
    member = _my_invitation(ctx, data.id)
    signup.refuse_staff(member.user)
    if not ways_in.email_is_proven(member.user, member.user.email):
        raise PermissionDenied(
            _("Confirm your email address before accepting the invitation."), code="hubs.email_unverified"
        )
    now = timezone.now()
    if member.is_expired(now):
        raise Conflict(
            _("This invitation expired. Ask whoever invited you to send it again."), code="hubs.invitation_expired"
        )
    _check_seat_to_enter(member, now)
    member.accepted_at = now
    member.save(update_fields=["accepted_at"])
    bump_state(member.hub_id)
    record_event(ctx, events.INVITATION_ACCEPTED, {"id": str(member.id), "hub_id": str(member.hub_id)})
    notify_people(ctx, events.MEMBER_CHANGED, member.hub_id)
    push_after_commit(member.hub_id)
    return businesses.business_row(member, now)


@operation(
    "hubs.invitation.decline",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=RemovedOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Declines an invitation of this account to a business.",
        asks={
            "en": (
                "decline the invitation from the café",
                "I don't want to join that business",
                "reject Marta's invite",
            ),
            "es": (
                "rechaza la invitación del café",
                "no quiero unirme a ese negocio",
                "dile que no a la invitación de Marta",
            ),
        },
    ),
)
def invitation_decline(ctx: OperationContext, data: ByIdIn) -> dict:
    """Decline an invitation: the row goes."""
    member = _my_invitation(ctx, data.id)
    member.delete()
    record_event(ctx, events.INVITATION_DECLINED, {"id": str(data.id), "hub_id": str(member.hub_id)})
    notify_people(ctx, events.MEMBER_CHANGED, member.hub_id)
    return {"id": data.id}
