"""The schemas of ``billing.promo.check``: a promo code typed in the store, and what it grants."""

from ninja import Field, Schema

from billing.schemas.discounts import DiscountOut


class PromoCheckIn(Schema):
    """A promo code typed in the store, before paying."""

    code: str = Field(max_length=64)


class PromoCheckOut(Schema):
    """Whether the code is valid now and what it grants: trial days (``0`` without them) or a discount (``None``
    without one, and both when the code is not valid)."""

    code: str
    valid: bool
    trial_days: int
    discount: DiscountOut | None
