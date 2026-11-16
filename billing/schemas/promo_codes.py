"""The schemas of ``billing.promo.check``: a promo code typed in the store, and what it grants."""

from typing import Literal

from ninja import Field, Schema

PromoKind = Literal["trial_days", "free_months"]


class PromoCheckIn(Schema):
    """A promo code typed in the store, before paying."""

    code: str = Field(max_length=64)


class PromoCheckOut(Schema):
    """Whether the code is valid now and what it grants: trial days or free months (``0`` for the other, and for both
    when it is not valid)."""

    code: str
    valid: bool
    kind: PromoKind
    trial_days: int
    free_months: int
