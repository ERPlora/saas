"""The schemas of Stripe's own pages a person is sent to: the Customer Portal and the page to pay an invoice."""

from uuid import UUID

from ninja import Schema


class PortalOpenIn(Schema):
    hub_id: UUID


class PortalOpenOut(Schema):
    """Stripe's Customer Portal for the payer of the business (cards, invoices): one use, a few minutes."""

    url: str


class InvoicePayIn(Schema):
    id: UUID


class InvoicePayOut(Schema):
    """Stripe's page to pay the invoice (the payer's card, 3-D Secure included)."""

    url: str
