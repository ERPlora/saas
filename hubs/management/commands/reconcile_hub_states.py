"""``python manage.py reconcile_hub_states [--stuck-minutes N]``: every 15 minutes in ``saas-cron``.

Keeps the Hub equal to the SaaS (plan 2026-10-13 §3, the push to the Hub): retries what the Hub still owes
an answer to (registry, deletion, restoration, snapshot), asks the Hub about a sign-up stuck without its
``ready`` callback for more than N minutes (``GET /internal/hubs/{id}``; 2 by default, PLAN-SAAS §3.1)
(``preparing`` while the Hub prepares it, ``provision_failed`` when it says it could not, ``unexpected`` for any other
answer), ends the trials that ran out, marks purged the businesses past their 90 days, tells the owner of a deleted
business once the copy of its data is ready (``GET /internal/hubs/{id}/dumps``: ``data_copies_told``,
``data_copy_unsent``) and delivers the session revocations the Hub has not taken yet once their wait passed
(``SessionRevocation``: ``sessions_ended``, ``sessions_pending``). Idempotent, under the
advisory lock ``hashtext('erplora.saas.reconcile_hub_states')`` (``services.run_exclusively``; a second run
returns at once). A business that fails never stops the pass: it stays owed for the next run, the counts
go to the log, and the run ends with an error after its pass when anything stayed owed, unreachable or
crashed (the ``task_failed`` alarm).
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from hubs import services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Retry what the Hub owes, settle stuck sign-ups, end trials, purge expired deletions, tell owners their "
        "data copy is ready and deliver pending session revocations (idempotent)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stuck-minutes",
            type=int,
            default=int(services.STUCK_AFTER.total_seconds() // 60),
            help="Ask the Hub about an sign-up without its ready callback after this many minutes.",
        )

    def handle(self, *args, **options):
        with services.run_exclusively("reconcile_hub_states") as mine:
            if not mine:
                self.stdout.write("reconcile_hub_states: already running, nothing done.")
                return
            counts = services.reconcile(stuck_after=timedelta(minutes=options["stuck_minutes"]))
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("hubs.reconcile %s", summary)
        self.stdout.write(f"reconcile_hub_states: {summary}")
        if services.run_failed(counts):
            raise CommandError(f"reconcile_hub_states left work owed: {summary}")
