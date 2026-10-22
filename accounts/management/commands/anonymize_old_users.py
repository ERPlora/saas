"""``python manage.py anonymize_old_users``: the accounts unused for two years go (ACCOUNTS-F35; GDPR art. 5.1.e).

Weekly in ``saas-cron``. Ported from ERPlora/saas ``apps/auth/users/management/commands/anonymize_old_users.py`` (a Celery
beat task there, ``gdpr.anonymize_old_users``): every active account that is not staff and has not signed in on
erplora.com for ``--inactive-days`` (730; never signed in, since it was created) goes as its owner deletes it
(``accounts.services.erase_inactive_account``, ACCOUNTS-F27), unless it belongs to a business that is not deleted.
ERPlora's invoices stay with their recipient as issued.

``--dry-run`` counts what a run would do and changes nothing. No question is asked (the old ``--no-input`` is the only
way here). Idempotent, under the advisory lock ``hashtext('erplora.saas.anonymize_old_users')``: a second run returns at
once. One account never stops the pass: one that fails is logged by its id (never its email) and the run ends with an
error after its pass (the ``task_failed`` alarm).
"""

import logging
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from accounts import services

logger = logging.getLogger(__name__)

#: What each outcome of ``erase_inactive_account`` counts as, in a run and in a dry run.
COUNTS = {"erased": "erased", "member": "skipped_member", "active": "skipped_active"}
DRY_COUNTS = {"erased": "would_erase", "member": "skipped_member", "active": "skipped_active"}


class Command(BaseCommand):
    help = "Erase the accounts unused for two years (default 730 days), as their owners would delete them (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--inactive-days", type=int, default=services.INACTIVE_DAYS, help="Days without signing in (default 730)."
        )
        parser.add_argument("--dry-run", action="store_true", help="Count what would go and change nothing.")

    def handle(self, *args, inactive_days: int, dry_run: bool, **options):
        if inactive_days < 1:
            raise CommandError("--inactive-days must be at least 1.")
        names = DRY_COUNTS if dry_run else COUNTS
        with services.run_exclusively("anonymize_old_users") as mine:
            if not mine:
                self.stdout.write("anonymize_old_users: already running, nothing done.")
                return
            counts = Counter({name: 0 for name in [*names.values(), "failed"]})
            for user_id in services.inactive_account_ids(inactive_days=inactive_days):
                try:
                    outcome = services.erase_inactive_account(user_id, inactive_days=inactive_days, dry_run=dry_run)
                except Exception:  # noqa: BLE001 - one account never stops the pass; it is tried again next week
                    logger.exception("accounts.anonymize_old_users.failed user=%s", user_id)
                    counts["failed"] += 1
                    continue
                counts[names[outcome]] += 1
        summary = " ".join(f"{key}={value}" for key, value in counts.items())
        logger.info("accounts.anonymize_old_users%s %s", " dry_run" if dry_run else "", summary)
        self.stdout.write(f"anonymize_old_users{' (dry run)' if dry_run else ''}: {summary}")
        if counts["failed"]:
            raise CommandError(f"anonymize_old_users left accounts for the next run: {summary}")
