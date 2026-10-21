"""``python manage.py sweep_unpaid``: the safety net of unpaid plans and deleted businesses (``saas-cron``).

Ported from ERPlora/saas ``suspend_lapsed_unpaid_plans`` (``hubs/main/webhooks.py``, saas#2594; a Celery beat
task there, an ECS scheduled task here, ronda 14). The webhook acts when Stripe sends an event; this replays
every business in dunning with its oldest open invoice (7 days of grace, then suspended; ``unpaid`` at
once) and cancels the Stripe subscription of every deleted business (``billing.services.sweep_unpaid``).

Idempotent, under the advisory lock ``hashtext('erplora.saas.sweep_unpaid')`` (``hubs.services.run_exclusively``,
the SaaS's convention: a second run returns at once). One business never stops the pass; the counts go to
the log, and the run ends with an error after its pass when one failed (the ``task_failed`` alarm).
Scheduled hourly in ``aws-next/stacks/prod/scheduler.tf`` (``sweep-unpaid``).
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from billing import services
from hubs.services import run_exclusively

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Suspend the businesses whose plan is unpaid past its grace and end the billing of deleted ones (idempotent)."

    def handle(self, *args, **options):
        with run_exclusively("sweep_unpaid") as mine:
            if not mine:
                self.stdout.write("sweep_unpaid: already running, nothing done.")
                return
            counts = services.sweep_unpaid()
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("billing.sweep_unpaid %s", summary)
        self.stdout.write(f"sweep_unpaid: {summary}")
        if counts["errors"] or counts["mail_failed"]:
            raise CommandError(f"sweep_unpaid left work for the next run: {summary}")
