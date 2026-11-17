"""The advisory lock a run of the SaaS holds, so a second run at the same time does nothing."""

from contextlib import contextmanager

from django.db import connection


def lock_name(command: str) -> str:
    """The advisory lock of ``command``: ``hashtext('erplora.saas.<command>')``, the namespace every lock
    of the SaaS's database takes (``base``'s ``migrate`` and ``report_seal_expiry``)."""
    return f"erplora.saas.{command}"


@contextmanager
def run_exclusively(command: str):
    """Hold the advisory lock of ``command`` while the block runs; yields ``False`` (and runs nothing of
    its own) when another run holds it.

    A session lock, not ``pg_try_advisory_xact_lock``: a run spans many transactions and calls to the Hub
    (one business per transaction, so a failure never undoes another's acknowledgement). One transaction
    around it all would hold every business row it touched until the end, blocking the panel's writes
    (the nightly bump touches every live one), and would sit idle in transaction through every call to
    the Hub, which Aurora ends past 30 s (``idle_in_transaction_session_timeout``, ``stacks/prod/aurora.tf``
    of the ``aws`` repo), taking the whole pass with it. ``base``'s ``migrate`` holds a
    session lock for the same reason. Released at the end, when the run fails, and when the task dies
    (Postgres ends its session). The SaaS's database is direct, never PgBouncer.
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
