"""Schemas of what the platform records of the Hub about a business: ready, its last refusal, its
maintenance pause, the maintenance scheduled for its night and its status."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema


class HubMaintenanceOut(Schema):
    """The platform-wide provisioning pause reported by the Hub's signed status poll."""

    frozen: bool
    reason: str = Field(max_length=500)
    since: datetime | None


class MarkReadyIn(Schema):
    id: UUID


class HubErrorIn(Schema):
    """The Hub's refusal of a call about the business (its error code), or ``None`` once a call succeeds."""

    id: UUID
    hub_error: str | None = Field(None, max_length=64)


class HubMaintenanceIn(Schema):
    """The maintenance state read by the platform from the Hub, or ``None`` after it lifts."""

    id: UUID
    maintenance: HubMaintenanceOut | None = None


class HubScheduledMoveIn(Schema):
    """When the Hub's move of the business, asked for its night, starts; ``None`` without one."""

    id: UUID
    move_scheduled_for: datetime | None = None


class HubStatusOut(Schema):
    id: UUID
    status: str
    ready_at: datetime | None
