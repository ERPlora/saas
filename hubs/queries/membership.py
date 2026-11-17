"""The people of a business: its seats, its members and invitations, and who enters a hub."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy
from live.context import OperationContext
from live.operations import AI, INTERNAL, operation

from hubs.models import Hub, HubMember, HubOwnershipTransfer, Subscription
from hubs.queries.access_control import RANK, Role, access, account_of, is_writable
from hubs.queries.invitations import _name_of
from hubs.schemas import MemberListIn, MemberListMineIn, MemberListMineOut, MemberListOut


def seats_of(hub: Hub, now: datetime) -> dict[str, int | None]:
    """The seats of the business: ``used`` = its people, answered or invited (a live
    invitation holds its seat: it is spent when somebody is added, never when they walk in), and
    ``limit`` = what its plan covers at ``now``, ``None`` when nothing caps it (``max_users = 0`` on
    every paid plan and the Starter trial, or no subscription at all)."""
    used = (
        HubMember.objects.filter(hub=hub)
        .filter(
            Q(accepted_at__isnull=False)
            | Q(invitation_expires_at__isnull=True)
            | Q(invitation_expires_at__gt=now)
        )
        .count()
    )
    return {"used": used, "limit": seat_limit_of(hub, now)}


def seat_limit_of(hub: Hub, now: datetime) -> int | None:
    """The people the plan of ``hub`` covers at ``now``; ``None`` = unlimited."""
    subscription = (
        Subscription.objects.select_related("plan", "trial_plan")
        .filter(hub=hub)
        .first()
    )
    limit = subscription.effective_plan(now).max_users if subscription else 0
    return limit or None


def people_inside(hub: Hub) -> int:
    """The people who answered: those an acceptance must find a seat beside."""
    return HubMember.objects.filter(hub=hub, accepted_at__isnull=False).count()


def owner_id(hub_id: UUID) -> UUID | None:
    return (
        HubMember.objects.filter(hub_id=hub_id, role=Role.OWNER)
        .values_list("user_id", flat=True)
        .first()
    )


def people_to_tell(hub_id: UUID, also=()) -> list[UUID]:
    """Who sees the people of the business ``hub_id`` (its answered owner and admins) and the accounts in
    ``also`` (whom a change touched), each once: the channels ``services.people_notices.notify_people`` tells."""
    managers = HubMember.objects.filter(
        hub_id=hub_id, accepted_at__isnull=False, role__in=[Role.OWNER, Role.ADMIN]
    ).values_list("user_id", flat=True)
    return sorted(
        {*managers, *(user_id for user_id in also if user_id is not None)}, key=str
    )


def answered_business_ids(user_id: UUID) -> list[UUID]:
    """The businesses whose snapshot lists the account (its answered memberships), by id."""
    return list(
        HubMember.objects.filter(user_id=user_id, accepted_at__isnull=False)
        .order_by("hub_id")
        .values_list("hub_id", flat=True)
    )


def _who_enters():
    """The members who enter a hub: answered, on a business that still opens. A business being deleted lets nobody in
    (a restore gives the access back), whatever ``business_list`` shows its owner in its days of recovery."""
    return HubMember.objects.filter(accepted_at__isnull=False).exclude(
        hub__status__in=[Hub.Status.DELETING, Hub.Status.DELETED]
    )


def access_of(user_id) -> list[tuple[str, str]]:
    """``(slug, role)`` of every business the account ``user_id`` enters, by address."""
    return list(_who_enters().filter(user_id=user_id).order_by("hub__slug").values_list("hub__slug", "role"))


def hubs_with_members() -> list[tuple[str, int]]:
    """``(slug, people who enter)`` of every business somebody enters, by address: «Hubs» of the SaaS admin."""
    rows = _who_enters().values("hub__slug").annotate(members=Count("id")).order_by("hub__slug")
    return [(row["hub__slug"], row["members"]) for row in rows]


@operation(
    "hubs.member.list_mine",
    kind="query",
    permission="hubs.view",
    input=MemberListMineIn,
    output=MemberListMineOut,
    ai=INTERNAL,  # only ``accounts`` calls it
)
def member_list_mine(ctx: OperationContext, data: MemberListMineIn) -> dict[str, Any]:
    """The businesses the account enters with its role on each: what the jump to a hub reads. Called by its name
    from ``accounts`` (``accounts.queries.hub_roles_of``), which never imports ``hubs``; it has no route."""
    user = account_of(ctx)
    return {"rows": [{"slug": slug, "role": role} for slug, role in access_of(user.pk)]}


#: The roles an invitation or a role change may hand out, from the most authority to the least.
INVITABLE = [Role.ADMIN, Role.MANAGER, Role.EMPLOYEE]
MEMBER_STATUS_LABELS = {
    "active": gettext_lazy("Active"),
    "pending": gettext_lazy("Pending"),
    "expired": gettext_lazy("Expired"),
}


def assignable_roles(role: str) -> list[str]:
    """The roles ``role`` may hand out: strictly below its own, and only from admin up."""
    if RANK[role] > RANK[Role.ADMIN]:
        return []
    return [str(candidate) for candidate in INVITABLE if RANK[candidate] > RANK[role]]


def manages(actor: HubMember, target: HubMember) -> bool:
    """Whether ``actor`` may act on ``target``: an admin or the owner, never on itself nor on a peer
    or a superior; the hierarchy is per business."""
    return (
        target.user_id != actor.user_id
        and RANK[actor.role] <= RANK[Role.ADMIN]
        and RANK[target.role] > RANK[actor.role]
    )


def ranked(members):
    """``members`` with their ``rank``, the owner first."""
    return members.annotate(
        rank=Case(
            *[When(role=role, then=Value(rank)) for role, rank in RANK.items()],
            output_field=IntegerField(),
        )
    )


@operation(
    "hubs.member.list",
    kind="query",
    permission="hubs.view",
    input=MemberListIn,
    output=MemberListOut,
    expose_api=True,
    ai=AI(
        description="The people of one business and its pending invitations, with their roles; for its owner and "
                    "administrators.",
        asks={
            "en": ("who has access to the bar?", "show the people of my salon", "list the team and pending invites"),
            "es": ("¿quién tiene acceso al bar?", "¿quiénes están en la peluquería?", "enséñame el equipo del negocio"),
        },
    ),
)
def member_list(ctx: OperationContext, data: MemberListIn) -> dict[str, Any]:
    """The members page of a business (the Members tab), for its owner and its administrators: every member
    and invitation, the owner first, with the actions the account may take on each row."""
    actor = access(account_of(ctx), data.hub_id, Role.ADMIN)
    now = timezone.now()
    everyone = ranked(
        HubMember.objects.select_related("user", "invited_by").filter(
            hub_id=data.hub_id
        )
    ).order_by("rank", "joined_at", "id")
    total = everyone.count()
    page = everyone[data.offset : data.offset + data.limit]
    offered = HubOwnershipTransfer.objects.filter(
        hub_id=data.hub_id,
        status=HubOwnershipTransfer.Status.PENDING,
        expires_at__gt=now,
    ).exists()
    with translation.override(ctx.language):
        rows = [
            member_row(actor, member, now, transfer_pending=offered) for member in page
        ]
    return {
        "rows": rows,
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
        "seats": seats_of(actor.hub, now),
        "invitable_roles": assignable_roles(actor.role)
        if is_writable(actor.hub)
        else [],
    }


#: The row actions in the order the members page shows them.
MEMBER_ACTIONS = ("change_role", "remove", "resend", "cancel", "transfer")


def member_actions(
    actor: HubMember, member: HubMember, *, transfer_pending: bool = False
) -> list[str]:
    """What ``actor`` may do on ``member``'s row, in ``MEMBER_ACTIONS`` order: the
    same rules the writes apply (``services.member_management._managed``, ``services.ownership.ownership_transfer``), so the page never
    offers a button its door refuses. Nothing on one's own row, a peer, a superior or a deleted business."""
    if not is_writable(actor.hub):
        return []
    pending = member.accepted_at is None
    manageable = manages(actor, member)
    allowed = {
        "change_role": manageable,
        "remove": manageable and not pending,
        "resend": manageable and pending,
        "cancel": manageable and pending,
        "transfer": actor.role == Role.OWNER
        and member.user_id != actor.user_id
        and not pending
        and not transfer_pending,
    }
    return [action for action in MEMBER_ACTIONS if allowed[action]]


