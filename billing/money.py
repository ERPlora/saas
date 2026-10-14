"""Euros ↔ integer cents, with the one rounding of the system: HALF_UP, explicit (ADR-0123 §4).

Every amount that is summed (the OSS threshold) or handed to Stripe is integer cents, so a sum is exact
by construction. ``quantize()`` without a mode inherits ``ROUND_HALF_EVEN`` from the decimal context,
which differs exactly on the .xx5 tie.
"""

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")
_UNIT = Decimal("1")


def to_cents(amount: Decimal | int | str) -> int:
    """``amount`` euros as integer cents, the tie rounded up (0.005 € → 1 cent)."""
    return int((Decimal(amount) * 100).quantize(_UNIT, rounding=ROUND_HALF_UP))


def from_cents(cents: int) -> Decimal:
    """``cents`` as euros with two decimals."""
    return (Decimal(int(cents)) / 100).quantize(_CENT, rounding=ROUND_HALF_UP)
