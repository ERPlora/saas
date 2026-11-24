"""A sale as the VAT engine is asked about it: who pays, by the facts of a payer, and how much.

A fact that is not said keeps the engine's own default."""

from billing import vat

PAYER = {"country", "postal_code", "tax_id", "tax_id_type", "tax_id_verified"}


def _arguments(facts: dict) -> dict:
    return {f"customer_{name}" if name in PAYER else name: value for name, value in facts.items()}


def priced(net, **facts):
    """The tax to add to a net price, before charging it; ``None`` when the sale cannot be priced."""
    return vat.quote_vat(net, **_arguments(facts))


def charged(gross, **facts):
    """How an amount already charged splits into base and quota."""
    return vat.resolve_vat(gross, **_arguments(facts))
