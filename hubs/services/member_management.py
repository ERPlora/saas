"""The people of a business as its managers change them: invitations, roles and removals."""

from functools import partial
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import AI, operation
from live.outbox import record_event

from accounts import queries as account_queries
from accounts.services import mailbox_proof
from hubs import emails, events
from hubs.models import Hub, HubMember, HubOwnershipTransfer
from hubs.queries import access_control, membership, payers, signup
from hubs.queries.access_control import Role
from hubs.schemas.common import ByIdIn
from hubs.schemas.membership import MemberInviteIn, MemberRoleIn, MemberRowOut, RemovedOut
from hubs.services.hub_push import bump_state, push_after_commit
from hubs.services.people_notices import notify_people
from hubs.services.refusals import SeatLimitReached, business_deleted
from hubs.services.session_revocations import revoke_after_commit


def _member_not_found() -> NotFound:
    return NotFound(_("This member does not exist or you have no access to it."))


def _managed(ctx: OperationContext, member_id: UUID, role: str | None = None) -> tuple[HubMember, HubMember]:
    """``(actor, target)`` for a write on the member ``member_id``, both locked after their hub's row.

    The actor must be an admin or the owner of the target's business (404 otherwise, 403 below
    admin), never act on itself nor on a peer or a superior, and never hand out its own rank or more.
    """
    user = access_control.account_of(ctx)
    hub_id = HubMember.objects.filter(pk=member_id).values_list("hub_id", flat=True).first()
    if hub_id is None:
        raise _member_not_found()
    actor = access_control.access(user, hub_id, Role.ADMIN, lock=True)
    if actor.hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    target = (
        HubMember.objects.select_for_update(of=("self",))
        .select_related("hub", "user", "invited_by")
        .filter(pk=member_id)
        .first()
    )
    if target is None:
        raise _member_not_found()
    if target.user_id == actor.user_id:
        raise PermissionDenied(_("You cannot change your own membership."), code="hubs.own_membership")
    if not membership.manages(actor, target):
        raise PermissionDenied(_("You cannot manage a member whose role is equal to or above yours."))
    if role is not None and role not in membership.assignable_roles(actor.role):
        raise PermissionDenied(_("You cannot hand out a role equal to or above yours."))
    return actor, target


def _check_seat(hub: Hub, now) -> None:
    """The plan covers one more person, checked where the seat is spent: inviting (a live invitation holds
    its seat), and renewing an invitation that had expired."""
    seats = membership.seats_of(hub, now)
    if seats["limit"] is not None and seats["used"] >= seats["limit"]:
        raise SeatLimitReached(
            _("This plan covers %(cap)s people and they are all taken.") % {"cap": seats["limit"]},
            limit=seats["limit"],
            used=seats["used"],
        )


def _renew(member: HubMember, inviter, now) -> None:
    member.invited_by = inviter
    member.invited_at = now
    member.invitation_expires_at = now + HubMember.INVITATION_WINDOW
    member.save(update_fields=["invited_by", "invited_at", "invitation_expires_at"])


def _mail_invitation(ctx: OperationContext, member: HubMember) -> None:
    # Somebody with no way in yet (a new account, or one released below) is told how to claim it.
    new_account = account_queries.has_no_way_in(member.user)
    transaction.on_commit(
        partial(emails.send_invitation, member, base_url=emails.base_url(ctx.request), new_account=new_account),
        robust=True,
    )


