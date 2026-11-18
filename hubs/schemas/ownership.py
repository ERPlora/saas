"""Schemas of the hand-over of a business to another of its members."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema

from hubs.schemas.common import HubRefOut


class OwnershipOfferOut(Schema):
    """A business offered to this account (an ownership transfer waiting for its answer)."""

    id: UUID
    hub: HubRefOut
    from_email: str
    expires_at: datetime


class TransferRefOut(Schema):
    id: UUID
    to_email: str
    expires_at: datetime


class OwnershipTransferIn(Schema):
    hub_id: UUID
    #: The member the business is offered to (already on it).
    member_id: UUID


class OwnershipTransferOut(Schema):
    id: UUID
    hub: HubRefOut
    from_email: str
    to_email: str
    status: Literal["pending", "accepted", "declined", "cancelled", "expired"]
    expires_at: datetime
    resolved_at: datetime | None
