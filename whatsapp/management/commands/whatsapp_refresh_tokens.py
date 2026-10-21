"""``python manage.py whatsapp_refresh_tokens``: once a day in ``saas-cron`` (WHATSAPP-G12).

Renews Meta's permission of every connected number whose deadline is 14 days away or closer, marks «needs
reconnecting» the ones Meta refused (or could not answer for with 3 days or less left) and mails their owner once
per incident (``gateway.renew_tokens``). Under the advisory lock of its name (a second run returns at once). Without
Meta's app configured, or when a number crashed, it ends with an error (the ``task_failed`` alarm).
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from hubs.services import run_exclusively
from whatsapp import gateway, meta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Renew Meta's permission of the WhatsApp numbers about to expire and tell the owners it could not renew."

    def handle(self, *args, **options):
        with run_exclusively("whatsapp_refresh_tokens") as mine:
            if not mine:
                self.stdout.write("whatsapp_refresh_tokens: already running, nothing done.")
                return
            try:
                counts = gateway.renew_tokens()
            except meta.NotConfigured as missing:
                logger.error("whatsapp.token.not_configured")
                raise CommandError(f"whatsapp_refresh_tokens: {missing}") from None
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("whatsapp.token.renewal %s", summary)
        self.stdout.write(f"whatsapp_refresh_tokens: {summary}")
        if counts["failed"]:
            raise CommandError(f"whatsapp_refresh_tokens: some numbers crashed: {summary}")
