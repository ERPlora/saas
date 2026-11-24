"""A sale as the VAT engine is asked about it: who pays, by the facts of a payer, and how much.

A fact that is not said keeps the engine's own default."""

from dataclasses import fields

from billing import vat
from billing.payer import Payer

PAYER = {field.name for field in fields(Payer)}


def _apart(facts: dict) -> tuple[Payer, dict]:
    sale = {name: value for name, value in facts.items() if name not in PAYER}
    return Payer(**{name: value for name, value in facts.items() if name in PAYER}), sale


def priced(net, **facts):
    """The tax to add to a net price, before charging it; ``None`` when the sale cannot be priced."""
    payer, sale = _apart(facts)
    return vat.quote_vat(net, payer, **sale)


def charged(gross, **facts):
    """How an amount already charged splits into base and quota."""
    payer, sale = _apart(facts)
    return vat.resolve_vat(gross, payer, **sale)
