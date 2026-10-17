"""``python manage.py migrate``: Django's, under a Postgres advisory lock (``saas-migrate``; aws README,
«Comandos ``manage.py``»), so two deploys never migrate the SaaS database at once.

The lock, ``pg_advisory_lock(hashtext('erplora.saas.migrate'))``, is a session lock taken on a
connection of its own (the SaaS goes straight to Aurora, never through PgBouncer) before Django's
migrate starts and held until it ends. A second run waits for it and then migrates whatever is left
(usually nothing). The run releases it when it ends, also when it fails, before closing that
connection: Postgres ends a closed session (and drops its locks) a moment after the close, too late
for a task asking right then. If the task dies, Postgres ends its session and the lock goes with it;
if the session ends mid-run, the release fails and so does the run, since another migrate may have
run alongside. Django takes a command from the first app of ``INSTALLED_APPS`` that defines it and
none before ``base`` defines ``migrate``, so this one wins, also for pytest-django, which creates
the test database through it.
"""

from contextlib import contextmanager

import psycopg
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connections

LOCK_KEY = "hashtext('erplora.saas.migrate')"


class Command(MigrateCommand):
    def handle(self, *args, **options):
        with migration_lock(options["database"], self.stdout):
            return super().handle(*args, **options)


@contextmanager
def migration_lock(alias: str, stdout):
    """Hold the migrate lock of ``alias``'s database while the block runs, waiting for it if another
    run holds it."""
    params = connections[alias].get_connection_params()
    with psycopg.connect(**params, autocommit=True) as session:
        taken = session.execute(f"SELECT pg_try_advisory_lock({LOCK_KEY})").fetchone()[
            0
        ]
        if not taken:
            stdout.write("migrate: another migrate holds the lock, waiting for it.")
            session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
        try:
            yield
        finally:
            session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
