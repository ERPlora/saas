"""The commands of whatsapp (``@operation`` kind="command"): the only writes of the app, each in its transaction.

Only the platform runs them (``platform_context``): the Hub through its signed doors, Meta through its webhook, the
``saas-cron`` commands and the staff's admin actions. No account role holds ``whatsapp.manage``. A call to Meta or to
the Hub never happens inside one of these: ``gateway`` calls Meta or the Hub between two commands, so no lock waits
for a third party.

- ``whatsapp.webhook.ingest``: what Meta's webhook reported, parked once per message for each active number
  (``Delivery``), the furthest status of each message, and Meta's verdicts on the templates (WHATSAPP-G07);
- ``whatsapp.delivery.claim`` / ``whatsapp.delivery.record``: the push of what is parked to the Hub's doors 1 and 2,
  leased so two processes never push the same thing at once, and retried with a growing wait.
"""

import logging
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.operations import operation
from live.outbox import record_event

from hubs import services as hubs_services
from whatsapp import events, parse
from whatsapp.models import Delivery, PhoneNumber, Send, Template
from whatsapp.schemas import ClaimedDelivery, ClaimIn, ClaimOut, IngestIn, IngestOut, RecordIn, RecordOut

logger = logging.getLogger(__name__)

PERMISSION = "whatsapp.manage"
#: How long a claimed delivery is held for its push before another run may take it again.
LEASE = timedelta(minutes=2)
#: The first wait after the Hub did not take a delivery; each next one doubles, up to ``LONGEST_WAIT``.
FIRST_WAIT = timedelta(seconds=30)
LONGEST_WAIT = timedelta(hours=1)
#: How far each delivery status is; ``failed`` replaces anything but ``read``, and nothing replaces it.
STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3}


def platform_context() -> OperationContext:
    """The platform acting on WhatsApp (the Hub's doors, Meta's webhook, the tasks, the admin's actions)."""
    return system_context(Scope("platform", "whatsapp"))


def media_url(delivery_id: UUID) -> str:
    """Where the business's people open an attachment: erplora.com's own origin (the only one the Hub accepts)."""
    return f"{settings.WHATSAPP_MEDIA_BASE_URL}/whatsapp/media/{delivery_id}"


def retry_wait(attempts: int) -> timedelta:
    return min(FIRST_WAIT * (2 ** max(attempts - 1, 0)), LONGEST_WAIT)


def announce_channel(hub_id: UUID) -> None:
    """The business's WhatsApp changed (its number, its month's usage, a template): its snapshot carries it under
    ``whatsapp`` (door 4) with a newer version, pushed after the COMMIT and retried by ``reconcile_hub_states``."""
    hubs_services.bump_state(hub_id)
    hubs_services.push_after_commit(hub_id)


# --- Meta's webhook ---------------------------------------------------------------------------------------------


@operation("whatsapp.webhook.ingest", kind="command", permission=PERMISSION, input=IngestIn, output=IngestOut)
def webhook_ingest(ctx: OperationContext, data: IngestIn) -> IngestOut:
    parsed = parse.parse(data.payload)
    named = {message.phone_number_id for message in parsed.messages} | {status.phone_number_id for status in parsed.statuses}
    numbers = dict(
        PhoneNumber.objects.filter(phone_number_id__in=named, is_active=True).values_list("phone_number_id", "hub_id")
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
    yet are returned, to read their templates from Meta again (``gateway.sync_templates``)."""
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


# --- The deliveries to the Hub ----------------------------------------------------------------------------------


@operation("whatsapp.delivery.claim", kind="command", permission=PERMISSION, input=ClaimIn, output=ClaimOut)
def delivery_claim(ctx: OperationContext, data: ClaimIn) -> ClaimOut:
    """Lease what is due (oldest first) for ``LEASE``: another run skips it meanwhile."""
    now = timezone.now()
    due = (
        Delivery.objects.select_for_update(skip_locked=True, of=("self",))
        .select_related("hub")
        .filter(delivered_at__isnull=True, next_attempt_at__lte=now)
    )
    if data.hub_ids is not None:
        due = due.filter(hub_id__in=data.hub_ids)
    rows = list(due.order_by("received_at")[: data.limit])
    Delivery.objects.filter(pk__in=[row.pk for row in rows]).update(next_attempt_at=now + LEASE)
    keys = _client_keys([row for row in rows if row.kind == Delivery.Kind.STATUS])
    return ClaimOut(
        deliveries=[
            ClaimedDelivery(
                id=row.id, kind=row.kind, revision=row.revision, received_at=row.received_at, body=_door_body(row, keys)
            )
            for row in rows
        ]
    )


def _client_keys(statuses: list[Delivery]) -> dict[tuple[UUID, str], str]:
    """The Hub's key (its ``Idempotency-Key``) of each message whose status is pushed: door 2 always carries it."""
    if not statuses:
        return {}
    sends = Send.objects.filter(
        hub_id__in={row.hub_id for row in statuses}, wa_message_id__in={row.wa_message_id for row in statuses}
    ).values_list("hub_id", "wa_message_id", "idempotency_key")
    return {(hub_id, wa_message_id): key for hub_id, wa_message_id, key in sends}


def _door_body(row: Delivery, keys: dict[tuple[UUID, str], str]) -> dict:
    body = {"hub": row.hub.slug, **row.body}
    if row.kind == Delivery.Kind.STATUS:
        body["client_message_id"] = keys.get((row.hub_id, row.wa_message_id), "")
    elif body.get("media") is not None:
        body["media"] = {"url": media_url(row.id), **body["media"]} if row.media_id else None
    return body


@operation("whatsapp.delivery.record", kind="command", permission=PERMISSION, input=RecordIn, output=RecordOut)
def delivery_record(ctx: OperationContext, data: RecordIn) -> RecordOut:
    row = Delivery.objects.select_for_update().filter(pk=data.id).first()
    if row is None:
        return RecordOut(outcome="gone")
    now = timezone.now()
    if row.revision != data.revision:
        # Its body moved on while the older one was being pushed: the newer one is due now.
        row.next_attempt_at = now
        row.save(update_fields=["next_attempt_at"])
        return RecordOut(outcome="stale")
    if data.outcome == "drop":
        row.delete()
    elif data.outcome == "delivered":
        row.delivered_at = now
        row.last_error = ""
        row.save(update_fields=["delivered_at", "last_error"])
    else:
        row.attempts += 1
        row.last_error = data.error[:300]
        row.next_attempt_at = None if data.outcome == "refused" else now + retry_wait(row.attempts)
        row.save(update_fields=["attempts", "last_error", "next_attempt_at"])
    record_event(ctx, events.DELIVERY_RECORDED, {"delivery_id": str(data.id), "outcome": data.outcome})
    return RecordOut(outcome=data.outcome)
