"""``python manage.py purge_webhook_events``: forget the Stripe events received more than 30 days ago (BILLING-F37).

Ported from ERPlora/saas ``cleanup_old_webhook_events`` (``apps/dashboard/billing``; a weekly Celery beat task
there, an ECS scheduled task here). Each row only guards a delivery against being processed twice, and Stripe
resends an event for 3 days at most (``billing.services.purge_webhook_events``). One ``DELETE``: idempotent, two
runs at once delete each row once.
"""

import logging

from django.core.management.base import BaseCommand

from billing import services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete the Stripe events received more than 30 days ago (idempotent)."

    def handle(self, *args, **options):
        deleted = services.purge_webhook_events()
        logger.info("billing.purge_webhook_events deleted=%s", deleted)
        self.stdout.write(f"purge_webhook_events: deleted={deleted}")
