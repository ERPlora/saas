"""``python manage.py whatsapp_purge [--days N]``: once a day in ``saas-cron`` (WHATSAPP-G14).

Forgets what erplora.com no longer keeps of the businesses' WhatsApp (``whatsapp.retention.purge``): what the Hub
took more than N days ago, the delivery statuses older than that, what the Hub never took in that time and the keys
of the sends and of the templates' registrations. N is 30, and can be shortened by hand (1 to 30), never lengthened:
out of that range nothing is deleted and it ends with an error.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from whatsapp import services
from whatsapp.schemas import PurgeIn

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Forget the WhatsApp messages, statuses and keys past their retention (30 days, or fewer by hand)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Days kept, 1 to 30.")

    def handle(self, *args, **options):
        days = options["days"]
        if not 1 <= days <= 30:
            raise CommandError(f"whatsapp_purge: --days is 1 to 30, not {days}; nothing deleted.")
        out = services.retention_purge(services.platform_context(), PurgeIn(days=days))
        summary = " ".join(f"{key}={value}" for key, value in out.model_dump().items())
        logger.info("whatsapp.retention %s", summary)
        self.stdout.write(f"whatsapp_purge: {summary}")
