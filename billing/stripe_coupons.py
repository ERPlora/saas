"""The Stripe coupons of the promo codes of free months: one per number of months, 100 % off for that many months.

Its id is fixed (``free-months-<N>``), so the same code works with the test and the live account without storing
anything: every checkout of a code of N months asks Stripe to create it, and from the second one on Stripe answers
that it exists already, which is the expected answer and no error.
"""

from datetime import UTC, datetime

from billing import stripe_service

COUPON_PREFIX = "free-months-"


def free_months_coupon_id(months: int) -> str:
    return f"{COUPON_PREFIX}{months}"


def ensure_free_months_coupon(months: int) -> str:
    """The id of the coupon of ``months`` free months, created when Stripe does not have it yet."""
    coupon_id = free_months_coupon_id(months)
    stripe_service._call(
        _create_unless_there,
        params={
            "id": coupon_id,
            "percent_off": 100,
            "duration": "repeating",
            "duration_in_months": months,
            "name": f"{months} months free",
        },
    )
    return coupon_id


def _create_unless_there(*, params: dict, options: dict) -> object:
    """``coupons.create``, with Stripe's «already exists» taken as the coupon itself: it is the usual answer, and
    ``stripe_service`` would log every refusal as an ERROR."""
    try:
        return stripe_service.client().v1.coupons.create(params=params, options=options)
    except Exception as refused:
        # Read by its code: only stripe_service imports the SDK, and any other failure goes back to it as it came.
        if getattr(refused, "code", None) != "resource_already_exists":
            raise
        return {"id": params["id"], "object": "coupon"}


def free_months_end(live: dict) -> datetime | None:
    """When the free months of a live subscription end: the end of the discount of one of these coupons (its
    ``discounts`` expanded, as ``stripe_service.retrieve_subscription`` reads them); ``None`` without one."""
    ends = [
        discount["end"]
        for discount in live.get("discounts") or []
        if isinstance(discount, dict) and discount.get("end") and _coupon_of(discount).startswith(COUPON_PREFIX)
    ]
    return datetime.fromtimestamp(max(ends), tz=UTC) if ends else None


def _coupon_of(discount: dict) -> str:
    coupon = (discount.get("source") or {}).get("coupon") or ""
    return coupon.get("id", "") if isinstance(coupon, dict) else coupon
