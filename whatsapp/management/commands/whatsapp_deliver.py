"""``python manage.py whatsapp_deliver``: every minute in ``saas-cron`` (WHATSAPP-G07).

Pushes again what still waits for the Hub (it was off, without the inbox, or answered 5xx) once its growing wait
passed (``gateway.deliver``), batch after batch while a batch comes full, up to ``MAX_BATCHES``. A Hub still away is
not a failure of the task: its rows wait for their next turn. A crash ends with an error (the ``task_failed`` alarm).
"""

import logging

from django.core.management.base import BaseCommand

from whatsapp import gateway

logger = logging.getLogger(__name__)

BATCH = 50
MAX_BATCHES = 20


class Command(BaseCommand):
    help = "Push to the Hubs the WhatsApp messages and statuses that still wait for them."

    def handle(self, *args, **options):
        totals: dict[str, int] = {}
        for _ in range(MAX_BATCHES):
            counts = gateway.deliver(limit=BATCH)
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
            if sum(counts.values()) < BATCH:
                break
        summary = " ".join(f"{key}={value}" for key, value in totals.items())
        logger.info("whatsapp.deliver %s", summary)
        self.stdout.write(f"whatsapp_deliver: {summary}")
