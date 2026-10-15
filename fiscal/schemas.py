"""Schemas of fiscal: the contract with the Hub (plan 2026-10-15, «Contrato»), the panel's state of the
authorisation and the reviews of the staff.

What the Hub posts is read leniently (every field a string, empty when left out): the rules are the service's
(``fiscal.services.representation_submit``), so each broken one answers its own ``fiscal.*`` code instead of a
generic validation error. Unknown fields are refused, so a typo of the Hub never passes for an absent document.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict, Field, field_validator

#: The state the Hub and the panel read: «none» is a business that never sent anything.
RepresentationState = Literal["none", "submitted", "approved", "returned", "revoked"]


#: The columns of ``RepresentationGrant`` keep 16 characters: a longer tax ID is malformed, never a crash.
TAX_ID_MAX_LENGTH = 16


class StrictIn(Schema):
    model_config = ConfigDict(extra="forbid")


# --- What the Hub posts (POST /internal/hubs/{id}/representation) ----------------------------------


class RepresentationDocumentsIn(StrictIn):
    """The four documents, each a PDF in base64: the signed Anexo I, the signer's identity document, a sample
    of the signature (required with a NIE) and the proof of representation (required for a company)."""

    signed_model: str = ""
    id_copy: str = ""
    signature_sample: str = ""
    representation_proof: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _absent_is_empty(cls, value):
        return "" if value is None else value


class RepresentationSubmitIn(StrictIn):
    """The authorisation as the Hub sends it: who owes the tax, who signs and the documents.

    ``hub_id`` is the business of the path (``fiscal.internal`` sets it): the body may name it too, and then it
    must be the same one (the v1 signature covers the body only, not the path)."""

    hub_id: UUID
    taxpayer_tax_id: str = Field("", max_length=TAX_ID_MAX_LENGTH)
    taxpayer_name: str = Field("", max_length=200)
    signer_tax_id: str = Field("", max_length=TAX_ID_MAX_LENGTH)
    signer_name: str = Field("", max_length=200)
    signer_document_type: str = Field("", max_length=8)
    documents: RepresentationDocumentsIn = Field(
        default_factory=RepresentationDocumentsIn
    )


class RepresentationSubmitOut(Schema):
    status: Literal["submitted"]
    version: int
    submitted_at: datetime


# --- The snapshot (PUT /internal/hubs/{id}/state, block ``verifactu``) ------------------------------


class RepresentationSnapshot(Schema):
    """``verifactu.representation`` of the business's snapshot: never a document, never a name."""

    status: RepresentationState
    updated_at: datetime | None
    reason: str


# --- The panel (fiscal.representation.status) -------------------------------------------------------


class RepresentationStatusIn(Schema):
    id: UUID


class RepresentationDocumentsOut(Schema):
    """Which documents the authorisation carries (never the documents)."""

    signed_model: bool
    id_copy: bool
    signature_sample: bool
    representation_proof: bool


class RepresentationHistoryOut(Schema):
    """One version the business sent; ``superseded`` when a newer one replaced it before any review."""

    version: int
    status: Literal["submitted", "approved", "returned", "revoked"]
    submitted_at: datetime
    reviewed_at: datetime | None
    reason: str
    superseded: bool


class RepresentationStatusOut(Schema):
    """The authorisation as the business sees it: the one in force if there is one, else the one waiting for
    review, else the one that changed last. ``changed_at`` is when it last changed (sent, reviewed or
    withdrawn): the date of its state."""

    status: RepresentationState
    version: int | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    changed_at: datetime | None
    reason: str
    taxpayer_tax_id: str
    taxpayer_name: str
    signer_name: str
    documents: RepresentationDocumentsOut
    history: list[RepresentationHistoryOut]


# --- The staff's review (fiscal.admin → fiscal.services) --------------------------------------------


class ReviewIn(Schema):
    id: UUID


class ReviewOut(Schema):
    """The authorisation once decided."""

    id: UUID
    status: Literal["approved", "returned", "revoked"]
    version: int


class ReturnIn(Schema):
    id: UUID
    reason: str = ""


class WithdrawIn(Schema):
    id: UUID
    reason: str = ""


class NotifyIn(Schema):
    """A change of the business's authorisation, told on the context's channel (a system command)."""

    id: UUID


class NotifyOut(Schema):
    id: UUID
