"""The inputs and outputs of whatsapp's operations (``services.py``, ``queries.py``) and of its doors.

The doors' bodies are the Hub's contract (``hub/apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con el SaaS»): the
same fields, codes and answers the Hub already sends and reads; nothing here renames them.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field, SecretStr, StringConstraints, model_validator

#: The Hub's ``hub``: the business's slug in phase 1 (its UUID in phase 2).
HubRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
#: An international number, with or without ``+`` (the Hub's ``INTERNATIONAL``).
International = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[1-9]\d{6,14}$")]
#: The ``Idempotency-Key`` of a send (the Hub's ``client_message_id``) or of a template's registration.
IdempotencyKey = Annotated[str, StringConstraints(min_length=1, max_length=255)]


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


# --- Door 5: send ---------------------------------------------------------------------------------------------


class TemplateRef(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
    language: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16)] = "es"
    variables: list[Annotated[str, StringConstraints(max_length=1024)]] = Field(default_factory=list, max_length=100)


class SendIn(Schema):
    """Door 5's body: ``{"hub", "to", "type": "text", "text"}`` or ``{"hub", "to", "type": "template", "template"}``."""

    hub: HubRef
    to: International
    type: Literal["text", "template"]
    text: Annotated[str, StringConstraints(max_length=4096)] | None = None
    template: TemplateRef | None = None

    @model_validator(mode="after")
    def _one_kind(self):
        if self.type == "text" and (not (self.text or "").strip() or self.template is not None):
            raise ValueError("A text message carries a non-empty text and no template.")
        if self.type == "template" and (self.template is None or self.text is not None):
            raise ValueError("A template message carries its template and no text.")
        return self


class SendClaimIn(Schema):
    hub: HubRef
    key: IdempotencyKey
    template_name: str = ""
    template_language: str = ""


class SendClaimOut(Schema):
    #: ``claimed``: this call sends it now; ``sent``: it went before (``wa_message_id``, maybe empty when Meta gave
    #: none); ``in_flight``: another call is sending it; ``refused``: it does not leave (``status``, ``code``).
    outcome: Literal["claimed", "sent", "in_flight", "refused"]
    status: int = 0
    code: str = ""
    message: str = ""
    send_id: UUID | None = None
    hub_id: UUID | None = None
    phone_number_id: str = ""
    token: SecretStr | None = None
    wa_message_id: str = ""


class SendRecordIn(Schema):
    send_id: UUID
    #: ``sent``: Meta accepted it (``wa_message_id``, empty if Meta gave none); ``unknown``: no answer came back (the
    #: place stays taken); ``released``: Meta refused it or was not reached: nothing left, the place is freed.
    outcome: Literal["sent", "unknown", "released"]
    wa_message_id: str = Field("", max_length=255)
    needs_reconnect: bool = False


class SendRecordOut(Schema):
    outcome: str


# --- Door 6: erase --------------------------------------------------------------------------------------------


class EraseIn(Schema):
    hub: HubRef
    phone: International
    wa_message_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=255)]] = Field(
        default_factory=list, max_length=10000
    )


class EraseOut(Schema):
    erased: bool
