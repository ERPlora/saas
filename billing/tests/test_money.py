"""Euros ↔ integer cents, with the one rounding of the system (ADR-0123 §4: HALF_UP, explicit).

A bare ``quantize()`` inherits ``ROUND_HALF_EVEN`` from the decimal context, a different mode that
shows up exactly on the .xx5 tie; the OSS threshold and every amount sent to Stripe are cents.
"""

from decimal import Decimal

import pytest

from billing.money import from_cents, to_cents


@pytest.mark.parametrize(
    "amount, cents",
    [
        (Decimal("29.99"), 2999),
        (Decimal("0.005"), 1),  # the tie goes up, not to the even neighbour
        (Decimal("0.015"), 2),
        (Decimal("0.025"), 3),
        (Decimal("10000"), 1_000_000),
        ("12.345", 1235),
        (0, 0),
    ],
)
def test_to_cents_rounds_half_up(amount, cents):
    assert to_cents(amount) == cents


def test_from_cents_gives_two_decimals():
    assert from_cents(2999) == Decimal("29.99")
    assert from_cents(0) == Decimal("0.00")
    assert str(from_cents(1_200_000)) == "12000.00"


def test_the_round_trip_keeps_every_cent():
    for cents in (0, 1, 99, 2999, 1_000_001):
        assert to_cents(from_cents(cents)) == cents
