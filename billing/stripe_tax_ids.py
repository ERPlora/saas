"""A payer's tax id on its Stripe customer, which Stripe prints on its own receipts and pages.

ERPlora's invoices and their fiscal record take the tax id from the billing profile, never from Stripe, so Stripe
refusing it is logged and never stops a sale.
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


def attach(customer: str, *, tax_type: str, number: str, country: str) -> None:
    """Add the payer's tax id to its Stripe customer, unless the customer has it already. Stripe not answering
    raises (``StripeUnavailable``): only its refusal is let go."""
    value = stripe_value(number, country=country)
    if any(existing.get("value") == value for existing in stripe_service.customer_tax_ids(customer)):
        return
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
