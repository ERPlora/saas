"""The SaaS's worker (``base.worker``, ``manage.py run_worker``; saas#305): one process and one thread that drains the
WhatsApp deliveries to the Hub and runs the two reconciliations of every 15 minutes, and that between two wake-ups
sends nothing to the database (Aurora can go down to its minimum).

It wakes on the first of: a NOTIFY on ``whatsapp_delivery`` (a delivery parked, retried, held or made due, after its
COMMIT), the time of the next delivery due (``whatsapp.delivery.next_due``) and the next quarter of an hour (the
reconciliations, at :00, :15, :30 and :45). A pass that fails leaves its ERROR line (``saas.worker.pass_failed``, the
text the infra's metric filter looks for) and the loop goes on; a stop request ends it after the pass in course.
"""

import logging
import threading
import time
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from base import worker
from base.listener import Listener
from base.tests.conftest import other_session  # noqa: F401 - a second session, as another process
from hubs.tests.test_guardrails import database_touches
from whatsapp import gateway, queries, services
from whatsapp.models import Delivery
from whatsapp.schemas import NextDueOut
from whatsapp.tests.conftest import (  # noqa: F401 - the fixtures of a business with its number
    business,
    hub_double,
    make_user,
    offline_hub,
    owner,
    plans,
    whatsapp_on,
)
from whatsapp.tests.test_gateway import number  # noqa: F401 - shared fixture
from whatsapp.tests.test_parse import messages, text
from whatsapp.tests.test_services import ingest

INBOUND = r"^/internal/whatsapp/inbound$"
NOTHING = dict.fromkeys(gateway.COUNTS, 0)
TEN_O_SEVEN = datetime(2026, 11, 5, 10, 7, tzinfo=UTC)
DELIVER_LOCK = "hashtext('erplora.saas.whatsapp_deliver')"


class Clock:
    """The worker's clock (``run(clock=…)``), moved by hand."""

    def __init__(self, at: datetime):
        self.now = at

    def __call__(self) -> datetime:
        return self.now


class Ear:
    """A listener that hears nothing: each wait moves the clock by the time asked (when it has one), notes it and
    stops the loop after ``waits`` of them; ``on_wait`` runs at each one."""

    def __init__(self, stop: threading.Event, waits: int, clock: Clock | None = None, on_wait=lambda timeout: None):
        self.stop, self.waits, self.clock, self.on_wait = stop, waits, clock, on_wait
        self.timeouts: list[float] = []
        self.started = self.closed = False

    def start(self) -> bool:
        self.started = True
        return True

    def drain(self) -> bool:
        return False

    def wait(self, timeout: float) -> bool:
        self.timeouts.append(timeout)
        self.on_wait(timeout)
        if self.clock is not None:
            self.clock.now += timedelta(seconds=timeout)
        if len(self.timeouts) >= self.waits:
            self.stop.set()
        return False

    def interrupt(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def quiet_deliveries(monkeypatch):
    """No delivery to push and none due: the passes of the reconciliations alone."""
    passes: list[object] = []
    monkeypatch.setattr(gateway, "deliver_pass", lambda stop=None: passes.append(stop) or dict(NOTHING))
    monkeypatch.setattr(queries, "delivery_next_due", lambda ctx, data: NextDueOut(at=None))
    return passes


@pytest.fixture
def keep_the_connection(monkeypatch):
    """``close_old_connections`` would end the test's transaction (its autocommit differs): noted, not run."""
    closes: list[int] = []
    monkeypatch.setattr(worker, "close_old_connections", lambda: closes.append(1))
    return closes


def recorder(name, ran, clock, counts=None):
    def run():
        ran.append((name, clock.now))
        return Counter(counts or {"delivered": 0})

    return run


# --- The cadence ------------------------------------------------------------------------------------------------


def test_the_two_reconciliations_run_every_quarter_of_an_hour_in_the_process(monkeypatch, quiet_deliveries):
    clock, stop, ran = Clock(TEN_O_SEVEN), threading.Event(), []
    monkeypatch.setattr(
        worker,
        "PERIODIC",
        (
            worker.Periodic("reconcile_hub_states", recorder("hubs", ran, clock), lambda counts: False),
            worker.Periodic("reconcile_platform_invoices", recorder("billing", ran, clock), lambda counts: False),
        ),
    )
    ear = Ear(stop, waits=5, clock=clock)

    assert worker.run(stop, listener=ear, clock=clock) == 0

    quarters = [TEN_O_SEVEN.replace(minute=15) + timedelta(minutes=15 * n) for n in range(4)]
    assert ran == [(name, at) for at in quarters for name in ("hubs", "billing")]
    assert ear.timeouts == [480, 900, 900, 900, 900]
    assert len(quiet_deliveries) == 5
    assert ear.started and ear.closed


def test_the_real_reconciliations_are_the_ones_of_the_commands():
    from billing import services as billing_services
    from hubs import services as hubs_services

    assert [(task.name, task.run, task.failed) for task in worker.PERIODIC] == [
        ("reconcile_hub_states", hubs_services.reconcile_exclusively, hubs_services.run_failed),
        (
            "reconcile_platform_invoices",
            billing_services.reconcile_platform_invoices_exclusively,
            billing_services.platform_run_failed,
        ),
    ]
    assert worker.ROUND == timedelta(minutes=15)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 5, 10, 7, 30, tzinfo=UTC), datetime(2026, 11, 5, 10, 15, tzinfo=UTC)),
        (datetime(2026, 11, 5, 10, 15, tzinfo=UTC), datetime(2026, 11, 5, 10, 30, tzinfo=UTC)),
        (datetime(2026, 11, 5, 23, 59, 59, tzinfo=UTC), datetime(2026, 11, 6, 0, 0, tzinfo=UTC)),
    ],
)
def test_the_next_round_is_the_next_quarter_of_an_hour_after_now(now, expected):
    assert worker.next_round(now) == expected


