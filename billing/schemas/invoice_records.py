"""The internal schemas that record what Stripe's webhook and ERPlora's platform hub report about an invoice, a
credit note, a refund or a refunded checkout."""

from typing import Any, Literal
from uuid import UUID

from ninja import Schema

from billing.schemas.invoices import InvoicePaymentStatus

PlatformStatus = Literal["issuing", "issued", "accepted", "accepted_with_errors", "rejected"]


class InvoiceRecordIn(Schema):
    """Internal (the webhook): a Stripe invoice of a business, to list (``open``), invoice (``paid``) or drop
    (``void``). The VIES clearance of the payer is asked before the business is locked."""

    hub_id: UUID
    invoice: dict[str, Any]
    status: InvoicePaymentStatus
    tax_id_verified: bool = False
    vat_consultation_number: str = ""


class InvoiceRecordOut(Schema):
    id: UUID | None
    number: str
    payment_status: str
    #: ``listed``, ``numbered``, ``duplicate``, ``voided``, ``ignored`` or ``unknown``.
    outcome: str


class CreditNoteRecordIn(Schema):
    """Internal (the webhook): a Stripe credit note of an invoice ERPlora issued."""

    credit_note: dict[str, Any]


class RefundRecordIn(Schema):
    """Internal (the webhook): a Stripe refund made without a credit note, of the invoice ``invoice_id``."""

    invoice_id: UUID
    refund: dict[str, Any]


class CheckoutRefundRecordIn(Schema):
    """Internal (the webhook): a checkout paid by somebody who no longer owned the business, already ended and
    refunded in Stripe (``refunded`` in cents)."""

    attempt_id: UUID
    refunded: int


class CheckoutRefundRecordOut(Schema):
    attempt_id: UUID
    status: str


class FiscalAnswerIn(Schema):
    """Internal: what ERPlora's platform hub answered about an invoice."""

    id: UUID
    status: PlatformStatus
    qr: str = ""
    error_code: str = ""
    error: str = ""


class FiscalAnswerOut(Schema):
    id: UUID
    fiscal_status: str
    changed: bool
