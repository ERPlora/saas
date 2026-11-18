"""Schemas of the usage of a business: the last day its page carries, ``hubs.usage.*`` and what the Hub
sends each night."""

from datetime import date
from typing import Any
from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator


class StorageUsageOut(Schema):
    """What the business's files take (``used_bytes``, S3) against the space its plan includes
    (``limit_bytes``; ``None`` without a plan), and how full it is, rounded (``percent``, over 100 past it)."""

    used_bytes: int
    limit_bytes: int | None
    percent: int | None


class ActiveUsersOut(Schema):
    """The people active on the day measured (``on_day``) and in the 30 days up to it."""

    on_day: int
    last_30_days: int


class UsageOut(Schema):
    """The last day the Hub measured of a business; ``stale`` when it is not yesterday's (UTC)."""

    day: date
    storage: StorageUsageOut
    active_users: ActiveUsersOut
    stale: bool


#: The largest figures the columns of ``HubUsageDaily`` hold.
MAX_BYTES = 2**63 - 1
MAX_PEOPLE = 2**31 - 1
MAX_REQUESTS = 2**63 - 1
MAX_CONNECTIONS = 2**31 - 1


class UsageGetIn(Schema):
    business_id: UUID


class UsageSeriesIn(Schema):
    business_id: UUID
    #: The window: the days up to yesterday (UTC), from one to a year.
    days: int = Field(30, ge=1, le=365)


class UsagePointOut(Schema):
    """One day of the window (only the days measured: a chart draws the gaps)."""

    day: date
    storage: StorageUsageOut
    active_users: ActiveUsersOut


class UsageSeriesOut(Schema):
    """The days of the window, oldest first, against the space the plan includes today."""

    business_id: UUID
    limit_bytes: int | None
    points: list[UsagePointOut]


class HubUsageIn(Schema):
    """One business's usage on a day, as the Hub sends it (``GET /internal/usage``, ``hubs/README.md``).

    ``requests``, ``peak_connections`` and ``busy_requests`` are ``None`` when the Hub did not measure them, or does
    not send them yet: not measured is never a 0. A figure this schema does not know is ignored, so the Hub can add
    one before the SaaS reads it."""

    id: UUID
    s3_bytes: int = Field(ge=0, le=MAX_BYTES)
    db_bytes: int = Field(ge=0, le=MAX_BYTES)
    active_users_1d: int = Field(ge=0, le=MAX_PEOPLE)
    active_users_30d: int = Field(ge=0, le=MAX_PEOPLE)
    requests: int | None = Field(None, ge=0, le=MAX_REQUESTS)
    peak_connections: int | None = Field(None, ge=0, le=MAX_CONNECTIONS)
    busy_requests: int | None = Field(None, ge=0, le=MAX_REQUESTS)

    @model_validator(mode="after")
    def _one_day_within_its_thirty(self):
        if self.active_users_1d > self.active_users_30d:
            raise ValueError("active_users_1d is more than active_users_30d, which holds that day")
        return self


class HubUsagePageIn(Schema):
    """One page of ``GET /internal/usage``: each row is read on its own, so a broken one never drops the page."""

    day: date
    hubs: list[dict[str, Any]]
    #: Sent back as it came for the next page; ``None`` on the last.
    next_cursor: str | None = Field(None, min_length=1, max_length=512)


class UsageRecordIn(HubUsageIn):
    """The usage of the business ``id`` on ``day`` (the system command ``hubs.usage.record``)."""

    day: date


class UsageRecordOut(Schema):
    id: UUID
    day: date
    #: The figures were new or different (the owner and the admins were told).
    changed: bool


class UsagePruneIn(Schema):
    pass


class UsagePruneOut(Schema):
    #: The oldest day still kept: every day before it was forgotten.
    before: date
    #: How many days of usage were forgotten, of every business.
    deleted: int
