"""The SaaS's worker (saas#305): ``manage.py run_worker`` runs it in the ``saas-worker`` task, one per deploy
(ERPlora/aws ``stacks/prod/apps.tf``). One process and one thread, long-running, in place of the tasks that started a
container every minute (``whatsapp_deliver``) and every 15 minutes (the two reconciliations).

It wakes on the first of:

- a ``NOTIFY`` on ``whatsapp.services.DELIVERY_CHANNEL``, sent after the COMMIT of what made a delivery to the Hub due
  or moved its wait (parked by Meta's webhook, retried, held, «Push to the Hub now»);
- the time of the next delivery due (``whatsapp.delivery.next_due``);
- the next quarter of an hour (``next_round``: :00, :15, :30 and :45 UTC, whatever the process's start).

Each wake-up runs the pass of the deliveries (``gateway.deliver_pass``, under the lock of ``whatsapp_deliver``: the
command of the same name and another worker never run one beside it), and at each quarter the two reconciliations,
each under its own lock (``PERIODIC``: the passes of ``reconcile_hub_states`` and ``reconcile_platform_invoices``, the
same functions their commands run). Between two wake-ups it sends nothing to the database, so Aurora can go down to its
minimum: its connections go back to the pool and the wait is on the socket of its own LISTEN connection
(``base.listener``). It never looks again at once when a pass took nothing (``IDLE_FLOOR``) and, after a pass that
failed, looks again in ``RETRY_AFTER_FAILURE`` at most.

A pass that fails, or a reconciliation that left work owed, logs one ERROR line that starts with
``saas.worker.pass_failed task=<name>`` (the text the infra's metric filter looks for; it replaces the ``task_failed``
of a task that ended with an error) and the loop goes on. A stop request (``stop``, set by SIGTERM or SIGINT, whose
handler also wakes the wait) ends the loop after the push in course, and ``run`` returns 0; anything else that fails
outside a pass ends it with 1 (``saas.worker.crashed``).
"""

import logging
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.db import close_old_connections
from django.utils import timezone

from base.listener import Listener
from billing import services as billing_services
from hubs import services as hubs_services
from whatsapp import gateway, queries, services
from whatsapp.schemas import NextDueIn

logger = logging.getLogger(__name__)

#: The name of the deliveries' pass in its log lines (its lock's too).
DELIVERY = "whatsapp_deliver"
#: The INFO line the worker writes at start and at every round: its sign of life for the infra's alarm.
LIVENESS = "saas.worker.alive"
#: How often the reconciliations run: at each quarter of an hour of the clock.
ROUND = timedelta(minutes=15)
#: The least it waits after a pass that took nothing while a delivery is due already (another run holds the lock, or a
#: row is locked a moment): it never looks again at once.
IDLE_FLOOR = 5.0
#: The most it waits after a pass that failed (the database went away): when the next delivery is due is unknown.
RETRY_AFTER_FAILURE = 60.0
#: How long each reconciliation of a round may go on (seconds): asked between two businesses (``go_on``), so Hubs that
#: do not answer (10 s a call at most) never hold the deliveries, which wait in the same thread, for long; what is left
#: goes in the next round. As ``gateway.PASS_BUDGET``.
ROUND_BUDGET = 50.0


@dataclass(frozen=True)
class Periodic:
    """A pass the worker runs at each round: ``run(go_on=…)`` returns its counts, or ``None`` when another run holds its
    lock, and asks ``go_on`` between two businesses (``cut_short`` in its counts when it said no); ``failed`` says
    whether those counts leave work owed (its command ends with an error then)."""

    name: str
    run: Callable[..., Counter | None]
    failed: Callable[[Counter], bool]


PERIODIC = (
    Periodic("reconcile_hub_states", hubs_services.reconcile_exclusively, hubs_services.run_failed),
    Periodic(
        "reconcile_platform_invoices",
        billing_services.reconcile_platform_invoices_exclusively,
        billing_services.platform_run_failed,
    ),
)


def make_listener() -> Listener:
    return Listener(services.DELIVERY_CHANNEL)


