"""``python manage.py sync_subscriptions [--dry-run]``: every live subscription read again from Stripe (BILLING-F38).

Ported from ERPlora/saas ``apps/dashboard/hubs/subscriptions/management/commands/sync_subscriptions.py``. The
webhook keeps each subscription as Stripe says (BILLING-F21); this pass puts right what an event that never
arrived left behind, reading each one as the webhook does (``billing.services.sync_subscriptions``).
``--dry-run`` only says what drifted.

Under the advisory lock ``hashtext('erplora.saas.sync_subscriptions')`` (``hubs.services.run_exclusively``). One
business never stops the pass; one Stripe could not read, or does not know, ends the run with an error after
its pass (the ``task_failed`` alarm).
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from billing import services
from hubs.services import run_exclusively

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Read every live subscription again from Stripe and put right what drifted."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only say what drifted; write nothing.")

    def handle(self, *args, **options):
        with run_exclusively("sync_subscriptions") as mine:
            if not mine:
                self.stdout.write("sync_subscriptions: already running, nothing done.")
                return
            counts = services.sync_subscriptions(apply=not options["dry_run"])
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("billing.sync_subscriptions %s", summary)
        self.stdout.write(f"sync_subscriptions: {summary}")
        if counts["missing"] or counts["errors"]:
            raise CommandError(f"sync_subscriptions left subscriptions to look at: {summary}")
