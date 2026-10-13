"""``python manage.py push_hub_snapshots [--behind-only]``: nightly in ``saas-cron`` (00:30 UTC, no flags).

The safety net of PLAN-SAAS §2.2 (every night, every business): pushes the snapshot of every live
business, each with a newer version (the Hub ignores an equal one), so a Hub that lost what it had
acknowledged is put right. ``--behind-only`` pushes only the snapshots the Hub is behind on
(``pushed_state_version < state_version``). Under a Postgres advisory lock (a second run returns at
once); a business that fails stays owed, never stops the batch, and the run ends with an error after
its pass (the ``task_failed`` alarm).
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from hubs import services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Push every live business's snapshot to the Hub; --behind-only, only the ones it is behind on."

    def add_arguments(self, parser):
        parser.add_argument(
            "--behind-only", action="store_true", help="Push only the businesses whose snapshot the Hub is behind on."
        )

    def handle(self, *args, **options):
        with services.run_exclusively("push_hub_snapshots") as mine:
            if not mine:
                self.stdout.write("push_hub_snapshots: already running, nothing done.")
                return
            counts = services.push_snapshots(behind_only=options["behind_only"])
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("hubs.push_snapshots %s", summary)
        self.stdout.write(f"push_hub_snapshots: {summary}")
        if services.run_failed(counts):
            raise CommandError(f"push_hub_snapshots left work owed: {summary}")
