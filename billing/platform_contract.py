"""What the body of ``POST /internal/platform/invoices`` needs beyond the invoice's own fields: the days of its contract."""

from datetime import datetime

from django.utils import timezone


def day(value) -> str | None:
    """A day of the platform hub's contract, ``YYYY-MM-DD``: a moment (a period of Stripe) is the day it falls on in
    Spain, never the moment itself, which the hub refuses."""
    if isinstance(value, datetime):
        value = timezone.localdate(value, timezone.get_default_timezone())
    return value.isoformat() if value is not None else None
