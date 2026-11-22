"""Schemas of the members of a business: the list, an invitation sent, a role changed, and the notice of
a change of its people."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from hubs.schemas.common import Email, InvitableRole, Page, PageIn, Role


class SeatsOut(Schema):
    """People on the business (members and live invitations) and what its plan covers."""

    used: int
    #: ``None`` = unlimited (every paid plan, the Starter trial, no subscription).
    limit: int | None


class NotifyPeopleIn(Schema):
    """A change of the people of the business ``id``, told on the context's channel (a system command)."""

    id: UUID
    event: Literal["hubs.member.changed", "hubs.ownership.changed", "hubs.business.usage_collected"]


class NotifyPeopleOut(Schema):
    id: UUID


class MemberListIn(PageIn):
    hub_id: UUID


#: What the account may do on a row of the members page.
MemberAction = Literal["change_role", "remove", "resend", "cancel", "transfer"]


class MemberRowOut(Schema):
    id: UUID
    user_id: UUID
    email: str
    name: str
    role: Role
    role_label: str
    #: ``active`` (answered), ``pending`` (invited) or ``expired`` (invited, past its window).
    status: Literal["active", "pending", "expired"]
    status_label: str
    invited_by: str | None
    invited_at: datetime | None
    invitation_expires_at: datetime | None
    #: None while the invitation waits for its answer.
    joined_at: datetime | None
    accepted_at: datetime | None
    last_opened_at: datetime | None
    #: The account's own row.
    is_me: bool
    #: What the account may do on this row, computed by the server, in this order: ``change_role``,
    #: ``remove`` (answered), ``resend`` and ``cancel`` (invitation), ``transfer`` (owner only, while no
    #: offer waits). Empty on one's own row, a peer, a superior and a deleted business.
    actions: list[MemberAction]
    #: The roles the account may give this member (empty without ``change_role``).
    assignable_roles: list[InvitableRole]


class MemberListOut(Page[MemberRowOut]):
    seats: SeatsOut
    #: The roles that take no seat of the plan: an invitation with one goes through with every seat taken.
    free_roles: list[InvitableRole]
    #: The roles the account may invite with.
    invitable_roles: list[InvitableRole]


class MemberListMineIn(Schema):
    """Nothing to ask: the account is the caller's."""


class MemberMineOut(Schema):
    slug: str
    role: Role


class MemberListMineOut(Schema):
    #: The businesses the account enters, by address.
    rows: list[MemberMineOut]


class MemberInviteIn(Schema):
    hub_id: UUID
    email: Email
    role: InvitableRole = "hub_employee"
    message: str = Field("", max_length=500)


class MemberRoleIn(Schema):
    id: UUID
    role: InvitableRole


class RemovedOut(Schema):
    id: UUID
