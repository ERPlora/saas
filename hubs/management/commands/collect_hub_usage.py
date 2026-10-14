"""``python manage.py collect_hub_usage [--day YYYY-MM-DD]``: nightly in ``saas-cron`` (lot L4-A, PLAN-SAAS §5).

Asks the Hub for one day's usage of every business (``GET /internal/usage?day=``, page by page; contract in
``hubs/README.md``, «Uso») and keeps it as ``HubUsageDaily``, one row per business and day
(``services.collect_usage``). By default the day is yesterday in UTC, the last one the Hub's nightly
measure closed; ``--day`` collects another (a backfill), never one not over yet. Idempotent: a day collected
again replaces its figures and tells nobody when they are the same. Under the advisory lock
``hashtext('erplora.saas.collect_hub_usage')`` (``services.run_exclusively``; a second run returns at once).
A row that fails never stops the pass; the run ends with an error after it when the Hub was away or refused,
or answered off the contract (the ``task_failed`` alarm).
"""

import logging
from datetime import UTC, date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from hubs import queries, services

logger = logging.getLogger(__name__)


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CommandError(f"--day {value!r} is not a day (YYYY-MM-DD).") from None


class Command(BaseCommand):
    help = "Collect one day's usage of every business from the Hub (yesterday in UTC by default; idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--day",
            type=_day,
            help="The day to collect, YYYY-MM-DD (default: yesterday, UTC).",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        day = options["day"] or queries.last_measured_day(now)
        if day >= now.astimezone(UTC).date():
            raise CommandError(
                f"collect_hub_usage: {day} is not over yet in UTC; the Hub has not measured it."
            )
        with services.run_exclusively("collect_hub_usage") as mine:
            if not mine:
                self.stdout.write("collect_hub_usage: already running, nothing done.")
                return
            counts = services.collect_usage(day)
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("hubs.collect_usage day=%s %s", day, summary)
        self.stdout.write(f"collect_hub_usage {day}: {summary}")
        if services.usage_run_failed(counts):
            raise CommandError(
                f"collect_hub_usage {day} did not get every business: {summary}"
            )