def next_round(now: datetime) -> datetime:
    """The next quarter of an hour strictly after ``now``."""
    step = ROUND.total_seconds()
    return datetime.fromtimestamp((now.timestamp() // step + 1) * step, tz=UTC)


def run(
    stop: threading.Event,
    *,
    listener: Listener | None = None,
    clock: Callable[[], datetime] = timezone.now,
) -> int:
    """Drain the deliveries and run the rounds until ``stop`` is set; the process's exit code.

    ``listener`` is the LISTEN connection (``make_listener`` when missing; ``run_worker`` passes its own, which the
    signal handler wakes). ``clock()`` is now: a test's fake clock moves it."""
    ear = make_listener() if listener is None else listener
    try:
        ear.start()
        upcoming = next_round(clock())
        logger.info("saas.worker.started next_round=%s", upcoming.isoformat())
        _alive(upcoming)
        while not stop.is_set():
            counts, failed = _deliver(stop)
            if not stop.is_set() and clock() >= upcoming:
                _rounds(stop, clock)
                upcoming = next_round(clock())
                _alive(upcoming)
            if stop.is_set():
                break
            # What was notified until now is in the read that follows: no wake-up for it after the read.
            ear.drain()
            due, unknown = _next_due()
            close_old_connections()
            # A stop request that came during the drain had its wake-up taken by it: never sleep through it.
            if stop.is_set():
                break
            idle = counts is None or not any(counts.values())
            ear.wait(sleep_for(clock(), due, upcoming, idle=idle, failed=failed or unknown))
    except Exception:
        logger.exception("saas.worker.crashed")
        return 1
    finally:
        ear.close()
    logger.info("saas.worker.stopped")
    return 0


def sleep_for(now: datetime, due: datetime | None, upcoming: datetime, *, idle: bool, failed: bool) -> float:
    """Seconds until the next wake-up: the next delivery due or the next round, whichever comes first."""
    to_round = max((upcoming - now).total_seconds(), 0.0)
    if failed:
        return min(RETRY_AFTER_FAILURE, to_round)
    seconds = to_round if due is None else min(to_round, max((due - now).total_seconds(), 0.0))
    if seconds == 0 and idle:
        return min(IDLE_FLOOR, to_round)
    return seconds


def _alive(upcoming: datetime) -> None:
    """The worker's sign of life, at start and at every round (``LIVENESS``): the infra raises an alarm when it stops
    coming, a loop stuck without dying (the task has no health check)."""
    logger.info("%s next_round=%s", LIVENESS, upcoming.isoformat())


def _summary(counts) -> str:
    return " ".join(f"{key}={value}" for key, value in counts.items() if value)


def _failed(name: str, owed: str = "") -> None:
    if owed:
        logger.error("saas.worker.pass_failed task=%s left work owed: %s", name, owed)
    else:
        logger.exception("saas.worker.pass_failed task=%s", name)
    # A pass that failed may leave its connection broken: the next one opens another.
    close_old_connections()


def _deliver(stop: threading.Event) -> tuple[dict[str, int] | None, bool]:
    """The pass of the deliveries: its counts (``None``: another run holds its lock) and whether it failed."""
    try:
        counts = gateway.deliver_pass(stop)
    except Exception:
        _failed(DELIVERY)
        return None, True
    if counts is None:
        logger.info("saas.worker.pass_skipped task=%s: another run holds its lock", DELIVERY)
    elif any(counts.values()):
        logger.info("saas.worker.pass task=%s %s", DELIVERY, _summary(counts))
    return counts, False


def _next_due() -> tuple[datetime | None, bool]:
    """When the next delivery is due, and whether reading it failed."""
    try:
        return queries.delivery_next_due(services.platform_context(), NextDueIn()).at, False
    except Exception:
        _failed("whatsapp_next_due")
        return None, True


def _rounds(stop: threading.Event, clock: Callable[[], datetime]) -> None:
    for task in PERIODIC:
        if stop.is_set():
            return
        deadline = clock() + timedelta(seconds=ROUND_BUDGET)

        def go_on(deadline=deadline) -> bool:
            return not stop.is_set() and clock() < deadline

        try:
            counts = task.run(go_on=go_on)
        except Exception:
            _failed(task.name)
            continue
        if counts is None:
            logger.info("saas.worker.pass_skipped task=%s: another run holds its lock", task.name)
            continue
        if counts.get("cut_short"):
            logger.info("saas.worker.pass_cut task=%s: a stop request or its time ended it; the rest goes in the next round", task.name)
        if task.failed(counts):
            _failed(task.name, owed=_summary(counts))
        else:
            logger.info("saas.worker.pass task=%s %s", task.name, _summary(counts))
