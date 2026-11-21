"""Meta's webhook, ``whatsapp.webhook.ingest``: what Meta reported, parked once per message for each active number
(``Delivery``), the furthest status of each message, and Meta's verdicts on the templates."""

import logging
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, on_commit, operation
from live.outbox import record_event

from hubs.services import hub_push
from whatsapp import events, parse
from whatsapp.models import Delivery, PhoneNumber, Template
from whatsapp.schemas import IngestIn, IngestOut
from whatsapp.services.channel_snapshot import announce_channel
from whatsapp.services.delivery_queue import wake_the_worker
from whatsapp.services.platform_actor import PERMISSION

logger = logging.getLogger("whatsapp.services")

#: How far each delivery status is; ``failed`` replaces anything but ``read``, and nothing replaces it.
STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3}


@operation(
    "whatsapp.webhook.ingest",
    kind="command",
    permission=PERMISSION,
    input=IngestIn,
    output=IngestOut,
    ai=INTERNAL,  # meta
)
def webhook_ingest(ctx: OperationContext, data: IngestIn) -> IngestOut:
    parsed = parse.parse(data.payload)
    named = {message.phone_number_id for message in parsed.messages} | {status.phone_number_id for status in parsed.statuses}
    # A number of a business that left (being deleted or purged) takes nothing any more.
    numbers = dict(
        PhoneNumber.objects.filter(
            phone_number_id__in=named, is_active=True, hub__status__in=hub_push.LIVE_STATUSES
        ).values_list("phone_number_id", "hub_id")
    )
    touched: set[UUID] = set()
    parked = statuses = 0
    discarded = parsed.skipped
    for message in parsed.messages:
        hub_id = numbers.get(message.phone_number_id)
        if hub_id is None:
            discarded += 1
        elif _park_message(hub_id, message):
            parked += 1
            touched.add(hub_id)
    for status in parsed.statuses:
        hub_id = numbers.get(status.phone_number_id)
        if hub_id is None:
            discarded += 1
        elif _park_status(hub_id, status):
            statuses += 1
            touched.add(hub_id)
    template_hubs = _apply_verdicts(parsed.verdicts)
    for phone_number_id in parsed.history_declined:
        logger.info("whatsapp.history.declined phone_number_id=%s", phone_number_id)
    if discarded:
        logger.info("whatsapp.webhook.discarded count=%s", discarded)
    if touched:
        on_commit(wake_the_worker)
    record_event(
        ctx,
        events.WEBHOOK_INGESTED,
        {"parked": parked, "statuses": statuses, "verdicts": len(parsed.verdicts), "discarded": discarded},
    )
    return IngestOut(
        hub_ids=sorted(touched, key=str),
        template_hubs=sorted(template_hubs, key=str),
        parked=parked,
        statuses=statuses,
        verdicts=len(parsed.verdicts),
        discarded=discarded,
    )


def _due_again(row: Delivery, now) -> None:
    row.revision += 1
    row.delivered_at = None
    row.attempts = 0
    row.next_attempt_at = now
    row.last_error = ""


def _park_message(hub_id: UUID, message: parse.Message) -> bool:
    """Park ``message`` for ``hub_id`` once (Meta delivers at least once). A media placeholder of the history is
    completed by its follow-up, in its place (who spoke and under which customer), and goes to the Hub again."""
    row, created = Delivery.objects.get_or_create(
        hub_id=hub_id,
        kind=Delivery.Kind.MESSAGE,
        wa_message_id=message.wa_message_id,
        defaults={"contact": message.contact[:32], "body": message.body, "media_id": message.media_id},
    )
    if created:
        return True
    if not (message.follow_up and message.media_id and row.body.get("type") == parse.PLACEHOLDER):
        return False
    row = Delivery.objects.select_for_update().get(pk=row.pk)
    if row.body.get("type") != parse.PLACEHOLDER:
        return False
    kept = {name: row.body[name] for name in ("from", "direction", "contact_name") if name in row.body}
    row.body = {**message.body, **kept}
    row.media_id = message.media_id
    _due_again(row, timezone.now())
    row.save()
    return True


def _further(current: str | None, new: str) -> bool:
    if new == current or current == "failed":
        return False
    if new == "failed":
        return current != "read"
    return STATUS_RANK.get(new, 0) > STATUS_RANK.get(current or "", 0)


def _park_status(hub_id: UUID, status: parse.Status) -> bool:
    """Keep the furthest status of a message: Meta does not guarantee their order, so a late «delivered» never
    undoes a «read»."""
    body = {
        "wa_message_id": status.wa_message_id,
        "status": status.status,
        "error": status.error,
        "status_at": status.status_at,
    }
    row = (
        Delivery.objects.select_for_update()
        .filter(hub_id=hub_id, kind=Delivery.Kind.STATUS, wa_message_id=status.wa_message_id)
        .first()
    )
    if row is None:
        _, created = Delivery.objects.get_or_create(
            hub_id=hub_id, kind=Delivery.Kind.STATUS, wa_message_id=status.wa_message_id, defaults={"body": body}
        )
        return created
    if not _further(row.body.get("status"), status.status):
        return False
    row.body = body
    _due_again(row, timezone.now())
    row.save()
    return True


def _apply_verdicts(verdicts: list[parse.Verdict]) -> set[UUID]:
    """Write Meta's verdicts on the businesses' templates; the businesses of a template the mirror does not have
    yet are returned, to read their templates from Meta again (``gateway.message_templates.sync_templates``)."""
    unknown: set[UUID] = set()
    for verdict in verdicts:
        hub_ids = PhoneNumber.objects.filter(waba_id=verdict.waba_id, is_active=True).values_list("hub_id", flat=True)
        for hub_id in hub_ids:
            named = Q(meta_id=verdict.meta_id) if verdict.meta_id else Q(name=verdict.name, language=verdict.language)
            template = Template.objects.select_for_update().filter(named, hub_id=hub_id).first()
            if template is None:
                unknown.add(hub_id)
                continue
            if verdict.status:
                status = parse.hub_verdict(verdict.status)
                if status is None:
                    template.delete()
                    announce_channel(hub_id)
                    continue
                template.status = status
                template.rejected_reason = verdict.reason if status == Template.Status.REJECTED else ""
            if verdict.category:
                template.category = verdict.category
            template.save()
            announce_channel(hub_id)
    return unknown
