"""``python manage.py check_custom_domains``: hourly in ``saas-cron`` (HUBS-F17; ``aws`` README, «Dominio propio de un
negocio»).

Moves each business's own domain as far as it goes today (``services.check_custom_domains``): its certificate, on the
shared listener, the customer's CNAME, the snapshot and the probe to active; three failures in a row out of the snapshot,
with its certificate gone and the owner told; back when the CNAME is. At the end it publishes
``ERPlora/CustomDomains CertificatesAttached``, which the alarm at 80 % of the listener reads.

With ``CUSTOM_DOMAINS_ENABLED`` absent or false it looks at nothing and calls nobody. Idempotent, under the advisory lock
``hashtext('erplora.saas.check_custom_domains')`` (a second run returns at once). A domain that fails never stops the
pass. AWS, the DNS or the Hub being away are no error: the next pass tries again. A crash or a metric that could not be
published end the run with an error after its pass (the ``task_failed`` alarm).
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from hubs import services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Move each business's own domain as far as it goes today and publish the certificates on the listener."

    def handle(self, *args, **options):
        if not settings.CUSTOM_DOMAINS_ENABLED:
            self.stdout.write("check_custom_domains: own domains are off, nothing done.")
            return
        with services.run_exclusively("check_custom_domains") as mine:
            if not mine:
                self.stdout.write("check_custom_domains: already running, nothing done.")
                return
            counts = services.check_custom_domains()
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("hubs.check_custom_domains %s", summary)
        self.stdout.write(f"check_custom_domains: {summary}")
        if services.custom_domains_failed(counts):
            raise CommandError(f"check_custom_domains: a domain crashed or the metric was not published: {summary}")
