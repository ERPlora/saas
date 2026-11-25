"""The ``saas-worker``'s ear (``base.listener``, saas#305): a psycopg connection of its own that LISTENs on a channel
and waits on its socket. Between two wake-ups nothing goes to the database (Aurora can go down to its minimum): the
wait is a ``select`` on the connection and on a pipe a stop request writes to.

- a NOTIFY on its channel wakes it before its time, and one on another channel does not;
- the time up, it returns ``False`` having sent nothing: neither through Django's connection nor through its own;
- ``interrupt`` (the stop request's signal handler) wakes it at once, also when it came before the wait;
- an interrupt goes before a notification that came with it, which waits for the next wait;
- what reaches its socket and is no notification neither wakes it nor lengthens the wait;
- a lost connection wakes it (what was notified meanwhile is unknown: the worker looks), and the next wait connects
  again;
- a database it cannot reach is logged (``saas.worker.listen_failed``) and tried again after a pause that grows up to
  its cap, never raised.
"""

import logging
import select
import threading
import time
from types import SimpleNamespace

import psycopg
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from base.listener import Listener
from base.tests.conftest import other_session  # noqa: F401 - a second session, as another process

pytestmark = pytest.mark.django_db
CHANNEL = "worker_test"


@pytest.fixture
def listener():
    ear = Listener(CHANNEL)
    yield ear
    ear.close()


def timed(wait, seconds):
    started = time.monotonic()
    woke = wait(seconds)
    return woke, time.monotonic() - started


def test_a_notify_on_its_channel_wakes_it_before_its_time(listener, other_session):
    assert listener.start() is True
    other_session.execute(f"NOTIFY {CHANNEL}")

    woke, took = timed(listener.wait, 10)

    assert woke is True and took < 5
    assert listener.wait(0) is False


def on_its_socket(listener, seconds):
    """Wait, ``seconds`` at most, until something reached the listener's socket, leaving it there unread."""
    ready, _, _ = select.select([listener._conn.fileno()], [], [], seconds)
    return bool(ready)


def test_drain_takes_what_was_notified_without_waiting(listener, other_session):
    listener.start()
    with other_session.transaction():  # one commit: both reach the listener in the same write, neither comes late
        other_session.execute(f"NOTIFY {CHANNEL}")
        other_session.execute(f"NOTIFY {CHANNEL}, 'again'")
    assert on_its_socket(listener, 10)  # a NOTIFY takes its time to arrive (saas#323): wait for it, not for drain()

    woke, took = timed(lambda _: listener.drain(), None)
    assert woke is True and took < 0.5
    woke, took = timed(lambda _: listener.drain(), None)
    assert woke is False and took < 0.5


def test_an_interrupt_after_the_close_is_harmless():
    ear = Listener(CHANNEL)
    ear.close()

    ear.interrupt()


def test_a_notify_on_another_channel_does_not_wake_it(listener, other_session):
    listener.start()
    other_session.execute("NOTIFY some_other_channel")

    assert timed(listener.wait, 0.3)[0] is False


def test_the_time_up_it_returns_having_sent_nothing_to_the_database(listener, other_session):
    listener.start()

    with CaptureQueriesContext(connection) as through_django:
        woke, took = timed(listener.wait, 0.3)

    assert woke is False and 0.25 <= took < 3
    assert len(through_django) == 0
    query, state = other_session.execute(
        "SELECT query, state FROM pg_stat_activity WHERE pid = %s", [listener.pid]
    ).fetchone()
    assert query.startswith("LISTEN") and state == "idle"


def test_interrupt_wakes_a_long_wait_at_once(listener):
    listener.start()
    threading.Timer(0.2, listener.interrupt).start()

    woke, took = timed(listener.wait, 30)

    assert woke is False and took < 5


def test_an_interrupt_before_the_wait_is_not_lost(listener):
    listener.start()
    listener.interrupt()
    listener.interrupt()

    assert timed(listener.wait, 30)[1] < 1


def test_an_interrupt_wakes_one_wait_only(listener):
    listener.start()
    listener.interrupt()
    assert listener.wait(30) is False

    woke, took = timed(listener.wait, 0.3)

    assert woke is False and took >= 0.25


def test_an_interrupt_goes_before_a_notification_that_waits_for_the_next_wait(listener, other_session):
    listener.start()
    other_session.execute(f"NOTIFY {CHANNEL}")
    assert on_its_socket(listener, 10)
    listener.interrupt()

    assert listener.wait(10) is False
    assert listener.wait(10) is True


