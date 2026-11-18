"""What every place that applies Stripe's word shares: its timestamps as moments, the business held while it is
applied, the live subscription read without failing, and the tax rates of an item update."""

import logging
from contextlib import contextmanager
from datetime import UTC, datetime

from django.db import transaction

from billing import stripe_service
from hubs.models import Hub

logger = logging.getLogger("billing.services")


def _moment(timestamp: int | None) -> datetime | None:
    return datetime.fromtimestamp(timestamp, tz=UTC) if timestamp else None


@contextmanager
def holding(hub_id):
    """A transaction holding the business's row: what a webhook reads from Stripe inside it is applied before
    any operation on the business can change it (operations take the same lock)."""
    with transaction.atomic():
        Hub.objects.select_for_update().filter(pk=hub_id).first()
        yield


def _read_live(subscription_id: str) -> dict | None:
    """The live subscription, or ``None`` when Stripe does not answer (the caller decides what that means)."""
    try:
        return stripe_service.retrieve_subscription(subscription_id)
    except stripe_service.StripeUnavailable, stripe_service.StripeNotConfigured:
        logger.warning(
            "[STRIPE WEBHOOK] Could not read %s from Stripe: the event is applied as it came",
            subscription_id,
        )
        return None


def _rates_param(rates: list[str]) -> list[str] | str:
    """``tax_rates`` of an item UPDATE: an empty list is dropped by the SDK (Stripe keeps the old rate), an
    empty string is what removes it."""
    return rates or ""