# --- When it wakes ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("due_in", "pushed", "expected"),
    [
        (None, 0, 480.0),  # nothing waits: until the next round
        (42.0, 0, 42.0),  # a retry in 42 s: then
        (-3.0, 1, 0.0),  # due already, after a pass that pushed (its budget ran out): again at once
        (-3.0, 0, worker.IDLE_FLOOR),  # due already, yet the pass took nothing (another holds it): soon, not at once
    ],
)
def test_it_sleeps_until_the_next_delivery_due_or_the_next_round(monkeypatch, due_in, pushed, expected):
    clock, stop = Clock(TEN_O_SEVEN), threading.Event()
    due = None if due_in is None else TEN_O_SEVEN + timedelta(seconds=due_in)
    monkeypatch.setattr(gateway, "deliver_pass", lambda stop=None: {**NOTHING, "delivered": pushed})
    monkeypatch.setattr(queries, "delivery_next_due", lambda ctx, data: NextDueOut(at=due))
    monkeypatch.setattr(worker, "PERIODIC", ())
    ear = Ear(stop, waits=1)

    worker.run(stop, listener=ear, clock=clock)

    assert ear.timeouts == [expected]


def test_a_failed_pass_is_logged_and_the_loop_goes_on(monkeypatch, caplog):
    clock, stop, calls = Clock(TEN_O_SEVEN), threading.Event(), []

    def deliver_pass(stop=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the database went away")
        return dict(NOTHING)

    monkeypatch.setattr(gateway, "deliver_pass", deliver_pass)
    monkeypatch.setattr(queries, "delivery_next_due", lambda ctx, data: NextDueOut(at=None))
    monkeypatch.setattr(worker, "PERIODIC", ())
    ear = Ear(stop, waits=2, clock=clock)

    with caplog.at_level(logging.INFO, logger="base.worker"):
        assert worker.run(stop, listener=ear, clock=clock) == 0

    (failure,) = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert failure.getMessage() == "saas.worker.pass_failed task=whatsapp_deliver"
    assert failure.exc_info is not None
    assert len(calls) == 2
    assert ear.timeouts[0] == worker.RETRY_AFTER_FAILURE  # it does not wait for the round to look again


def test_a_reconciliation_that_leaves_work_owed_or_crashes_is_logged_and_the_other_still_runs(
    monkeypatch, quiet_deliveries, caplog
):
    clock, stop, ran = Clock(TEN_O_SEVEN.replace(minute=14, second=59)), threading.Event(), []

    def crashes():
        raise RuntimeError("boom")

    monkeypatch.setattr(
        worker,
        "PERIODIC",
        (
            worker.Periodic("reconcile_hub_states", crashes, lambda counts: False),
            worker.Periodic(
                "reconcile_platform_invoices",
                recorder("billing", ran, clock, {"unreachable": 2}),
                lambda counts: counts["unreachable"] > 0,
            ),
        ),
    )
    ear = Ear(stop, waits=2, clock=clock)

    with caplog.at_level(logging.INFO, logger="base.worker"):
        assert worker.run(stop, listener=ear, clock=clock) == 0

    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert errors == [
        "saas.worker.pass_failed task=reconcile_hub_states",
        "saas.worker.pass_failed task=reconcile_platform_invoices left work owed: unreachable=2",
    ]
    assert len(ran) == 1


def test_a_reconciliation_another_run_holds_is_skipped_without_an_error(monkeypatch, quiet_deliveries, caplog):
    clock, stop = Clock(TEN_O_SEVEN.replace(minute=14, second=59)), threading.Event()
    monkeypatch.setattr(worker, "PERIODIC", (worker.Periodic("reconcile_hub_states", lambda: None, lambda c: True),))

    with caplog.at_level(logging.INFO, logger="base.worker"):
        worker.run(stop, listener=Ear(stop, waits=2, clock=clock), clock=clock)

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert "saas.worker.pass_skipped task=reconcile_hub_states" in caplog.text


def test_a_stop_asked_during_the_pass_ends_the_loop_after_it(monkeypatch):
    stop, finished = threading.Event(), []

    def deliver_pass(stop_asked=None):
        stop.set()
        finished.append(stop_asked)
        return dict(NOTHING)

    monkeypatch.setattr(gateway, "deliver_pass", deliver_pass)
    monkeypatch.setattr(worker, "PERIODIC", ())
    ear = Ear(stop, waits=99)

    assert worker.run(stop, listener=ear, clock=Clock(TEN_O_SEVEN)) == 0
    assert finished == [stop]  # the pass hears the stop itself (it ends after the push in course)
    assert ear.timeouts == [] and ear.closed


def test_a_crash_outside_the_passes_ends_the_worker_with_an_error(monkeypatch, quiet_deliveries, caplog):
    stop = threading.Event()
    monkeypatch.setattr(worker, "PERIODIC", ())
    ear = Ear(stop, waits=99)

    def broken(timeout):
        raise RuntimeError("a bug")

    ear.wait = broken

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, listener=ear, clock=Clock(TEN_O_SEVEN)) == 1

    assert "saas.worker.crashed" in caplog.text
    assert ear.closed


