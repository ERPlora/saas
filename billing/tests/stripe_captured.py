"""Stripe's own objects for the tests, captured from the test account with test clocks (``fixtures/discounts/``): a
discount's coupon, the subscriptions and schedules that carry it and the ``invoice.paid`` of what it billed.

``paid`` hands an event over billed to the tests' subscription and prices, so the webhook records it as it would the
real one: the business of ``running`` (``sub_1``), and Starter, Standard and the inventory module by their name.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "discounts"
#: The tests' prices of what the captures sell, by the product a line names and its billing.
PRICES = {
    ("Starter", "month"): "price_starter_month",
    ("Starter", "year"): "price_starter_year",
    ("Standard", "month"): "price_standard_month",
    ("Bookings", "month"): "price_inventory_month",
}


def captured(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def paid(name: str, subscription_id: str = "sub_1") -> dict:
    """The captured ``invoice.paid`` ``name`` (``repeating_100/invoice_paid_1.json``), billed to ``subscription_id``
    with the tests' prices."""
    payload = captured(name)
    stripe_invoice = payload["data"]["object"]
    stripe_invoice["parent"]["subscription_details"]["subscription"] = subscription_id
    for line in stripe_invoice["lines"]["data"]:
        product = next(word for word in ("Starter", "Standard", "Bookings") if word in line["description"])
        line["pricing"]["price_details"]["price"] = PRICES[product, line["price"]["recurring"]["interval"]]
    return payload
