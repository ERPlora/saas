"""Each Stripe event processed once: a delivery claims it before processing it and releases it with how it ended,
and what is older than Stripe's resending is forgotten."""

from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from billing.models import WebhookEvent


CLAIMED, DUPLICATE, IN_PROGRESS = "claimed", "duplicate", "in_progress"


def claim_event(event_id: str, event_type: str) -> str:
    """Decide whether this delivery processes the event: ``CLAIMED`` (process it, then ``finish_event``),
    ``DUPLICATE`` (processed already) or ``IN_PROGRESS`` (another delivery holds it; Stripe retries). The
    row is created or locked in one transaction, so of two simultaneous deliveries only one claims it; a
    claim older than ``CLAIM_LEASE`` (a process that died) is taken over."""
    now = timezone.now()
    with transaction.atomic():
        row, created = WebhookEvent.objects.select_for_update().get_or_create(
            event_id=event_id,
            defaults={"event_type": event_type, "processing_since": now, "attempts": 1},
        )
        if created:
            return CLAIMED
        if row.success:
            return DUPLICATE
        if (
            row.processing_since is not None
            and row.processing_since > now - WebhookEvent.CLAIM_LEASE
        ):
            return IN_PROGRESS
        WebhookEvent.objects.filter(pk=row.pk).update(
            processing_since=now, attempts=F("attempts") + 1
        )
        return CLAIMED


def finish_event(
    event_id: str, *, success: bool, outcome: str, error: str = ""
) -> None:
    """Release the claim with how the processing ended; a failure stays claimable for Stripe's retry."""
    WebhookEvent.objects.filter(event_id=event_id).update(
        success=success,
        outcome=outcome[:32],
        error_message=error,
        processing_since=None,
        processed_at=timezone.now(),
    )


#: How long an event's row is kept: Stripe resends an event for 3 days at most and keeps it 30, so
#: an older row never guards a delivery again.
WEBHOOK_EVENT_RETENTION = timedelta(days=30)


def purge_webhook_events() -> int:
    """saas-cron, ``manage.py purge_webhook_events``: forget the events received more than
    ``WEBHOOK_EVENT_RETENTION`` ago, processed or not. How many were deleted."""
    deleted, _ = WebhookEvent.objects.filter(received_at__lt=timezone.now() - WEBHOOK_EVENT_RETENTION).delete()
    return deleted
