"""The schemas of the payment details in the Billing section: each payer's card and the businesses it pays."""

from datetime import datetime
from uuid import UUID

from ninja import Schema

from billing.schemas.common import InvoiceBusinessOut


class PaymentMethodIn(Schema):
    hub_id: UUID | None = None


class CardOut(Schema):
    brand: str
    last4: str
    exp_month: int
    exp_year: int


class LastFailureOut(Schema):
    at: datetime
    business: str


class PaymentMethodRowOut(Schema):
    """The card of one payer (a Stripe customer) and the businesses it pays."""

    businesses: list[InvoiceBusinessOut]
    #: ``None`` when Stripe has no card for it, or did not answer (``unavailable``).
    card: CardOut | None
    unavailable: bool
    last_failure: LastFailureOut | None


class PaymentMethodOut(Schema):
    methods: list[PaymentMethodRowOut]
