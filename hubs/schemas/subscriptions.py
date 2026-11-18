"""Schemas of what billing applies to a business from its Stripe subscription, and of the clock of a
suspended business."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from ninja import Field, Schema


#: Why a renewal is not paid (``hubs.Subscription.UnpaidReason``).
UnpaidReason = Literal["card_declined", "card_changed", "authentication_required", "payment_failed"]


class SuspensionStepOut(Schema):
    """What one step of the clock of a suspended business did (HUBS-F20): ``warned``, ``final_notice``,
    ``expired``, ``undated``, ``mail_failed`` or ``""`` (nothing due)."""

    id: UUID
    outcome: str


#: The label of a paid app (``modules[].id`` of the snapshot).
ModuleSlug = Annotated[str, Field(max_length=63, pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")]
SubscriptionStatus = Literal[
    "active", "trialing", "past_due", "unpaid", "canceled", "incomplete", "incomplete_expired", "paused"
]


class ModuleRightIn(Schema):
    """A module Stripe bills the business for (``source = purchase``): open-ended, or until ``valid_until``
    (cancelled at the end of its period)."""

    module_slug: ModuleSlug
    stripe_item_id: str = Field("", max_length=255)
    valid_until: datetime | None = None


class SubscriptionApplyIn(Schema):
    """What the live Stripe subscription says of a business (billing), applied as it comes. A field
    left out is left as it is; one sent as ``None`` is cleared.

    ``modules`` replaces the bought modules (the ones the plan includes are not Stripe's). ``standing``
    moves the business: ``good`` (paid), ``grace`` (a renewal failed, inside the 7 days: «payment
    pending») or ``suspended``.
    """

    hub_id: UUID
    plan: str | None = Field(None, max_length=50)
    billing_interval: Literal["month", "year"] | None = None
    status: SubscriptionStatus | None = None
    stripe_customer_id: str | None = Field(None, max_length=255)
    stripe_subscription_id: str | None = Field(None, max_length=255)
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool | None = None
    trial_start: datetime | None = None
    trial_end: datetime | None = None
    modules: list[ModuleRightIn] | None = None
    standing: Literal["good", "grace", "suspended"] | None = None
    unpaid_reason: UnpaidReason | None = None
    unpaid_since: datetime | None = None
    unpaid_invoice_url: str | None = Field(None, max_length=2048)
    #: Cleared once the subscription a deleted business still had ended in Stripe.
    cancel_requested_at: datetime | None = None


class SubscriptionApplyOut(Schema):
    hub_id: UUID
    #: The version of the snapshot after the change (it grows only when what the Hub sees changed).
    state_version: int
    #: Something was written.
    changed: bool
