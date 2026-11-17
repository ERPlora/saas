"""What a discount takes off and where it applies, with no database: the answers the checkout, the next invoice and
the coupon's name in Stripe share."""

from collections.abc import Collection
from decimal import ROUND_HALF_UP, Decimal

#: Stripe's limit on a coupon's name.
COUPON_NAME_LENGTH = 40


def off_cents(discount, net_cents: int) -> int:
    """What ``discount`` takes off ``net_cents``: its percentage rounded to the nearest cent (half up, as Stripe), or
    its amount, never more than there is."""
    if discount.percent_off is not None:
        taken = (Decimal(net_cents) * discount.percent_off / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return min(int(taken), net_cents)
    return min(discount.amount_off_cents or 0, net_cents)


def covers(plan_ids: Collection, plan_id) -> bool:
    """Whether a discount on ``plan_ids`` (none = every plan) applies to the plan ``plan_id``."""
    return not plan_ids or plan_id in plan_ids


def intervals(discount) -> tuple[str, ...]:
    """The billings it is sold with: one that lasts a number of months runs on the clock, so monthly only."""
    return ("month",) if discount.duration == "repeating" else ("month", "year")


def coupon_name(discount) -> str:
    """Its name in Stripe, in English: what it takes off and for how long."""
    off = _off_label(discount)
    if discount.duration == "repeating":
        months = discount.duration_in_months
        name = f"{off} for {months} month{'' if months == 1 else 's'}"
    elif discount.duration == "forever":
        name = f"{off} forever"
    else:
        name = "Free first payment" if off == "Free" else f"{off} the first payment"
    return name[:COUPON_NAME_LENGTH]


def _off_label(discount) -> str:
    if discount.percent_off == 100:
        return "Free"
    if discount.percent_off is not None:
        return f"{discount.percent_off}% off"
    return f"{Decimal(discount.amount_off_cents) / 100:.2f} {discount.currency.upper()} off"
