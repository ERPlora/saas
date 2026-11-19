"""A payer's tax id on its Stripe customer, which Stripe prints on its own receipts and pages.

The customer holds the payer's current tax id and no other: Stripe prints every tax id a customer has and refuses a
sixth one. ERPlora's invoices and their fiscal record take the tax id from the billing profile, never from Stripe, so
Stripe refusing to add or remove one is logged and never stops a sale.
"""

import logging

from billing import stripe_service, vies

logger = logging.getLogger(__name__)


def stripe_value(number: str, *, country: str) -> str:
    """``number`` as Stripe takes it: with its country's prefix, which a national number is kept without (an
    ``eu_vat`` of ``B12345674`` is refused, of ``ESB12345674`` taken)."""
    if vies.split_vat_number(number)[0]:
        return number
    return vies.vies_prefix(country) + number


def keep_only(customer: str, *, tax_type: str, number: str, country: str) -> None:
    """Leave ``number`` as the only tax id of the Stripe customer, or none when ``number`` is empty (a payer without
    one, or whose number may not travel to Stripe). The old ones go first, so a customer holding five still takes the
    new one. Stripe not answering raises (``StripeUnavailable``): only its refusals are let go."""
    value = stripe_value(number, country=country) if number else ""
    held = stripe_service.customer_tax_ids(customer)
    for old in held:
        if old.get("value") != value:
            _remove(customer, old["id"])
    if value and not any(existing.get("value") == value for existing in held):
        _add(customer, tax_type=tax_type, value=value)


def _remove(customer: str, tax_id: str) -> None:
    try:
        stripe_service._call(stripe_service.client().v1.customers.tax_ids.delete, customer, tax_id)
    except stripe_service.StripeRefused as refused:
        logger.error(
            "[BILLING] Stripe refused to remove the old tax id %s of customer %s (%s): Stripe goes on printing it",
            tax_id,
            customer,
            refused.code or "no code",
            extra={"event": "billing.stripe_tax_id_not_removed", "code": refused.code},
        )


def _add(customer: str, *, tax_type: str, value: str) -> None:
    try:
        stripe_service.add_customer_tax_id(customer, tax_type=tax_type, value=value)
    except stripe_service.StripeRefused as refused:
        logger.error(
            "[BILLING] Stripe refused the %s tax id of customer %s (%s): the sale goes on without it",
            tax_type,
            customer,
            refused.code or "no code",
            extra={"event": "billing.stripe_tax_id_refused", "code": refused.code},
        )
