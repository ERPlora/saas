"""One run at a time of a scheduled command of accounts, under a session advisory lock."""

from contextlib import contextmanager

from django.db import connection


def lock_name(command: str) -> str:
    """The advisory lock of ``command``: ``hubs.services.lock_name``'s namespace (accounts never imports hubs)."""
    return f"erplora.saas.{command}"


@contextmanager
def run_exclusively(command: str):
    """Hold the session advisory lock of ``command`` while the block runs; yields ``False`` when another run holds it.

    ``hubs.services.run_exclusively``'s twin (accounts never imports hubs): a session lock, because a run spans one
    transaction per account, so one that fails undoes no other. Released at the end, when the run fails and when the
    task dies (Postgres ends its session). The SaaS's database is direct, never PgBouncer.
    """
    name = lock_name(command)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [name])
        taken = cursor.fetchone()[0]
    try:
        yield taken
    finally:
        if taken:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [name])
