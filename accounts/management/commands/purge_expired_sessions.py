"""``python manage.py purge_expired_sessions``: the daily sweep of what a sign-in leaves behind (ACCOUNTS-G71).

Daily in ``saas-cron``. The old SaaS's ``clearsessions_task`` and ``flush_expired_tokens_task`` (``apps/core/tasks.py``,
origin/develop c5ca8cae8), Celery beat tasks there; with no JWT here (PLAN-SAAS §1.1 point 2), what goes is: the
sessions past their expiry (Django's ``clearsessions``), the rows of «Active sessions» whose session is gone (they keep
the address and the browser; allauth only drops them when their account opens the list), the one-time codes of the jumps
to a business past their 60 s and the changes of email past their code's 15 minutes
(``accounts.services.purge_expired_sign_in_leftovers``).

``--dry-run`` counts what a run would delete and deletes nothing. Idempotent, under the advisory lock
``hashtext('erplora.saas.purge_expired_sessions')``: a second run returns at once. A failure ends the run with its error
(the ``task_failed`` alarm); what went before it stays deleted and the next run goes on.
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts import services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete the expired sessions, their «Active sessions» rows and the expired one-time codes (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count what would go and delete nothing.")

    def handle(self, *args, dry_run: bool, **options):
        now = timezone.now()
        with services.run_exclusively("purge_expired_sessions") as mine:
            if not mine:
                self.stdout.write("purge_expired_sessions: already running, nothing done.")
                return
            counts = (
                services.count_expired_sign_in_leftovers(now)
                if dry_run
                else services.purge_expired_sign_in_leftovers(now)
            )
        summary = " ".join(f"{kind}={count}" for kind, count in counts.items())
        logger.info("accounts.purge_expired_sessions%s %s", " dry_run" if dry_run else "", summary)
        self.stdout.write(f"purge_expired_sessions{' (dry run)' if dry_run else ''}: {summary}")
