"""The schemas of the subscriptions of the account in the Billing section: each business's plan, modules, next
invoice and what its buttons do."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from billing.schemas.common import Interval, InvoiceBusinessOut
from billing.schemas.discounts import SubscriptionDiscountOut
from billing.schemas.subscription_changes import ScheduledChangeOut


class SubscriptionListIn(Schema):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)
    #: One business's subscription; only among the account's.
    hub_id: UUID | None = None
    #: Stripe's status of the subscription (an ended one is never a row).
    status: Literal["active", "trialing", "past_due", "unpaid", "incomplete", "paused"] | None = None


class SubscriptionPlanOut(Schema):
    slug: str
    name: str
    interval: Interval
    #: Net, as the plan is sold («29,99 €/mes + IVA»).
    price_cents: int


class SubscriptionModuleRowOut(Schema):
    slug: str
    interval: Interval
    #: Net; ``None`` for a module no longer on sale.
    price_cents: int | None
    source: Literal["plan", "purchase"]
    #: Cancelled: it works until then.
    valid_until: datetime | None


class NextInvoiceOut(Schema):
    date: datetime | None
    #: With VAT, as the payer's place prices it; ``None`` while that place is unknown.
    total_cents: int | None
    currency: str


class SubscriptionCanOut(Schema):
    change_plan: bool
    cancel_plan: bool
    keep_plan: bool
    #: «Keep it with my card»: the business was handed over and its plan is still on the previous payer's card.
    take_over: bool
    view_invoice: bool
    view_invoices: bool


class SubscriptionRowOut(Schema):
    business: InvoiceBusinessOut
    plan: SubscriptionPlanOut
    modules: list[SubscriptionModuleRowOut]
    #: ``None`` when the plan ends at the end of the period (``cancelling``) or the business was deleted: no invoice
    #: follows.
    next_invoice: NextInvoiceOut | None
    #: Stripe's status of the subscription; ``deleting`` once the business was deleted, as its own page says.
    status: str
    status_label: str
    cancelling: bool
    ends_at: datetime | None
    #: The business was deleted and its Stripe subscription is being ended.
    cancel_requested: bool
    #: The open invoice the business owes («View the invoice»), if any.
    unpaid_invoice_id: UUID | None
    #: A downgrade waiting for the end of the period («Starter from 1 Nov»).
    scheduled_change: ScheduledChangeOut | None = None
    #: The plan is charged to the card of another account (the payer before a hand-over, HUBS-F28).
    paid_by_another_account: bool
    #: The discount of a promo code it carries while it applies to the renewal.
    discount: SubscriptionDiscountOut | None
    actions: list[Literal["take_over", "change_plan", "keep_plan", "view_invoice", "cancel_plan", "view_invoices"]]
    can: SubscriptionCanOut


class SubscriptionListOut(Schema):
    rows: list[SubscriptionRowOut]
    total: int
    limit: int
    offset: int
