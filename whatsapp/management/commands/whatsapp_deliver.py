"""``python manage.py whatsapp_deliver``: every minute in ``saas-cron`` (WHATSAPP-G07).

Pushes again what still waits for the Hub (it was off, without the inbox, or answered 5xx) once its growing wait
passed (``gateway.deliver``), batch after batch while a batch comes full, for ``BUDGET`` at most. A Hub still away is
not a failure of the task: its rows wait for their next turn. A crash ends with an error (the ``task_failed`` alarm).

One pass at a time, under the advisory lock of its name: a pass that finds another one running says so and ends
without error. The figures, so that no row a pass claimed is claimed again while it still pushes it
(FIX-SAAS-WHATSAPP-DELIVER-OVERLAP):

- a call to the Hub takes ``hub_client.LONGEST_CALL`` at most: 10 s (5 s to connect, 5 s more to answer);
- each batch claims only the rows whose calls fit in what is left of ``BUDGET`` (50 s), so the pass's last call ends
  by 50 s: before saas-cron's next pass starts, a minute after this one, and inside ``services.LEASE`` (5 min) of
  every row it claimed (a row is leased when it is claimed, never before the pass started);
- Meta's webhook pushes up to ``gateway.WEBHOOK_DELIVERIES`` (20) without this lock: 20 x 10 s = 200 s, also inside
  the lease, so neither takes a row the other one is still pushing.

At the Hub's slowest a pass pushes 5 rows; with a Hub that answers in 20 ms, over a thousand. Before, a batch of 50
was leased for 2 minutes and took up to 250 s, for up to 20 batches (about 83 minutes): with a slow Hub every
minute's pass ran beside the ones before, each with its connection, and pushed again what they still held (the Hub
drops a message it already has by its WhatsApp id: repeated traffic, not doubled data).
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from hubs.services import run_exclusively
from whatsapp import gateway, hub_client

logger = logging.getLogger(__name__)

#: How long a pass may push for: less than a minute (saas-cron's next pass) and than ``services.LEASE``.
BUDGET = timedelta(seconds=50)


class Command(BaseCommand):
    help = "Push to the Hubs the WhatsApp messages and statuses that still wait for them."

    def handle(self, *args, **options):
        with run_exclusively("whatsapp_deliver") as mine:
            if not mine:
                logger.info("whatsapp.deliver.already_running")
                self.stdout.write("whatsapp_deliver: already running, nothing done.")
                return
            totals = self.push_for(BUDGET)
        summary = " ".join(f"{key}={value}" for key, value in totals.items())
        logger.info("whatsapp.deliver %s", summary)
        self.stdout.write(f"whatsapp_deliver: {summary}")

    def push_for(self, budget: timedelta) -> dict[str, int]:
        """Batch after batch while one comes full, each one only as big as the calls that still fit in ``budget``."""
        now = timezone.now()
        ends = now + budget
        totals: dict[str, int] = {}
        while (room := int((ends - now) / hub_client.LONGEST_CALL)) > 0:
            counts = gateway.deliver(limit=room)
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
            if sum(counts.values()) < room:
                break
            now = timezone.now()
        return totals
