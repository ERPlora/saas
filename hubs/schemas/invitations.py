"""Schemas of the invitations waiting for an account's answer."""

from datetime import datetime
from uuid import UUID

from ninja import Schema

from hubs.schemas.common import HubRefOut, Role


class InvitationOut(Schema):
    """An invitation waiting for this account's answer."""

    id: UUID
    hub: HubRefOut
    role: Role
    role_label: str
    invited_by: str | None
    invited_at: datetime | None
    expires_at: datetime | None
    message: str


class InvitationListIn(Schema):
    pass


class InvitationListOut(Schema):
    invitations: list[InvitationOut]