# --- Against the database ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_with_nothing_due_it_sleeps_until_the_next_round_without_a_query(keep_the_connection, monkeypatch):
    monkeypatch.setattr(worker, "PERIODIC", ())
    stop, seen = threading.Event(), []
    ear = Listener(services.DELIVERY_CHANNEL)

    def wait(timeout):
        with CaptureQueriesContext(connection) as during:
            Listener.wait(ear, min(timeout, 0.3))
        seen.append((timeout, len(during)))
        stop.set()
        return False

    ear.wait = wait

    assert worker.run(stop, listener=ear, clock=Clock(TEN_O_SEVEN)) == 0

    assert seen == [(480.0, 0)]
    assert keep_the_connection  # its connections released before it sleeps


@pytest.mark.django_db
def test_it_does_not_push_before_the_retry_time_and_pushes_once_it_came(
    number, hub_double, keep_the_connection, monkeypatch
):
    monkeypatch.setattr(worker, "PERIODIC", ())
    hub_double.answer("POST", INBOUND, 200, {"created": True})
    ingest(messages(text("wamid.1")))
    Delivery.objects.update(attempts=1, next_attempt_at=timezone.now() + timedelta(seconds=0.5))
    stop, seen = threading.Event(), []
    ear = Listener(services.DELIVERY_CHANNEL)

    def wait(timeout):
        seen.append((round(timeout, 1), len(hub_double.calls_to("POST", "/internal/whatsapp/inbound"))))
        if len(seen) == 2:
            stop.set()
            return False
        return Listener.wait(ear, timeout)

    ear.wait = wait

    assert worker.run(stop, listener=ear) == 0

    (first_timeout, before), (_, after) = seen
    assert 0 < first_timeout <= 0.5 and before == 0
    assert after == 1
    assert Delivery.objects.get().delivered_at is not None


