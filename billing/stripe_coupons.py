"""The Stripe coupons of the promo codes of free months: one per number of months, 100 % off for that many months.

Its id is fixed (``free-months-<N>``), so the same code works with the test and the live account without storing
anything: the coupon is made the first time a code of N months is used and found after that.
"""

from billing import stripe_service


def free_months_coupon_id(months: int) -> str:
    return f"free-months-{months}"


def ensure_free_months_coupon(months: int) -> str:
    """The id of the coupon of ``months`` free months, created when Stripe does not have it yet."""
    coupon_id = free_months_coupon_id(months)
    try:
        stripe_service._call(stripe_service.client().v1.coupons.retrieve, coupon_id)
        return coupon_id
    except stripe_service.StripeRefused as refused:
        if refused.code != "resource_missing":
            raise
    try:
        stripe_service._call(
            stripe_service.client().v1.coupons.create,
            params={
                "id": coupon_id,
                "percent_off": 100,
                "duration": "repeating",
                "duration_in_months": months,
                "name": f"{months} months free",
            },
        )
    except stripe_service.StripeRefused as refused:
        # Another checkout created it between the two calls: it is the same coupon.
        if refused.code != "resource_already_exists":
            raise
    return coupon_id