def test_a_wait_of_less_than_nothing_returns_at_once(listener):
    listener.start()

    woke, took = timed(listener.wait, -20)

    assert woke is False and took < 5


def test_a_lost_connection_wakes_it_and_the_next_wait_listens_again(listener, other_session, caplog):
    listener.start()
    lost = listener.pid
    other_session.execute("SELECT pg_terminate_backend(%s)", [lost])

    with caplog.at_level(logging.ERROR, logger="base.listener"):
        woke, took = timed(listener.wait, 10)

    assert woke is True and took < 5
    assert "saas.worker.listen_lost" in caplog.text
    assert listener.wait(10) is True  # listening again: what was notified meanwhile is unknown
    assert listener.pid not in (None, lost)
    other_session.execute(f"NOTIFY {CHANNEL}")
    assert listener.wait(10) is True
    assert listener.wait(0.2) is False


def test_a_database_it_cannot_reach_is_logged_and_tried_again_after_a_growing_pause(caplog):
    tries: list[float] = []
    asked: list[float] = []

    def unreachable():
        tries.append(time.monotonic())
        raise psycopg.OperationalError("connection refused")

    ear = Listener(CHANNEL, connect=unreachable, backoff=(0.05, 0.2))

    def sleep(seconds):
        # The pause it asks for, noted; the real one still runs (as test_worker wraps ``ear.wait``).
        asked.append(seconds)
        Listener._sleep(ear, seconds)

    ear._sleep = sleep
    try:
        with caplog.at_level(logging.ERROR, logger="base.listener"):
            assert ear.start() is False
            waits = [timed(ear.wait, 10) for _ in range(4)]
    finally:
        ear.close()

    assert len(tries) == 5
    assert caplog.text.count("saas.worker.listen_failed") == 5
    # The pause doubles up to its cap: what it asks for, which a loaded machine cannot change.
    assert asked == pytest.approx([0.05, 0.1, 0.2, 0.2])
    # And it does sleep it: a select nobody wakes never returns before its time; load only makes it longer.
    assert [woke for woke, _ in waits] == [False] * 4
    assert all(took >= pause for (_, took), pause in zip(waits, asked, strict=True))
    # Yet not much longer than its cap (0.2 s): a wide margin load stays under (0.55 s at most, measured in the
    # background QoS under load), which a sleep longer than what it asked for does not.
    assert waits[-1][1] < 1
    assert all(record.levelno == logging.ERROR for record in caplog.records)


def test_a_pause_never_outlasts_the_wait_asked_for(caplog):
    def unreachable():
        raise psycopg.OperationalError("connection refused")

    ear = Listener(CHANNEL, connect=unreachable, backoff=(30.0, 60.0))
    try:
        assert timed(ear.wait, 0.2)[1] < 2
    finally:
        ear.close()


def test_without_a_connection_a_wait_of_less_than_nothing_does_not_pause(caplog):
    def unreachable():
        raise psycopg.OperationalError("connection refused")

    ear = Listener(CHANNEL, connect=unreachable, backoff=(30.0, 60.0))
    try:
        woke, took = timed(ear.wait, -20)
    finally:
        ear.close()

    assert woke is False and took < 5


def test_the_wait_connects_when_the_start_could_not(other_session):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise psycopg.OperationalError("connection refused")
        return psycopg.connect(**_params(), autocommit=True)

    ear = Listener(CHANNEL, connect=flaky, backoff=(0.05, 0.2))
    try:
        assert ear.start() is False
        assert ear.wait(10) is True  # listening now: it looks once
        other_session.execute(f"NOTIFY {CHANNEL}")
        assert ear.wait(10) is True
    finally:
        ear.close()


SOCKET = object()


