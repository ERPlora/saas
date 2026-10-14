"""Stripe test clocks: a REAL charge for the billing QA (saas#1961; PLAN-SAAS §4).

Ported from ERPlora/saas ``hubs/main/services/stripe_test_clocks.py`` (origin/develop). Every paid plan
carries a trial and Stripe charges nothing during it, so the chain after a payment never ran in a test. A
clock removes the need for an internal 1 € plan: the customer is created attached to it
(``billing.services.ensure_customer(hub, test_clock=…)``), subscribes to a NORMAL plan with its NORMAL trial,
and the clock is advanced past the trial: Stripe issues a real invoice.

Two refusals, because both failures are silent and would turn a QA run green while proving nothing:

- **A live key** (``sk_live_``/``rk_live_``): clocks exist only in test mode. Refused before calling Stripe.
- **Returning before the clock is ``ready``**: advancing is asynchronous, and reading a subscription while
  the clock is ``advancing`` returns the state from BEFORE the jump.
"""

import logging
import time

from django.conf import settings

from billing import stripe_service
from billing.stripe_keys import StripeKeyMode, stripe_key_mode

logger = logging.getLogger("billing.stripe")

_ADVANCING = "advancing"
_READY = "ready"


class LiveModeRefused(RuntimeError):
    """A test clock was asked for while Stripe is configured with a live key."""


class ClockNotReady(RuntimeError):
    """The clock did not reach ``ready``: it failed, or it was still advancing when we gave up."""


def _refuse_live_mode(what: str) -> None:
    # The key as written (a live secret key the gateway refuses is still a live key, never a test one).
    if stripe_key_mode(settings.STRIPE_SECRET_KEY) is StripeKeyMode.LIVE:
        raise LiveModeRefused(
            f"{what} needs Stripe TEST mode: test clocks do not exist in live mode, and the configured "
            "STRIPE_SECRET_KEY is a live key."
        )


def create_test_clock(frozen_time: int, name: str = "") -> str:
    """A new clock frozen at ``frozen_time`` (unix seconds); its id. Name it: an unnamed clock in a shared
    test account is indistinguishable from anybody else's."""
    _refuse_live_mode("Creating a test clock")
    clock = stripe_service.create_test_clock({"frozen_time": frozen_time, "name": name})
    logger.info(
        "[TEST CLOCK] Created %s frozen at %s (%s)",
        clock["id"],
        frozen_time,
        name or "unnamed",
    )
    return clock["id"]


def advance_test_clock(
    clock_id: str, to_ts: int, *, max_polls: int = 60, poll_interval_s: float = 2.0
) -> None:
    """Advance ``clock_id`` to ``to_ts`` and return only once Stripe reports it ``ready``; ``ClockNotReady``
    if it fails or is still advancing after ``max_polls`` reads."""
    _refuse_live_mode("Advancing a test clock")
    stripe_service.advance_test_clock(clock_id, {"frozen_time": to_ts})
    for _poll in range(max_polls):
        status = stripe_service.retrieve_test_clock(clock_id).get("status", "")
        if status == _READY:
            logger.info("[TEST CLOCK] %s reached %s", clock_id, to_ts)
            return
        if status != _ADVANCING:
            raise ClockNotReady(
                f"Test clock {clock_id} reported {status!r} while advancing to {to_ts}."
            )
        time.sleep(poll_interval_s)
    raise ClockNotReady(
        f"Test clock {clock_id} was still advancing after {max_polls} reads on its way to {to_ts}."
    )
