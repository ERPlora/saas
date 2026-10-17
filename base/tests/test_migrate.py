"""``manage.py migrate`` under a Postgres advisory lock (aws README, «Comandos ``manage.py``»:
``migrate --noinput`` in ``saas-migrate``, «con advisory lock»): two deploys never migrate the SaaS
database at once. The lock, ``pg_advisory_lock(hashtext('erplora.saas.migrate'))``, is a session lock
on a connection of its own, held for the whole run and released at its end, also when it fails.

Django's own migrate is replaced by a recorder in most of these tests: they are about the lock
around it. pytest-django creates the test database through this same command, so the whole suite
proves that it still migrates.
"""

import threading
from io import StringIO
from types import SimpleNamespace

import psycopg
import pytest
from django.core.management import call_command, get_commands
from django.core.management.commands import migrate as django_migrate

from base.management.commands import migrate as base_migrate

LOCK_KEY = "hashtext('erplora.saas.migrate')"


def try_lock(session) -> bool:
    """Whether ``session`` gets the lock now; if it does, it lets it go at once."""
    taken = session.execute(f"SELECT pg_try_advisory_lock({LOCK_KEY})").fetchone()[0]
    if taken:
        session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
    return taken


@pytest.fixture
def migrations_run(monkeypatch):
    """Django's migrate replaced by a recorder; set once it starts migrating."""
    started = threading.Event()

    def handle(self, *args, **options):
        started.set()

    monkeypatch.setattr(django_migrate.Command, "handle", handle)
    return started


@pytest.fixture
def failed_migrations(monkeypatch):
    """Django's migrate replaced by one whose migration 0042 fails."""

    def handle(self, *args, **options):
        raise RuntimeError("migration 0042 failed")

    monkeypatch.setattr(django_migrate.Command, "handle", handle)


class _ClosingSession:
    """A lock session whose close the run has asked for and Postgres has not carried out yet."""

    def __init__(self, session):
        self.session = session
        self.close_asked = False

    def __getattr__(self, name):
        return getattr(self.session, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close_asked = True

    def close(self):
        self.close_asked = True


@pytest.fixture
def lock_sessions(monkeypatch):
    """The lock sessions the run opens, still alive after it until the test ends.

    Closing a connection only asks Postgres to end its session: the session, and the locks it
    holds, go a moment later, and another task asking in that moment finds the lock taken (the
    SaaS's CI did, in run 38990277326). Here that moment lasts until the test ends, so only a
    release before the close frees the lock in time.
    """
    sessions = []

    def connect(*args, **kwargs):
        sessions.append(_ClosingSession(psycopg.connect(*args, **kwargs)))
        return sessions[-1]

    monkeypatch.setattr(base_migrate, "psycopg", SimpleNamespace(connect=connect))
    yield sessions
    for closing in sessions:
        closing.session.close()


def test_migrate_is_bases():
    assert get_commands()["migrate"] == "base"


def test_a_second_migrate_waits_for_the_one_that_holds_the_lock(
    migrations_run, other_session
):
    other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
    out = StringIO()
    errors = []

    def second_task():
        try:
            call_command("migrate", verbosity=0, stdout=out)
        except Exception as exc:  # noqa: BLE001 - reported by the assertion below
            errors.append(exc)

    thread = threading.Thread(target=second_task)
    thread.start()
    try:
        # It does not migrate while the other task holds the lock...
        assert not migrations_run.wait(timeout=1.5)
    finally:
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
    # ...and migrates as soon as it is released.
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert errors == []
    assert migrations_run.is_set()
    assert "waiting" in out.getvalue()


def test_the_lock_is_held_while_migrating(monkeypatch, other_session):
    seen = {}

    def handle(self, *args, **options):
        seen["another_task_gets_the_lock"] = try_lock(other_session)

    monkeypatch.setattr(django_migrate.Command, "handle", handle)

    call_command("migrate", verbosity=0)

    assert seen == {"another_task_gets_the_lock": False}


def test_the_lock_is_released_after_the_run(migrations_run, other_session):
    call_command("migrate", verbosity=0)

    assert migrations_run.is_set()
    assert try_lock(other_session) is True


def test_a_failed_migration_releases_the_lock(failed_migrations, other_session):
    with pytest.raises(RuntimeError, match="0042"):
        call_command("migrate", verbosity=0)

    assert try_lock(other_session) is True


def test_the_lock_is_free_when_the_run_ends_even_before_its_session_does(
    migrations_run, lock_sessions, other_session
):
    call_command("migrate", verbosity=0)

    assert migrations_run.is_set()
    assert try_lock(other_session) is True
    assert [session.close_asked for session in lock_sessions] == [True]


def test_a_failed_run_frees_the_lock_even_before_its_session_ends(
    failed_migrations, lock_sessions, other_session
):
    with pytest.raises(RuntimeError, match="0042"):
        call_command("migrate", verbosity=0)

    assert try_lock(other_session) is True
    assert [session.close_asked for session in lock_sessions] == [True]


def test_a_run_whose_lock_session_ends_midway_fails(
    monkeypatch, lock_sessions, other_session
):
    """The lock went with its session (a dropped connection) and another migrate may have run
    alongside: the run fails, instead of ending as if it had held the lock throughout."""
    terminated = []

    def handle(self, *args, **options):
        pid = lock_sessions[0].info.backend_pid
        terminated.append(
            other_session.execute(
                "SELECT pg_terminate_backend(%s, 5000)", [pid]
            ).fetchone()[0]
        )

    monkeypatch.setattr(django_migrate.Command, "handle", handle)

    with pytest.raises(psycopg.OperationalError):
        call_command("migrate", verbosity=0)

    assert terminated == [True]
    assert try_lock(other_session) is True


@pytest.mark.django_db
def test_the_real_migrate_still_runs():
    """Django's migrate itself, through the lock: nothing left to apply on the test database."""
    call_command("migrate", check_unapplied=True, verbosity=0)
