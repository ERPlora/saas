"""The schemas of a discount as the panel reads it: in ``billing.promo.check`` and on a subscription."""

from datetime import datetime
from typing import Literal

from ninja import Schema

DiscountDuration = Literal["once", "repeating", "forever"]
DiscountAppliesTo = Literal["plans"]
Interval = Literal["month", "year"]


class DiscountAppliesToOut(Schema):
    """What the discount applies to: plans (none named = every plan), with the billings it goes with."""

    kind: DiscountAppliesTo
    plans: list[str]
    intervals: list[Interval]


class DiscountOut(Schema):
    """A percentage or an amount in cents (the other ``None``), once, for some months or forever."""

    percent_off: int | None
    amount_off_cents: int | None
    currency: str
    duration: DiscountDuration
    duration_in_months: int | None
    applies_to: DiscountAppliesToOut


class SubscriptionDiscountOut(Schema):
    """The discount of a promo code a subscription carries: its code, its terms and when it ends (``None``: never)."""

    code: str
    ends_at: datetime | None
    terms: DiscountOut
