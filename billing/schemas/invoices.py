"""The schemas of ERPlora's invoices in the Billing section: the filtered list, the detail and the file to download."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from billing.schemas.common import InvoiceBusinessOut

InvoicePaymentStatus = Literal["open", "paid", "void"]
InvoiceFiscalStatus = Literal["", "issuing", "issued", "accepted", "accepted_with_errors", "rejected"]
#: VeriFactu's ``TipoFactura`` of a rectifying invoice (``Invoice.RectificationType`` without its empty value).
InvoiceRectificationType = Literal["R1", "R2", "R3", "R4"]


class InvoiceFilterIn(Schema):
    """The filters of the invoices of the account: a business, the payment, a year and a number."""

    hub_id: UUID | None = None
    #: ``paid`` or ``open`` (not collected); empty, every one.
    status: InvoicePaymentStatus | None = None
    year: int | None = Field(None, ge=2000, le=2999)
    search: str | None = Field(None, max_length=64, description="Part of the number.")


class InvoiceListIn(InvoiceFilterIn):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class InvoiceCanOut(Schema):
    """What the row's buttons do for this account, computed by the server: ``pay`` (not collected, and the
    account pays it) and ``pdf`` (issued by the platform hub)."""

    pay: bool
    pdf: bool


class InvoiceRectificationOut(Schema):
    """Why a credit note rectifies: its VeriFactu type and the reason printed on it (empty when Stripe gave
    none)."""

    type: InvoiceRectificationType
    reason: str


class InvoiceRowOut(Schema):
    id: UUID
    kind: Literal["invoice", "credit_note"]
    kind_label: str
    #: ``None`` until it is paid (an unpaid Stripe invoice has no number of ours yet).
    number: str | None
    #: Stripe's number of it: the reference of one not numbered yet.
    reference: str
    date: date
    business: InvoiceBusinessOut
    currency: str
    net_cents: int
    tax_cents: int
    total_cents: int
    payment_status: InvoicePaymentStatus
    payment_status_label: str
    fiscal_status: InvoiceFiscalStatus
    fiscal_status_label: str
    #: Why «Pay» is disabled: the bank declined the card (change it first) or another account pays it.
    pay_blocked_reason: Literal["card_change_required", "payer_required"] | None
    #: The row's actions in order, the fixed one first.
    actions: list[Literal["pay", "pdf"]]
    can: InvoiceCanOut
    #: ``None`` for an invoice; a credit note's type (R1–R4) and reason.
    rectification: InvoiceRectificationOut | None
    #: The Stripe object that made a credit note (``cn_…`` credit note, ``re_…`` refund); empty for an invoice.
    stripe_source_id: str


class InvoiceListOut(Schema):
    rows: list[InvoiceRowOut]
    total: int
    limit: int
    offset: int


class InvoiceByIdIn(Schema):
    id: UUID


class InvoiceLineOut(Schema):
    position: int
    description: str
    item_kind: Literal["plan", "module", "other"]
    item_slug: str
    quantity: int
    proration: bool
    period_start: datetime | None
    period_end: datetime | None
    tax_rate: Decimal
    net_cents: int
    tax_cents: int
    total_cents: int
    discount_cents: int


class InvoiceRecipientOut(Schema):
    name: str
    tax_id: str
    address: str
    city: str
    postal_code: str
    country: str
    email: str


class InvoiceRefOut(Schema):
    id: UUID
    number: str


class InvoiceDetailOut(InvoiceRowOut):
    issued_on: date | None
    paid_at: datetime | None
    tax_treatment: str
    tax_country: str
    tax_rate: Decimal
    recipient: InvoiceRecipientOut
    lines: list[InvoiceLineOut]
    rectifies: InvoiceRefOut | None
    #: The content of the VeriFactu QR, once the platform hub issued it.
    qr: str


class InvoiceFileOut(Schema):
    """A document to download: the route answers it as the file itself."""

    filename: str
    content_type: str
    content: bytes
