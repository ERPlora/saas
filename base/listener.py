"""The ``saas-worker``'s ear (saas#305): one psycopg connection of its own, outside Django and the ORM, that LISTENs
on a channel, and the wait on its socket.

Between two wake-ups the worker sends nothing to the database, so Aurora can go down to its minimum: ``wait`` is a
``select`` on the connection's socket and on a pipe ``interrupt`` writes to (the stop request's signal handler), for
the time the worker asks at most. A lost connection wakes it (what was notified meanwhile is unknown, so the worker
looks: ``True``) and the next ``wait`` connects again, also ``True``. One it cannot make is logged at ERROR
(``saas.worker.listen_failed``) and tried again after a pause that doubles (``BACKOFF``: 1 s first, 60 s at most,
never longer than the wait asked for), never raised. Its connection string is the database's
(``live.broker.control_conninfo``, the same the live listener of the web uses), with its own ``application_name``.
"""

import logging
import os
import select
import time
from collections.abc import Callable

import psycopg
from live.broker import control_conninfo
from psycopg import sql

logger = logging.getLogger(__name__)

APPLICATION_NAME = "saas-worker-listener"
#: TCP keepalives, so a connection dropped without a word (a failover) is noticed within about a minute.
KEEPALIVES = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3}
#: The pause after a connection it could not make: the first, and the longest it doubles up to (seconds).
BACKOFF = (1.0, 60.0)


def connect() -> psycopg.Connection:
    return psycopg.connect(control_conninfo(), autocommit=True, application_name=APPLICATION_NAME, **KEEPALIVES)


class Listener:
    """``LISTEN channel`` on a connection of its own, and the wait for a notification on it."""

    def __init__(
        self,
        channel: str,
        *,
        connect: Callable[[], psycopg.Connection] = connect,
        backoff: tuple[float, float] = BACKOFF,
    ) -> None:
        self.channel = channel
        self._connect = connect
        self._first_pause, self._longest_pause = backoff
        self._pause = self._first_pause
        self._conn: psycopg.Connection | None = None
        self._read, self._write = os.pipe()
        os.set_blocking(self._read, False)
        os.set_blocking(self._write, False)

    @property
    def pid(self) -> int | None:
        """The backend process of its connection (``pg_stat_activity.pid``), while it has one."""
        return None if self._conn is None else self._conn.info.backend_pid

    def start(self) -> bool:
        """LISTEN now; whether it could (when not, the next ``wait`` tries again)."""
        return self._listen()

    def interrupt(self) -> None:
        """Wake the wait in course, or the next one, at once: safe in a signal handler."""
        try:
            os.write(self._write, b"\0")
        except BlockingIOError:
            pass  # The pipe is full: a wake-up is pending already.
        except OSError:
            pass  # The listener is closed: the worker has ended, there is no wait to wake.

    def wait(self, timeout: float) -> bool:
        """Sleep until a notification on the channel, an ``interrupt`` or ``timeout`` seconds; ``True`` when a
        notification came or the connection was lost or made again (the worker then looks), ``False`` otherwise."""
        return self._wait(timeout)

    def drain(self) -> bool:
        """Take, without waiting, what was notified until now; whether anything was (or the connection changed)."""
        return self._wait(0.0)

    def _wait(self, timeout: float) -> bool:
        deadline = time.monotonic() + max(timeout, 0.0)
        if self._conn is None:
            if self._listen():
                return True
            self._sleep(min(max(timeout, 0.0), self._pause))
            self._pause = min(self._pause * 2, self._longest_pause)
            return False
        socket = self._conn.fileno()
        while True:
            remaining = max(deadline - time.monotonic(), 0.0)
            ready, _, _ = select.select([socket, self._read], [], [], remaining)
            if self._read in ready:
                self._drain_pipe()
                return False
            if socket not in ready:
                return False
            try:
                heard = self._take_notifications()
            except psycopg.Error as error:
                logger.error("saas.worker.listen_lost channel=%s: %s", self.channel, error)
                self._drop()
                return True
            if heard:
                return True
            if self._conn.closed:
                logger.error("saas.worker.listen_lost channel=%s: the server closed the connection", self.channel)
                self._drop()
                return True
            if remaining <= 0:
                return False

    def close(self) -> None:
        self._drop()
        for fd in (self._read, self._write):
            try:
                os.close(fd)
            except OSError:
                pass  # Closed already: close() runs once per listener, and again on the way out.

    def _listen(self) -> bool:
        conn = None
        try:
            conn = self._connect()
            conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(self.channel)))
        except psycopg.Error as error:
            logger.error("saas.worker.listen_failed channel=%s: %s", self.channel, error)
            if conn is not None:
                conn.close()
            return False
        self._conn = conn
        self._pause = self._first_pause
        logger.info("saas.worker.listening channel=%s pid=%s", self.channel, conn.info.backend_pid)
        return True

    def _take_notifications(self) -> bool:
        pgconn = self._conn.pgconn
        pgconn.consume_input()
        heard = False
        while pgconn.notifies() is not None:
            heard = True
        return heard

    def _sleep(self, seconds: float) -> None:
        ready, _, _ = select.select([self._read], [], [], seconds)
        if ready:
            self._drain_pipe()

    def _drain_pipe(self) -> None:
        try:
            while os.read(self._read, 64):
                pass
        except BlockingIOError:
            pass  # Emptied: every pending wake-up taken at once.

    def _drop(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
