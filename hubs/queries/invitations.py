"""The invitations and ownership offers waiting for an account's answer."""

from datetime import datetime
from typing import Any

from django.db.models import Q
from django.utils import timezone, translation
from live.context import OperationContext
from live.operations import AI, operation

from hubs.models import Hub, HubMember, HubOwnershipTransfer
from hubs.queries.access_control import LISTED, account_of
from hubs.schemas import InvitationListIn, InvitationListOut


def _waiting_invitations(now: datetime):
    """The invitations waiting for an answer: not answered, not expired, business not deleted."""
    return HubMember.objects.filter(
        accepted_at__isnull=True,
        hub__status__in=[s for s in LISTED if s != Hub.Status.DELETING],
    ).filter(Q(invitation_expires_at__isnull=True) | Q(invitation_expires_at__gt=now))


def invitations_of(user, now: datetime) -> list[dict[str, Any]]:
    """The invitations waiting for ``user``'s answer (``_waiting_invitations``)."""
    pending = (
        _waiting_invitations(now)
        .select_related("hub", "invited_by")
        .filter(user=user)
        .order_by("invited_at", "id")
    )
    return [
        {
            "id": member.id,
            "hub": {
                "id": member.hub.id,
                "slug": member.hub.slug,
                "name": member.hub.name,
            },
            "role": member.role,
            "role_label": str(member.get_role_display()),
            "invited_by": _name_of(member.invited_by),
            "invited_at": member.invited_at,
            "expires_at": member.invitation_expires_at,
            "message": member.invitation_message,
        }
        for member in pending
    ]


def ownership_offers_of(user, now: datetime) -> list[dict[str, Any]]:
    """The businesses offered to ``user``, waiting for its answer (an expired offer is not live)."""
    offers = (
        HubOwnershipTransfer.objects.select_related("hub")
        .filter(
            to_user=user, status=HubOwnershipTransfer.Status.PENDING, expires_at__gt=now
        )
        .order_by("-created_at")
    )
    return [
        {
            "id": offer.id,
            "hub": {"id": offer.hub.id, "slug": offer.hub.slug, "name": offer.hub.name},
            "from_email": offer.from_email,
            "expires_at": offer.expires_at,
        }
        for offer in offers
    ]


def _name_of(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.email


@operation(
    "hubs.invitation.list_mine",
    kind="query",
    permission="hubs.view",
    input=InvitationListIn,
    output=InvitationListOut,
    ai=AI(
        description="The invitations to businesses waiting for this account's answer.",
        asks={
            "en": ("do I have any invitations?", "who invited me?", "pending invites for me"),
            "es": (
                "¿tengo invitaciones pendientes?",
                "¿alguien me ha invitado a su negocio?",
                "¿quién me ha invitado?",
            ),
        },
    ),
)
def invitation_list_mine(
    ctx: OperationContext, data: InvitationListIn
) -> dict[str, Any]:
    """The invitations waiting for the account's answer (the invitation page)."""
    user = account_of(ctx)
    with translation.override(ctx.language):
        return {"invitations": invitations_of(user, timezone.now())}
