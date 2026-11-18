"""Stripe's failures as the panel's errors, and what a charge passes first: Stripe configured and, with a live key,
a route that sends ERPlora's invoice and this year's OSS total on file."""

import logging
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _
from live.errors import Conflict, OperationError

from billing import queries, stripe_service
from billing.stripe_keys import StripeKeyMode
from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable

logger = logging.getLogger("billing.services")


def _payments_unavailable() -> OperationError:
    return OperationError(
        _(
            "Payments are not available right now. Nothing was charged; try again later."
        ),
        code="billing.payments_unavailable",
        status=503,
    )


@contextmanager
def stripe_errors(*, charging: bool = False):
    """Stripe's failures as the panel's errors. ``charging``: the call may have charged when Stripe did not
    answer (the request may have gone through), so the panel never hears «nothing was charged» then; a
    refusal, a declined card included, charged nothing."""
    try:
        yield
    except stripe_service.StripeNotConfigured:
        raise _payments_unavailable() from None
    except stripe_service.StripeUnavailable:
        message = (
            _(
                "The payment service did not answer, so the charge is not confirmed. Check Billing before trying again."
            )
            if charging
            else _(
                "The payment service did not answer. Nothing was charged; try again in a moment."
            )
        )
        raise OperationError(
            message, code="billing.stripe_unavailable", status=503
        ) from None
    except stripe_service.StripeRefused as refused:
        if refused.card:
            raise Conflict(
                _(
                    "The bank declined the card. Nothing was charged: change the card and try again."
                ),
                code="billing.card_declined",
            ) from None
        raise OperationError(
            _(
                "The payment service refused the operation. Nothing was charged; contact support."
            ),
            code="billing.stripe_refused",
            status=502,
        ) from None


def require_stripe() -> None:
    """Stripe is configured (a secret or restricted key): 503 ``billing.payments_unavailable`` otherwise,
    before anything is asked of it."""
    if stripe_service.key_mode() is StripeKeyMode.UNKNOWN:
        raise _payments_unavailable()


#: How long a healthy answer of the platform hub opens live charging; a failed one is asked again next time.
PLATFORM_HEALTH_SECONDS = 5 * 60
PLATFORM_HEALTH_KEY = "billing.platform_invoicing.healthy"


def invoicing_available() -> bool:
    """Whether a route sends ERPlora's invoices now: the platform invoicing is switched on
    (``PLATFORM_INVOICING_ENABLED``, off by default) AND the platform hub answers its health route
    (``GET /internal/platform/invoices/health`` → 200 ``{"status": "ok"}``), kept ``PLATFORM_HEALTH_SECONDS``."""
    if not settings.PLATFORM_INVOICING_ENABLED:
        return False
    if cache.get(PLATFORM_HEALTH_KEY):
        return True
    try:
        answer = hub_client.platform_invoicing_health()
    except (HubUnavailable, HubRefused) as failed:
        logger.error("[BILLING] The platform hub does not issue invoices now: %s", failed)
        return False
    healthy = answer.status == 200 and isinstance(answer.body, dict) and answer.body.get("status") == "ok"
    if healthy:
        cache.set(PLATFORM_HEALTH_KEY, True, PLATFORM_HEALTH_SECONDS)
    return healthy


def require_payments() -> None:
    """Stripe is configured, and a LIVE key moves real money only while a route sends ERPlora's invoice of
    it (``invoicing_available``: in production nothing is charged without a route that sends its invoice)
    and this year's OSS total is known.

    The OSS threshold (10,000 € a year of cross-border B2C sales) decides between Spanish and destination
    VAT, and part of the year was sold by the old SaaS (``FiscalPolicy.oss_carried_*``): until that sum is
    on file for this year, a sale could cross the threshold unseen. A
    test key moves no real money and is never held.
    """
    require_stripe()
    if stripe_service.key_mode() is not StripeKeyMode.LIVE:
        return
    if not invoicing_available():
        logger.error(
            "[BILLING] A live sale was refused: no route sends ERPlora's invoice now (PLATFORM_INVOICING_ENABLED "
            "and the platform hub's health)",
            extra={"event": "billing.invoicing_unavailable"},
        )
        raise Conflict(
            _(
                "Payments open once ERPlora can invoice them. Nothing was charged; try again later."
            ),
            code="billing.invoicing_unavailable",
        )
    year = timezone.localdate().year
    if not queries.oss_total_is_known(queries.fiscal_policy(), year):
        logger.error(
            "[BILLING] A live sale was refused: the OSS total of %s is not on file (FiscalPolicy.oss_carried_*)",
            year,
            extra={"event": "billing.oss_total_unknown", "year": year},
        )
        raise Conflict(
            _(
                "Payments are paused while this year's EU sales total is brought up to date. Nothing was "
                "charged; try again later."
            ),
            code="billing.oss_total_unknown",
        )