@operation(
    "hubs.member.invite",
    kind="command",
    permission="hubs.manage",
    input=MemberInviteIn,
    output=MemberRowOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Invites a person by email to a business with a role below one's own; the invitation lasts 7 days.",
        asks={
            "en": (
                "invite perito@correo.com to the salon",
                "add marta@gmail.com to my team as manager",
                "send an invite to luis@gmail.com",
            ),
            "es": (
                "invita a perito@correo.com a la peluquería",
                "añade a marta@gmail.com al equipo como encargada",
                "manda una invitación a luis@gmail.com",
            ),
        },
    ),
)
def member_invite(ctx: OperationContext, data: MemberInviteIn) -> dict:
    """Invite somebody to the business with a role below one's own.

    The invitation is a member without an answer, valid for 7 days; an address without an account gets
    one to claim (no password: Google or «Forgot your password?»). An account that never proved the
    address is released first (``accounts.services.mailbox_proof.release_unproven_account``): whoever opens the mailbox
    claims it, and its sessions in every business end. The plan must have a seat for one
    more person. It reaches the Hub only once answered. An expired invitation is renewed.
    """
    actor = access_control.access(access_control.account_of(ctx), data.hub_id, Role.ADMIN, lock=True)
    hub = actor.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    if data.role not in membership.assignable_roles(actor.role):
        raise PermissionDenied(_("You cannot hand out a role equal to or above yours."))
    now = timezone.now()
    member = HubMember.objects.select_for_update().select_related("user").filter(hub=hub, user__email__iexact=data.email).first()
    if member is not None:
        member.hub = hub
        if not member.is_pending:
            raise Conflict(_("%(email)s is already on this business.") % {"email": data.email}, code="hubs.already_member")
        if not member.is_expired(now):
            raise Conflict(
                _("%(email)s already has an invitation waiting. Resend it instead.") % {"email": data.email},
                code="hubs.already_invited",
            )
        if not membership.manages(actor, member):
            raise PermissionDenied(_("You cannot manage a member whose role is equal to or above yours."))
        signup.refuse_staff(member.user)
        _check_seat(hub, now)
        member.role = data.role
        member.invitation_message = data.message
        member.save(update_fields=["role", "invitation_message"])
        _renew(member, actor.user, now)
    else:
        _check_seat(hub, now)
        user = get_user_model().objects.filter(email__iexact=data.email).first()
        if user is None:
            user = get_user_model().objects.create_user(email=data.email, password=None, language=hub.language)
        else:
            signup.refuse_staff(user)
            if not account_queries.email_is_proven(user, data.email):
                mailbox_proof.release_unproven_account(user, reason="invited_while_unverified")
                revoke_after_commit(user.pk)
        member = HubMember.objects.create(
            hub=hub,
            user=user,
            role=data.role,
            invited_by=actor.user,
            invitation_message=data.message,
            invited_at=now,
            invitation_expires_at=now + HubMember.INVITATION_WINDOW,
            joined_at=now,
        )
    record_event(ctx, events.MEMBER_INVITED, {"id": str(member.id), "hub_id": str(hub.id)})
    notify_people(ctx, events.MEMBER_CHANGED, hub.id, member.user_id)
    _mail_invitation(ctx, member)
    return membership.member_row(actor, member, now)


@operation(
    "hubs.member.change_role",
    kind="command",
    permission="hubs.manage",
    input=MemberRoleIn,
    output=MemberRowOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Gives a member or a pending invitation of a business another role below one's own.",
        asks={
            "en": ("make Marta an admin", "change Luis's role to employee", "give Ana manager rights at the salon"),
            "es": ("cámbiale el rol a Marta", "haz a Luis encargado", "pon a Ana de administradora en la peluquería"),
        },
    ),
)
def member_change_role(ctx: OperationContext, data: MemberRoleIn) -> dict:
    """Give a member (or an invitation) another role below one's own; never the owner's."""
    actor, target = _managed(ctx, data.id, data.role)
    if target.role != data.role:
        target.role = data.role
        target.save(update_fields=["role"])
        if not target.is_pending:
            bump_state(target.hub_id)
            push_after_commit(target.hub_id)
            # The role travels in the Hub's session (``/internal/auth/redeem``): it signs in again with the new one.
            revoke_after_commit(target.user_id, target.hub_id)
        record_event(ctx, events.MEMBER_ROLE_CHANGED, {"id": str(target.id), "hub_id": str(target.hub_id)})
        notify_people(ctx, events.MEMBER_CHANGED, target.hub_id, target.user_id)
    return membership.member_row(actor, target, timezone.now())


