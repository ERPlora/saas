"""A real charge in PRE with a Stripe test clock (the staff, from the admin)."""

import logging
from datetime import UTC, datetime, timedelta

from django.utils import timezone
from django.utils.translation import gettext as _

from billing import stripe_service, stripe_test_clocks
from billing.services import stripe_customers
from billing.stripe_keys import StripeKeyMode
from hubs.models import Hub

logger = logging.getLogger("billing.services")


#: How far «Advance the clock» moves it: past a monthly renewal.
TEST_CLOCK_STEP = timedelta(days=31)


class TestClockRefused(Exception):
    """Why a test clock was not attached or advanced, said to the staff as it is."""


def _require_test_mode() -> None:
    if stripe_service.key_mode() is not StripeKeyMode.TEST:
        raise TestClockRefused(_("Test clocks only exist with Stripe's test keys."))


def attach_test_clock(hub_id) -> str:
    """Create a Stripe test clock and the payer of ``hub_id`` as a NEW Stripe customer on it (Stripe attaches a
    clock only when the customer is created); its id. Test keys only."""
    _require_test_mode()
    hub = Hub.objects.select_related("billing_profile").get(pk=hub_id)
    profile = hub.billing_profile
    if profile is None:
        raise TestClockRefused(_("This business has no payer yet: fill in its billing details first."))
    try:
        known = profile.stripe_customer_id or stripe_service.find_customer(str(profile.id))
        if known:
            raise TestClockRefused(_("Its payer is a Stripe customer already: a clock only takes a new one."))
        clock = stripe_test_clocks.create_test_clock(int(timezone.now().timestamp()), name=f"QA {hub.slug}")
        stripe_customers.ensure_customer(hub, test_clock=clock)
    except (stripe_service.StripeUnavailable, stripe_service.StripeRefused) as failed:
        raise TestClockRefused(_("Stripe did not take it: %(reason)s") % {"reason": failed}) from failed
    return clock


def advance_test_clock_of(hub_id) -> datetime:
    """Move the test clock of the payer of ``hub_id`` one step (``TEST_CLOCK_STEP``) from its own time; when it
    reaches. It does not wait: Stripe advances it and tells what happens (a renewal, a charge) by its events, as
    in production. Test keys only; a clock still advancing is not pushed again."""
    _require_test_mode()
    hub = Hub.objects.select_related("billing_profile").get(pk=hub_id)
    customer = hub.billing_profile.stripe_customer_id if hub.billing_profile is not None else ""
    if not customer:
        raise TestClockRefused(_("This business has no test clock: attach one first."))
    try:
        clock_id = stripe_service.retrieve_customer(customer).get("test_clock") or ""
        if isinstance(clock_id, dict):
            clock_id = clock_id.get("id", "")
        if not clock_id:
            raise TestClockRefused(_("This business has no test clock: attach one first."))
        clock = stripe_service.retrieve_test_clock(clock_id)
        if clock.get("status") != "ready":
            raise TestClockRefused(_("Its clock is still advancing: try again in a minute."))
        to = int(clock["frozen_time"] + TEST_CLOCK_STEP.total_seconds())
        stripe_service.advance_test_clock(clock_id, {"frozen_time": to})
    except (stripe_service.StripeUnavailable, stripe_service.StripeRefused) as failed:
        raise TestClockRefused(_("Stripe did not take it: %(reason)s") % {"reason": failed}) from failed
    logger.info("[TEST CLOCK] %s of hub %s advancing to %s", clock_id, hub.id, to)
    return datetime.fromtimestamp(to, tz=UTC)
