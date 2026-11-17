"""GDPR: the audit log keeps 90 days."""

from django.db import transaction


#: Days an audit entry is kept (GDPR art. 5.1.e). ``cleanup_old_logs --retention-days`` changes it.
AUDIT_LOG_RETENTION_DAYS = 90
#: Audit entries deleted per transaction: a long run never holds one big transaction.
AUDIT_LOG_BATCH = 1000


def audit_entries_before(cutoff) -> int:
    """How many audit entries were written before ``cutoff`` (``cleanup_old_logs --dry-run``)."""
    from auditlog.models import LogEntry

    return LogEntry.objects.filter(timestamp__lt=cutoff).count()


def prune_audit_log_batch(cutoff) -> int:
    """Delete up to ``AUDIT_LOG_BATCH`` of the audit entries written before ``cutoff``, in their own transaction; how
    many went, as the database counts them (0: none is left, or none could go, and the run ends)."""
    from auditlog.models import LogEntry

    with transaction.atomic():
        ids = list(
            LogEntry.objects.filter(timestamp__lt=cutoff).order_by("pk").values_list("pk", flat=True)[:AUDIT_LOG_BATCH]
        )
        deleted, _ = LogEntry.objects.filter(pk__in=ids).delete()
    return deleted


def forget_the_retired_audit_type() -> None:
    """Delete the content type of ``accounts.HubMembership`` once no audit entry names it. ``accounts/0012`` could not
    while one did: a content type takes its entries with it, and ``cleanup_old_logs`` still keeps them (saas#220)."""
    from auditlog.models import LogEntry
    from django.contrib.contenttypes.models import ContentType

    with transaction.atomic():
        retired = ContentType.objects.filter(app_label="accounts", model="hubmembership")
        if not LogEntry.objects.filter(content_type__in=retired).exists():
            retired.delete()
