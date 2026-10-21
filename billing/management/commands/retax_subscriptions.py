"""``python manage.py retax_subscriptions``: every live subscription takes today's rates (BILLING-F02, F06).

Ported from ERPlora/saas ``fiscal.retax_live_subscriptions`` (``oss_subscription_retax.py``, saas#2293; a daily
Celery beat task there, a scheduled ECS task here). The owner's save of the billing details retaxes at once;
this pass catches what that push missed, the year crossing the OSS threshold (or back to origin) and a rate
the table schedules (``billing.services.retax_live_subscriptions``).

Idempotent (a rate Stripe already holds is not sent again), under the advisory lock
``hashtext('erplora.saas.retax_subscriptions')`` (``hubs.services.run_exclusively``). One business never stops
the pass; a refused place or an error ends the run with an error after it (the ``task_failed`` alarm).
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from billing import services
from hubs.services import run_exclusively

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Hand Stripe today's tax rates on every live subscription (idempotent)."

    def handle(self, *args, **options):
        with run_exclusively("retax_subscriptions") as mine:
            if not mine:
                self.stdout.write("retax_subscriptions: already running, nothing done.")
                return
            counts = services.retax_live_subscriptions()
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("billing.retax_subscriptions %s", summary)
        self.stdout.write(f"retax_subscriptions: {summary}")
        if counts["refused"] or counts["errors"]:
            raise CommandError(f"retax_subscriptions left work for the next run: {summary}")
