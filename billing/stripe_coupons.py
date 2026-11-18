"""The Stripe coupon of a discount: its mirror, with an id derived from it, so nothing is stored on our side.

The id is ``erp-discount-<12 hex of the discount>-<8 hex of its terms and products>``: the same discount on the same
products is always the same coupon, in test and live mode alike. Every checkout asks Stripe to create it, and from the
second one on Stripe answers that it exists already, which is the expected answer and no error.
"""

import hashlib
import json
from datetime import UTC, datetime

from billing import discount_terms, stripe_service

COUPON_PREFIX = "erp-discount-"


def coupon_id(discount, products: list[str]) -> str:
    terms = {
        "percent_off": discount.percent_off,
        "amount_off": discount.amount_off_cents,
        "currency": discount.currency,
        "duration": discount.duration,
        "duration_in_months": discount.duration_in_months,
        "applies_to": discount.applies_to,
        "products": sorted(products),
    }
    print_ = hashlib.sha256(json.dumps(terms, sort_keys=True).encode()).hexdigest()[:8]
    return f"{COUPON_PREFIX}{discount.id.hex[:12]}-{print_}"


def ensure_coupon(discount, products: list[str]) -> str:
    """The id of the coupon of ``discount`` on ``products`` (those of its plans), created when Stripe does not have it."""
    params = {"id": coupon_id(discount, products), "duration": discount.duration}
    if discount.percent_off is not None:
        params["percent_off"] = discount.percent_off
    else:
        params.update(amount_off=discount.amount_off_cents, currency=discount.currency)
    if discount.duration_in_months is not None:
        params["duration_in_months"] = discount.duration_in_months
    params.update(applies_to={"products": products}, name=discount_terms.coupon_name(discount))
    stripe_service._call(_create_unless_there, params=params)
    return params["id"]


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


def live_discounts(live: dict) -> list[dict]:
    """The discounts of ours on a live subscription (its ``discounts`` expanded, as
    ``stripe_service.retrieve_subscription`` reads them)."""
    return [
        discount
        for discount in live.get("discounts") or []
        if isinstance(discount, dict) and _coupon_of(discount).startswith(COUPON_PREFIX)
    ]


def discount_end(live: dict) -> datetime | None:
    """When the discount of ours on a live subscription ends; ``None`` without one, or for one forever."""
    ends = [discount["end"] for discount in live_discounts(live) if discount.get("end")]
    return datetime.fromtimestamp(max(ends), tz=UTC) if ends else None


def _coupon_of(discount: dict) -> str:
    coupon = (discount.get("source") or {}).get("coupon") or ""
    return coupon.get("id", "") if isinstance(coupon, dict) else coupon
