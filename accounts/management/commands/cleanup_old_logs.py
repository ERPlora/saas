"""``python manage.py cleanup_old_logs``: the audit log keeps 90 days (ACCOUNTS-F37; GDPR art. 5.1.e).

Daily in ``saas-cron``. Ported from ERPlora/saas ``apps/auth/users/management/commands/cleanup_old_logs.py`` (a Celery
beat task there, ``cleanup_old_logs_task``): the audit entries (ACCOUNTS-F36) older than ``--retention-days`` (90) go,
batch after batch, each in its own transaction (``accounts.services.prune_audit_log_batch``).

``--dry-run`` counts what a run would delete and deletes nothing. No question is asked (the old ``--no-input`` is the
only way here). Idempotent, under the advisory lock ``hashtext('erplora.saas.cleanup_old_logs')``: a second run returns
at once. A batch that fails ends the run with its error (the ``task_failed`` alarm); the batches before it stay
deleted and the next run goes on from there.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts import services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete the audit log entries older than 90 days (default), batch after batch (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--retention-days",
            type=int,
            default=services.AUDIT_LOG_RETENTION_DAYS,
            help="Days an audit entry is kept (default 90).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Count what would go and delete nothing.")

    def handle(self, *args, retention_days: int, dry_run: bool, **options):
        if retention_days < 1:
            raise CommandError("--retention-days must be at least 1.")
        cutoff = timezone.now() - timedelta(days=retention_days)
        with services.run_exclusively("cleanup_old_logs") as mine:
            if not mine:
                self.stdout.write("cleanup_old_logs: already running, nothing done.")
                return
            if dry_run:
                summary = f"would_delete={services.audit_entries_before(cutoff)}"
            else:
                deleted = 0
                while batch := services.prune_audit_log_batch(cutoff):
                    deleted += batch
                summary = f"deleted={deleted}"
        logger.info("accounts.cleanup_old_logs%s retention_days=%d %s", " dry_run" if dry_run else "", retention_days, summary)
        self.stdout.write(f"cleanup_old_logs{' (dry run)' if dry_run else ''}: {summary}")