@pytest.mark.django_db
def test_while_another_run_holds_the_lock_it_looks_again_in_a_few_seconds_not_at_once(
    number, hub_double, keep_the_connection, monkeypatch, other_session
):
    monkeypatch.setattr(worker, "PERIODIC", ())
    ingest(messages(text("wamid.1")))
    other_session.execute(f"SELECT pg_advisory_lock({DELIVER_LOCK})")
    stop = threading.Event()
    ear = Ear(stop, waits=1)
    try:
        worker.run(stop, listener=ear)
    finally:
        other_session.execute(f"SELECT pg_advisory_unlock({DELIVER_LOCK})")

    assert ear.timeouts == [worker.IDLE_FLOOR]
    assert hub_double.calls == []


@pytest.mark.django_db(transaction=True)
def test_it_delivers_a_parked_message_as_soon_as_its_notify_comes(number, hub_double):
    hub_double.answer("POST", INBOUND, 200, {"created": True})
    stop, sleeping, timeouts = threading.Event(), threading.Event(), []
    ear = Listener(services.DELIVERY_CHANNEL)

    def wait(timeout):
        timeouts.append(timeout)
        sleeping.set()
        return Listener.wait(ear, timeout)

    ear.wait = wait
    errors: list[BaseException] = []

    def meta_reports_a_message():
        try:
            sleeping.wait(10)
            ingest(messages(text("wamid.1")))  # parked, and its NOTIFY after the COMMIT: the push is the worker's
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not Delivery.objects.filter(delivered_at__isnull=False).exists():
                time.sleep(0.05)
        except BaseException as error:  # noqa: BLE001 - surfaced by the assert below
            errors.append(error)
        finally:
            stop.set()
            ear.interrupt()
            connection.close()

    meta = threading.Thread(target=meta_reports_a_message)
    meta.start()
    started = time.monotonic()
    code = worker.run(stop, listener=ear, clock=Clock(TEN_O_SEVEN))
    meta.join(15)

    assert errors == [] and code == 0
    assert Delivery.objects.get().delivered_at is not None
    assert timeouts[0] == 480  # it slept until the next round, not a tick: the NOTIFY woke it
    assert time.monotonic() - started < 10


@pytest.mark.django_db(transaction=True)
def test_what_its_own_pass_notified_does_not_wake_it_again(number, offline_hub, monkeypatch):
    """The retry its own pass recorded notifies the channel after its COMMIT; it is taken before the read of the next
    due (``drain``), so the worker sleeps until that retry instead of waking at once for an empty pass."""
    monkeypatch.setattr(worker, "PERIODIC", ())
    ingest(messages(text("wamid.1")))
    stop, seen = threading.Event(), []
    ear = Listener(services.DELIVERY_CHANNEL)

    def wait(timeout):
        seen.append((timeout, Listener.wait(ear, min(timeout, 1.0))))
        stop.set()
        return False

    ear.wait = wait

    assert worker.run(stop, listener=ear) == 0

    ((timeout, woke),) = seen
    assert Delivery.objects.get().attempts == 1
    assert 0 < timeout <= services.FIRST_WAIT.total_seconds() + 0.5
    assert woke is False


# --- The rules of the module ------------------------------------------------------------------------------------


@pytest.mark.parametrize("module", [worker, __import__("base.listener", fromlist=["Listener"])])
def test_the_loop_and_its_ear_touch_no_orm(module):
    """The worker calls the operations and the passes of the apps (the ORM is only in ``services.py`` and
    ``queries.py``); its ear is a psycopg connection of its own."""
    with open(module.__file__, encoding="utf-8") as source:
        assert database_touches(source.read()) == []
