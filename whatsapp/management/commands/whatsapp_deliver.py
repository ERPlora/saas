"""``python manage.py whatsapp_deliver``: one pass of what still waits for the Hub, by hand (WHATSAPP-G07).

The ``saas-worker`` (``manage.py run_worker``, ``base.worker``, saas#305) runs the same pass whenever a delivery is
due: a ``NOTIFY`` after the COMMIT that parked it or moved its wait, the time of the next retry, and every 15 minutes.
This command stays for diagnosis and rescue (``pre`` runs it by hand while it has no worker of its own); it is no
longer scheduled.

It pushes again what still waits for the Hub (it was off, without the inbox, or answered 5xx) once its growing wait
passed (``gateway.deliver``), each business's messages in the order they arrived, batch after batch while a batch
comes full, for ``gateway.PASS_BUDGET`` at most. A Hub still away is not a failure: its rows wait for their next turn.
A crash ends with an error.

One pass at a time, under the advisory lock of its name (``gateway.deliver_pass``), the worker's included: a pass that
finds another one running says so and ends without error. The figures, so that no row a pass claimed is claimed again
while it still pushes it (FIX-SAAS-WHATSAPP-DELIVER-OVERLAP):

- a call to the Hub takes ``hub_client.LONGEST_CALL`` at most: 10 s (5 s to connect, 5 s more to answer);
- each batch claims only the rows whose calls fit in what is left of ``gateway.PASS_BUDGET`` (50 s), so the pass's
  last call ends by 50 s, inside ``services.LEASE`` (5 min) of every row it claimed (a row is leased when it is
  claimed, never before the pass started);
- Meta's webhook pushes up to ``gateway.WEBHOOK_DELIVERIES`` (20) without this lock: 20 x 10 s = 200 s, also inside
  the lease, so neither takes a row the other one is still pushing.

At the Hub's slowest a pass pushes 5 rows; with a Hub that answers in 20 ms, over a thousand.
"""

import logging

from django.core.management.base import BaseCommand

from whatsapp import gateway

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Push to the Hubs the WhatsApp messages and statuses that still wait for them (one pass, by hand)."

    def handle(self, *args, **options):
        totals = gateway.deliver_pass()
        if totals is None:
            logger.info("whatsapp.deliver.already_running")
            self.stdout.write("whatsapp_deliver: already running, nothing done.")
            return
        summary = " ".join(f"{key}={value}" for key, value in totals.items())
        logger.info("whatsapp.deliver %s", summary)
        self.stdout.write(f"whatsapp_deliver: {summary}")
