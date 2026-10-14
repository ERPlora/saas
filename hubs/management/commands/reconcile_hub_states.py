"""``python manage.py reconcile_hub_states [--stuck-minutes N]``: every 15 minutes in ``saas-cron``.

Keeps the Hub equal to the SaaS (plan 2026-10-13 §3, the push to the Hub): retries what the Hub still owes
an answer to (registry, deletion, restoration, snapshot), asks the Hub about an sign-up stuck without its
``ready`` callback for more than N minutes (``GET /internal/hubs/{id}``; 2 by default, PLAN-SAAS §3.1),
ends the trials that ran out and marks purged the businesses past their 90 days. Idempotent, under the
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
    help = "Retry what the Hub owes, settle stuck sign-ups, end trials and purge expired deletions (idempotent)."

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
