"""The inputs and outputs of whatsapp's operations (``services.py``, ``queries.py``) and of its doors.

The doors' bodies are the Hub's contract (``hub/apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con el SaaS»): the
same fields, codes and answers the Hub already sends and reads; nothing here renames them.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field


class IngestIn(Schema):
    payload: dict = Field(description="Meta's webhook as it arrived (its signature already checked).")


class IngestOut(Schema):
    hub_ids: list[UUID] = Field(description="The businesses something new was parked for.")
    template_hubs: list[UUID] = Field(
        default_factory=list, description="The businesses whose templates Meta changed and should be read again."
    )
    parked: int = 0
    statuses: int = 0
    verdicts: int = 0
    discarded: int = 0


class ClaimIn(Schema):
    hub_ids: list[UUID] | None = Field(None, description="Only these businesses; all when missing.")
    limit: int = Field(50, ge=1, le=500)


class ClaimedDelivery(Schema):
    id: UUID
    kind: Literal["message", "status"]
    revision: int
    received_at: datetime
    body: dict = Field(description="The door's body, ``hub`` included.")


class ClaimOut(Schema):
    deliveries: list[ClaimedDelivery]


class RecordIn(Schema):
    id: UUID
    revision: int = Field(ge=0)
    outcome: Literal["delivered", "retry", "refused", "drop"]
    error: str = Field("", max_length=300)


class RecordOut(Schema):
    outcome: str