class Wire:
    """What the listener hears through, as a test scripts it turn by turn: a connection (psycopg's part of it), the
    clock and ``select``, which answers at once and notes the wait it was asked for. A turn reads as ``(seconds it
    took, what came of it)``: a number of notifications, ``"closed"``, an error, or ``None`` when nothing came."""

    def __init__(self, monkeypatch):
        self.now = 0.0
        self.turns = []
        self.asked = []
        self.came = None
        self.closed = False
        self.info = SimpleNamespace(backend_pid=1)
        self.pgconn = SimpleNamespace(consume_input=self.consume_input, notifies=self.notifies)
        monkeypatch.setattr("base.listener.time", SimpleNamespace(monotonic=lambda: self.now))
        monkeypatch.setattr("base.listener.select", SimpleNamespace(select=self.select))

    def fileno(self):
        return SOCKET

    def execute(self, query):
        pass

    def close(self):
        self.closed = True

    def select(self, readers, _writers, _failed, timeout):
        self.asked.append(timeout)
        took, self.came = self.turns.pop(0)
        self.now += took
        return ([] if self.came is None else [SOCKET]), [], []

    def consume_input(self):
        if isinstance(self.came, Exception):
            raise self.came
        self.closed = self.came == "closed"

    def notifies(self):
        if isinstance(self.came, int) and self.came > 0:
            self.came -= 1
            return object()
        return None


class TestWhatReachesItsSocket:
    @pytest.fixture
    def wire(self, monkeypatch):
        return Wire(monkeypatch)

    @pytest.fixture
    def ear(self, wire):
        ear = Listener(CHANNEL, connect=lambda: wire)
        ear.start()
        yield ear
        ear.close()

    def test_the_wait_asked_for_is_the_one_waited(self, wire, ear):
        wire.turns = [(10, None)]

        assert ear.wait(10) is False
        assert wire.asked == [10]

    def test_what_is_no_notification_neither_wakes_it_nor_lengthens_the_wait(self, wire, ear):
        wire.turns = [(4, 0), (5, 0), (1, None)]

        assert ear.wait(10) is False
        assert wire.asked == [10, 6, 1]

    def test_a_notification_after_something_else_wakes_it(self, wire, ear):
        wire.turns = [(4, 0), (1, 1)]

        assert ear.wait(10) is True
        assert wire.asked == [10, 6]

    def test_past_its_time_it_looks_once_more(self, wire, ear):
        wire.turns = [(12, 0), (0, 1)]

        assert ear.wait(10) is True
        assert wire.asked == [10, 0]

    def test_a_socket_that_never_goes_quiet_does_not_hold_it_past_its_time(self, wire, ear):
        wire.turns = [(0, 0), (0, 1)]

        assert ear.drain() is False
        assert wire.asked == [0]

    def test_every_notification_that_came_is_taken_at_once(self, wire, ear):
        wire.turns = [(1, 3), (9, None)]

        assert ear.wait(10) is True
        assert wire.came == 0

    def test_a_connection_the_server_closed_wakes_it_and_the_next_wait_listens_again(self, wire, ear, caplog):
        wire.turns = [(1, "closed")]

        with caplog.at_level(logging.INFO, logger="base.listener"):
            assert ear.wait(10) is True
            assert ear.pid is None
            assert ear.wait(10) is True

        assert ear.pid == 1
        assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
            (logging.ERROR, f"saas.worker.listen_lost channel={CHANNEL}: the server closed the connection"),
            (logging.INFO, f"saas.worker.listening channel={CHANNEL} pid=1"),
        ]

    def test_a_connection_that_breaks_wakes_it_closed_and_logged(self, wire, ear, caplog):
        wire.turns = [(1, psycopg.OperationalError("the network went"))]

        with caplog.at_level(logging.INFO, logger="base.listener"):
            assert ear.wait(10) is True

        assert (ear.pid, wire.closed) == (None, True)
        assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
            (logging.ERROR, f"saas.worker.listen_lost channel={CHANNEL}: the network went")
        ]

    def test_an_error_that_is_not_the_connection_s_is_raised(self, wire, ear):
        wire.turns = [(1, RuntimeError("a bug"))]

        with pytest.raises(RuntimeError):
            ear.wait(10)

    def test_connected_again_the_pause_starts_over(self, wire, caplog):
        answers = [psycopg.OperationalError("refused"), psycopg.OperationalError("refused"), wire]

        def connect():
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        ear = Listener(CHANNEL, connect=connect, backoff=(1.0, 60.0))
        wire.turns = [(1, None), (2, None), (1, "closed"), (1, None)]
        assert [ear.wait(10), ear.wait(10)] == [False, False]
        assert (ear.wait(10), ear.wait(10)) == (True, True)
        answers.append(psycopg.OperationalError("refused"))

        assert ear.wait(10) is False

        assert wire.asked == [1, 2, 10, 1]
        ear.close()


def _params() -> dict:
    db = connection.settings_dict
    return {
        "dbname": db["NAME"], "user": db["USER"], "password": db["PASSWORD"], "host": db["HOST"], "port": db["PORT"]
    }
