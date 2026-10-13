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

import pytest
from django.core.management import call_command, get_commands
from django.core.management.commands import migrate as django_migrate

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


def test_a_failed_migration_releases_the_lock(monkeypatch, other_session):
    def handle(self, *args, **options):
        raise RuntimeError("migration 0042 failed")

    monkeypatch.setattr(django_migrate.Command, "handle", handle)

    with pytest.raises(RuntimeError, match="0042"):
        call_command("migrate", verbosity=0)

    assert try_lock(other_session) is True


@pytest.mark.django_db
def test_the_real_migrate_still_runs():
    """Django's migrate itself, through the lock: nothing left to apply on the test database."""
    call_command("migrate", check_unapplied=True, verbosity=0)
