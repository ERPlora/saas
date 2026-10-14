"""``python manage.py reconcile_platform_invoices``: what ERPlora's platform hub still owes (``saas-cron``).

The legal invoice is issued by ERPlora's platform hub in hub-next (PLAN-SAAS §4; lot L3-C). After the webhook's
COMMIT the SaaS posts each invoice once (``billing.services.post_platform_invoice``); this is the net, every
15 minutes: it posts again every «issuing» invoice whose wait passed (idempotent on the Hub by its id), asks
the Hub about every issued or rejected one until the AEAT accepts it, and counts the ones «issuing» for more
than an hour (``billing.services.reconcile_platform_invoices``).

Idempotent, under the advisory lock ``hashtext('erplora.saas.reconcile_platform_invoices')``
(``hubs.services.run_exclusively``, the SaaS's convention: a second run returns at once). One invoice never
stops the pass; the counts go to the log, and the run ends with an error after its pass when anything stayed
owed, was refused, rejected, stuck or crashed (the ``task_failed`` alarm). To schedule in
``aws-next/stacks/prod/scheduler.tf`` next to ``reconcile_hub_states``.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from billing import services
from hubs.services import run_exclusively

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Post again the invoices the platform hub has not issued and ask about the issued ones (idempotent)."

    def handle(self, *args, **options):
        with run_exclusively("reconcile_platform_invoices") as mine:
            if not mine:
                self.stdout.write(
                    "reconcile_platform_invoices: already running, nothing done."
                )
                return
            counts = services.reconcile_platform_invoices()
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("billing.reconcile_platform_invoices %s", summary)
        self.stdout.write(f"reconcile_platform_invoices: {summary}")
        if services.platform_run_failed(counts):
            raise CommandError(
                f"reconcile_platform_invoices left invoices owed: {summary}"
            )