@operation(
    "hubs.member.remove",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=RemovedOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Takes a person out of one business: their access to it ends; their account and other businesses "
                    "stay.",
        asks={
            "en": (
                "remove Luis from the bar",
                "Marta no longer works here, take her out",
                "revoke Ana's access to the salon",
            ),
            "es": ("quita a Luis del bar", "Marta ya no trabaja aquí, sácala", "quítale el acceso a Ana"),
        },
    ),
)
def member_remove(ctx: OperationContext, data: ByIdIn) -> dict:
    """Take somebody out of this business only (their other businesses and account stay): their
    access ends, the Hub learns it in the next snapshot and ends their sessions there."""
    _actor, target = _managed(ctx, data.id)
    if target.is_pending:
        raise Conflict(_("This person has not answered yet: cancel the invitation."), code="hubs.member_pending")
    _refuse_a_payer(target)
    hub = target.hub
    _take_out(target)
    record_event(ctx, events.MEMBER_REMOVED, {"id": str(data.id), "hub_id": str(hub.id)})
    notify_people(ctx, events.MEMBER_CHANGED, hub.id, target.user_id)
    revoke_after_commit(target.user_id, hub.id)
    return {"id": data.id}


def _refuse_a_payer(target: HubMember) -> None:
    """Whoever still pays for the business (the owner before a hand-over, ``payers.still_pays``) stays in it
    until the business is paid otherwise; out of it, it would pay for a business it no longer sees."""
    if not payers.still_pays(target):
        return
    name = target.user.get_full_name() or target.user.email
    if payers.is_payer(target):
        message = _(
            "%(name)s still pays for this business. Say who pays from now on first: your billing details are asked "
            "when you pay a plan or a module here."
        ) % {"name": name}
    else:
        message = _(
            "This business's plan is still paid with %(name)s's card: keep it with yours in Billing first."
        ) % {"name": name}
    raise Conflict(message, code="hubs.member_pays")


def _take_out(member: HubMember) -> None:
    """Take ``member`` out of its business (removed, or its account deleted): an ownership offer pending to it is
    cancelled, its access goes with its row and, once it had answered, the Hub gets a snapshot without it after the
    COMMIT."""
    hub = member.hub
    HubOwnershipTransfer.objects.filter(
        hub=hub, to_user_id=member.user_id, status=HubOwnershipTransfer.Status.PENDING
    ).update(status=HubOwnershipTransfer.Status.CANCELLED, resolved_at=timezone.now())
    member.delete()
    if member.accepted_at is not None:
        bump_state(hub.id)
        push_after_commit(hub.id)


def _pending_only(target: HubMember) -> None:
    if not target.is_pending:
        raise Conflict(_("This person already answered the invitation."), code="hubs.member_not_pending")


@operation(
    "hubs.member.resend",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=MemberRowOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Sends a pending invitation to a business again, valid for 7 more days.",
        asks={
            "en": (
                "resend the invitation to Marta",
                "Luis didn't get the invite, send it again",
                "send the invite again",
            ),
            "es": (
                "reenvía la invitación a Marta",
                "a Luis no le llegó la invitación, mándasela otra vez",
                "vuelve a mandar la invitación a perito@correo.com",
            ),
        },
    ),
)
def member_resend(ctx: OperationContext, data: ByIdIn) -> dict:
    """Send the invitation again: it gets 7 more days."""
    actor, target = _managed(ctx, data.id)
    _pending_only(target)
    signup.refuse_staff(target.user)
    now = timezone.now()
    if target.is_expired(now):
        _check_seat(target.hub, now)
    _renew(target, actor.user, now)
    record_event(ctx, events.MEMBER_INVITATION_RESENT, {"id": str(target.id), "hub_id": str(target.hub_id)})
    notify_people(ctx, events.MEMBER_CHANGED, target.hub_id, target.user_id)
    _mail_invitation(ctx, target)
    return membership.member_row(actor, target, now)


@operation(
    "hubs.member.cancel",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=RemovedOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Withdraws an invitation to a business nobody answered yet.",
        asks={
            "en": ("cancel the invitation to perito@correo.com", "withdraw Luis's invite", "never mind inviting Marta"),
            "es": (
                "cancela la invitación de perito@correo.com",
                "retira la invitación a Luis",
                "al final no invites a Marta",
            ),
        },
    ),
)
def member_cancel(ctx: OperationContext, data: ByIdIn) -> dict:
    """Withdraw an invitation nobody answered: the row goes."""
    _actor, target = _managed(ctx, data.id)
    _pending_only(target)
    target.delete()
    record_event(ctx, events.MEMBER_INVITATION_CANCELLED, {"id": str(data.id), "hub_id": str(target.hub_id)})
    notify_people(ctx, events.MEMBER_CHANGED, target.hub_id, target.user_id)
    return {"id": data.id}