def member_row(
    actor: HubMember,
    member: HubMember,
    now: datetime,
    *,
    transfer_pending: bool = False,
) -> dict[str, Any]:
    """One row of the members page as ``actor`` sees it: ``is_me`` marks the account's own row, and
    ``actions`` lists what it may do on this one (``member_actions``)."""
    pending = member.accepted_at is None
    status = "expired" if member.is_expired(now) else "pending" if pending else "active"
    actions = member_actions(actor, member, transfer_pending=transfer_pending)
    return {
        "id": member.id,
        "user_id": member.user_id,
        "email": member.user.email,
        "name": member.user.get_full_name() or member.user.email,
        "role": member.role,
        "role_label": str(member.get_role_display()),
        "status": status,
        "status_label": str(MEMBER_STATUS_LABELS[status]),
        "invited_by": _name_of(member.invited_by),
        "invited_at": member.invited_at,
        "invitation_expires_at": member.invitation_expires_at,
        # An invitation has not joined anything yet: no date until it is answered.
        "joined_at": None if pending else member.joined_at,
        "accepted_at": member.accepted_at,
        "last_opened_at": member.last_opened_at,
        "is_me": member.user_id == actor.user_id,
        "actions": actions,
        "assignable_roles": assignable_roles(actor.role)
        if "change_role" in actions
        else [],
    }
