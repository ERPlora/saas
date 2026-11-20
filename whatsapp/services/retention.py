"""``whatsapp.retention.purge``: the daily forgetting of what the Hub took, of what it never took and of the keys."""

import logging
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from whatsapp import events
from whatsapp.models import Delivery, Send, TemplateSubmission
from whatsapp.schemas import PurgeIn, PurgeOut
from whatsapp.services.platform_actor import PERMISSION

logger = logging.getLogger("whatsapp.services")


@operation(
    "whatsapp.retention.purge",
    kind="command",
    permission=PERMISSION,
    input=PurgeIn,
    output=PurgeOut,
    ai=INTERNAL,  # scheduled
)
def retention_purge(ctx: OperationContext, data: PurgeIn) -> PurgeOut:
    """Forget, past ``days``: what the Hub took, every delivery status (news only while its message is recent),
    what the Hub never took (a Hub off or without the inbox: said in the log, per business) and the keys of the
    sends and of the templates' registrations (the Hub retries a key within minutes, never a month later)."""
    since = timezone.now() - timedelta(days=data.days)
    taken, _ = Delivery.objects.filter(delivered_at__lt=since).delete()
    statuses, _ = Delivery.objects.filter(kind=Delivery.Kind.STATUS, received_at__lt=since).delete()
    lost = Delivery.objects.filter(kind=Delivery.Kind.MESSAGE, delivered_at__isnull=True, received_at__lt=since)
    for hub_id, count in lost.values_list("hub_id").annotate(count=Count("id")).values_list("hub_id", "count"):
        logger.warning("whatsapp.retention.never_taken hub_id=%s messages=%s days=%s", hub_id, count, data.days)
    never_taken, _ = lost.delete()
    sends, _ = Send.objects.filter(created_at__lt=since).delete()
    registrations, _ = TemplateSubmission.objects.filter(created_at__lt=since).delete()
    out = PurgeOut(
        deliveries=taken + statuses, never_taken=never_taken, sends=sends, registrations=registrations
    )
    record_event(ctx, events.RETENTION_PURGED, out.model_dump())
    return out
