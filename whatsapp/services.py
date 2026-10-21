"""The commands of whatsapp (``@operation`` kind="command"): the only writes of the app, each in its transaction.

Only the platform runs them (``platform_context``): the Hub through its signed doors, Meta through its webhook, the
``saas-cron`` commands and the staff's admin actions. No account role holds ``whatsapp.manage``. A call to Meta or to
the Hub never happens inside one of these: ``gateway`` calls Meta or the Hub between two commands, so no lock waits
for a third party.

- ``whatsapp.webhook.ingest``: what Meta's webhook reported, parked once per message for each active number
  (``Delivery``), the furthest status of each message, and Meta's verdicts on the templates (WHATSAPP-G07);
- ``whatsapp.delivery.claim`` / ``whatsapp.delivery.record``: the push of what is parked to the Hub's doors 1 and 2,
  leased so two processes never push the same thing at once, and retried with a growing wait;
- ``whatsapp.message.claim`` / ``whatsapp.message.record``: door 5, a send by its ``Idempotency-Key``. The claim
  reserves the month's place atomically (``UPDATE … WHERE used < limit``) before Meta is called, so two sends at once
  can never both pass the cap (saas#2652), and a key already sent answers its first id (saas#2633);
- ``whatsapp.message.erase``: door 6, what is kept of a customer's number for a business is forgotten;
- ``whatsapp.template.claim`` / ``whatsapp.template.record``: door 8, a template's registration at Meta by its
  ``Idempotency-Key``: a key Meta took answers what it said the first time, never registers again;
- ``whatsapp.template.forget`` / ``whatsapp.template.sync``: the mirror of Meta's templates, after a deletion at
  Meta (door 9) and when Meta's list is read again; ``whatsapp.number.reconnect_needed``: Meta refused the token;
- ``whatsapp.number.renewal`` / ``whatsapp.number.alerted``: the daily renewal of Meta's permission (WHATSAPP-G12),
  the mark «needs reconnecting» and the owner told once per incident;
- ``whatsapp.number.connect`` / ``whatsapp.number.disconnect``: the number a business connected through Meta's
  window (door 11, WHATSAPP-G01) and its disconnection (door 12, WHATSAPP-G02);
- ``whatsapp.retention.purge``: the daily forgetting of what the Hub took, of what it never took and of the keys
  (WHATSAPP-G14).

A refusal raises the envelope's error (``live.errors``): the transaction rolls back, the reservation with it.
"""

import logging
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, NotFound, OperationError
from live.operations import operation
from live.outbox import record_event

from hubs import queries as hubs_queries
from hubs import services as hubs_services
from hubs.models import HubMember
from whatsapp import events, parse, queries
from whatsapp.models import Delivery, PhoneNumber, Send, Template, TemplateSubmission, Usage
from whatsapp.schemas import (
    AlertedIn,
    AlertedOut,
    ClaimedDelivery,
    ClaimIn,
    ClaimOut,
    EraseIn,
    EraseOut,
    DisconnectIn,
    IngestIn,
    IngestOut,
    NumberConnectIn,
    NumberConnectOut,
    NumberDisconnectOut,
    PurgeIn,
    PurgeOut,
    ReconnectIn,
    ReconnectOut,
    RecordIn,
    RecordOut,
    ReconnectAlert,
    RenewalIn,
    RenewalOut,
    SendClaimIn,
    SendClaimOut,
    SendRecordIn,
    SendRecordOut,
    TemplateClaimIn,
    TemplateClaimOut,
    TemplateForgetIn,
    TemplateForgetOut,
    TemplateRecordIn,
    TemplateRecordOut,
    TemplateSyncIn,
    TemplateSyncOut,
)

logger = logging.getLogger(__name__)

PERMISSION = queries.PERMISSION
#: How long a claimed delivery is held for its push before another run may take it again.
LEASE = timedelta(minutes=2)
#: The first wait after the Hub did not take a delivery; each next one doubles, up to ``LONGEST_WAIT``.
FIRST_WAIT = timedelta(seconds=30)
LONGEST_WAIT = timedelta(hours=1)
#: How far each delivery status is; ``failed`` replaces anything but ``read``, and nothing replaces it.
STATUS_RANK = {"sent": 1, "delivered": 2, "read": 3}
#: How long a send whose call did not end is taken as still on its way (Meta cuts a send at 30 s; the Hub's
#: retries span minutes). Past it, the same key sends again, in the place it already took.
IN_FLIGHT = timedelta(minutes=2)


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
    # A number of a business that left (being deleted or purged) takes nothing any more.
    numbers = dict(
        PhoneNumber.objects.filter(
            phone_number_id__in=named, is_active=True, hub__status__in=hubs_services.LIVE_STATUSES
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


# --- Door 5: a send by its Idempotency-Key ----------------------------------------------------------------------


def in_progress() -> OperationError:
    return OperationError(
        "This message is already being sent: retry with the same key.", code="whatsapp.send_in_progress", status=503
    )


@operation("whatsapp.message.claim", kind="command", permission=PERMISSION, input=SendClaimIn, output=SendClaimOut)
def message_claim(ctx: OperationContext, data: SendClaimIn) -> SendClaimOut:
    """Take the place of a send in the month's allowance before Meta is called, or say why it does not leave."""
    hub = queries.known_hub(data.hub)
    if hub is None:
        raise queries.unknown_hub()
    now = timezone.now()
    existing = Send.objects.select_for_update().filter(hub=hub, idempotency_key=data.key).first()
    if existing is not None and existing.state == Send.State.SENT:
        return SendClaimOut(outcome="sent", send_id=existing.id, hub_id=hub.id, wa_message_id=existing.wa_message_id)
    if existing is not None and existing.updated_at > now - IN_FLIGHT:
        raise in_progress()
    number = PhoneNumber.objects.filter(hub=hub, is_active=True).first()
    if number is None or not number.access_token:
        raise queries.not_connected()
    if data.template_name:
        template = Template.objects.filter(hub=hub, name=data.template_name, language=data.template_language).first()
        if template is not None and template.status != Template.Status.APPROVED:
            raise Conflict(
                f"Meta has not approved the template «{template.name}» ({template.status}).",
                code="whatsapp.template_not_approved",
            )
    if existing is not None:
        # An earlier call with this key died or got no answer from Meta: it sends again in the place it took.
        existing.state = Send.State.PENDING
        existing.save(update_fields=["state", "updated_at"])
        send = existing
    else:
        month = now.strftime("%Y-%m")
        try:
            with transaction.atomic():
                send = Send.objects.create(hub=hub, idempotency_key=data.key, month=month)
        except IntegrityError:
            # Another call with the same key claimed it a moment ago.
            raise in_progress() from None
        if not _reserve(hub.id, month, now):
            raise Conflict("The plan's WhatsApp messages of this month are spent.", code="whatsapp.cap_reached")
    return SendClaimOut(
        outcome="claimed",
        send_id=send.id,
        hub_id=hub.id,
        phone_number_id=number.phone_number_id,
        token=number.access_token,
    )


def _reserve(hub_id: UUID, month: str, now) -> bool:
    """One more message of ``month`` if the plan's allowance has room: one ``UPDATE … WHERE used < limit``, which a
    concurrent send waits on and then evaluates again (0 = the plan includes none)."""
    plan = hubs_queries.effective_plan(hub_id, now)
    limit = plan.whatsapp_messages_per_month if plan is not None else 0
    usage, _ = Usage.objects.get_or_create(hub_id=hub_id, month=month)
    return Usage.objects.filter(pk=usage.pk, used__lt=limit).update(used=F("used") + 1) == 1


@operation("whatsapp.message.record", kind="command", permission=PERMISSION, input=SendRecordIn, output=SendRecordOut)
def message_record(ctx: OperationContext, data: SendRecordIn) -> SendRecordOut:
    """How Meta ended a claimed send: sent (its id), unknown (the place stays taken) or released (nothing left)."""
    send = Send.objects.select_for_update().filter(pk=data.send_id).first()
    if send is None:
        return SendRecordOut(outcome="gone")
    hub_id = send.hub_id
    if data.outcome == "released":
        Usage.objects.filter(hub_id=hub_id, month=send.month, used__gt=0).update(used=F("used") - 1)
        send.delete()
    else:
        send.state = Send.State.SENT if data.outcome == "sent" else Send.State.UNKNOWN
        send.wa_message_id = data.wa_message_id
        send.save(update_fields=["state", "wa_message_id", "updated_at"])
    if data.needs_reconnect:
        PhoneNumber.objects.filter(hub_id=hub_id, is_active=True).update(needs_reconnect=True)
    if data.outcome != "released" or data.needs_reconnect:
        # The month's usage (or the number's state) moved: the Hub learns it in its snapshot.
        announce_channel(hub_id)
    record_event(ctx, events.MESSAGE_RECORDED, {"send_id": str(data.send_id), "outcome": data.outcome})
    return SendRecordOut(outcome=data.outcome)


# --- Door 6: forgetting a customer's number ---------------------------------------------------------------------


@operation("whatsapp.message.erase", kind="command", permission=PERMISSION, input=EraseIn, output=EraseOut)
def message_erase(ctx: OperationContext, data: EraseIn) -> EraseOut:
    """Forget what is kept of ``phone`` for the business: its messages waiting for (or already taken by) the Hub and
    the statuses of the messages it names. Nothing of another business is touched."""
    hub = queries.known_hub(data.hub, live=False)
    if hub is None:
        raise queries.unknown_hub()
    contact = "".join(ch for ch in data.phone if ch.isdigit())
    named = Q(contact=contact) | Q(wa_message_id__in=data.wa_message_ids) if data.wa_message_ids else Q(contact=contact)
    erased, _ = Delivery.objects.filter(named, hub=hub).delete()
    record_event(ctx, events.MESSAGE_ERASED, {"hub_id": str(hub.id), "rows": erased})
    return EraseOut(erased=True)


# --- Doors 8 and 9: the business's templates at Meta -----------------------------------------------------------

#: What the mirror takes of a template (``templates.mirror`` / ``templates.from_meta``), besides its name and language.
MIRRORED = (
    "category", "status", "rejected_reason", "meta_id", "header_format", "header", "body", "body_examples", "footer",
    "buttons", "variables",
)


def template_in_progress() -> OperationError:
    return OperationError(
        "This template is already being registered: retry with the same key.",
        code="whatsapp.template_in_progress",
        status=503,
    )


@operation(
    "whatsapp.template.claim", kind="command", permission=PERMISSION, input=TemplateClaimIn, output=TemplateClaimOut
)
def template_claim(ctx: OperationContext, data: TemplateClaimIn) -> TemplateClaimOut:
    """Take a template's registration by its key before Meta is called, or answer what Meta said the first time."""
    hub = queries.known_hub(data.hub)
    if hub is None:
        raise queries.unknown_hub()
    existing = TemplateSubmission.objects.select_for_update().filter(hub=hub, idempotency_key=data.key).first()
    if existing is not None and existing.state == TemplateSubmission.State.DONE:
        return TemplateClaimOut(
            outcome="done", submission_id=existing.id, hub_id=hub.id, meta_id=existing.meta_id, status=existing.status
        )
    if existing is not None and existing.updated_at > timezone.now() - IN_FLIGHT:
        raise template_in_progress()
    number = PhoneNumber.objects.filter(hub=hub, is_active=True).first()
    if number is None or not number.access_token:
        raise queries.not_connected()
    if existing is not None:
        # An earlier call with this key died on its way: this one registers it.
        existing.save(update_fields=["updated_at"])
        submission = existing
    else:
        try:
            with transaction.atomic():
                submission = TemplateSubmission.objects.create(hub=hub, idempotency_key=data.key)
        except IntegrityError:
            raise template_in_progress() from None
    return TemplateClaimOut(
        outcome="claimed", submission_id=submission.id, hub_id=hub.id, waba_id=number.waba_id, token=number.access_token
    )


@operation(
    "whatsapp.template.record", kind="command", permission=PERMISSION, input=TemplateRecordIn, output=TemplateRecordOut
)
def template_record(ctx: OperationContext, data: TemplateRecordIn) -> TemplateRecordOut:
    """How Meta ended a claimed registration: taken (the mirror keeps it, the Hub learns it) or not (the key is
    forgotten, free to try again)."""
    submission = TemplateSubmission.objects.select_for_update().filter(pk=data.submission_id).first()
    if submission is None:
        return TemplateRecordOut(outcome="gone")
    if data.outcome == "released":
        submission.delete()
        return TemplateRecordOut(outcome="released")
    submission.state = TemplateSubmission.State.DONE
    submission.meta_id = str(data.mirror.get("meta_id") or "")
    submission.status = str(data.mirror.get("status") or "")
    submission.save(update_fields=["state", "meta_id", "status", "updated_at"])
    _mirror(submission.hub_id, data.mirror)
    announce_channel(submission.hub_id)
    record_event(
        ctx,
        events.TEMPLATE_REGISTERED,
        {"hub_id": str(submission.hub_id), "meta_id": submission.meta_id, "status": submission.status},
    )
    return TemplateRecordOut(outcome="done")


@operation(
    "whatsapp.template.forget", kind="command", permission=PERMISSION, input=TemplateForgetIn, output=TemplateForgetOut
)
def template_forget(ctx: OperationContext, data: TemplateForgetIn) -> TemplateForgetOut:
    """That one template, in that language, leaves the mirror: Meta deleted it or no longer has it."""
    deleted, _ = Template.objects.filter(hub_id=data.hub_id, name=data.name, language=data.language).delete()
    if deleted:
        announce_channel(data.hub_id)
        record_event(ctx, events.TEMPLATE_FORGOTTEN, {"hub_id": str(data.hub_id)})
    return TemplateForgetOut(forgotten=bool(deleted))


@operation(
    "whatsapp.template.sync", kind="command", permission=PERMISSION, input=TemplateSyncIn, output=TemplateSyncOut
)
def template_sync(ctx: OperationContext, data: TemplateSyncIn) -> TemplateSyncOut:
    """Write Meta's list of the business's templates on the mirror. What the list lacks is deleted only when it came
    whole: a list cut short says nothing of what it did not reach."""
    seen: set[tuple[str, str]] = set()
    changed = False
    for item in data.items:
        seen.add((item["name"], item["language"]))
        changed = _mirror(data.hub_id, item) or changed
    if data.complete:
        rows = Template.objects.filter(hub_id=data.hub_id).values_list("pk", "name", "language")
        lost = [pk for pk, name, language in rows if (name, language) not in seen]
        if lost:
            Template.objects.filter(pk__in=lost).delete()
            changed = True
    if changed:
        announce_channel(data.hub_id)
    record_event(ctx, events.TEMPLATES_SYNCED, {"hub_id": str(data.hub_id), "complete": data.complete})
    return TemplateSyncOut(changed=changed)


def _mirror(hub_id: UUID, item: dict) -> bool:
    """Keep ``item`` (a template as the mirror keeps it) for the business; whether anything changed."""
    values = {name: item[name] for name in MIRRORED if name in item}
    named = Template.objects.select_for_update().filter(hub_id=hub_id, name=item["name"], language=item["language"])
    row = named.first()
    if row is None:
        Template.objects.create(hub_id=hub_id, name=item["name"], language=item["language"], **values)
        return True
    if all(getattr(row, name) == value for name, value in values.items()):
        return False
    for name, value in values.items():
        setattr(row, name, value)
    row.save()
    return True


@operation(
    "whatsapp.number.reconnect_needed", kind="command", permission=PERMISSION, input=ReconnectIn, output=ReconnectOut
)
def number_reconnect_needed(ctx: OperationContext, data: ReconnectIn) -> ReconnectOut:
    """Meta refused the business's permission (an expired or withdrawn token): only connecting again fixes it, and
    the Hub shows it from its snapshot."""
    changed = PhoneNumber.objects.filter(hub_id=data.hub_id, is_active=True, needs_reconnect=False).update(
        needs_reconnect=True
    )
    if changed:
        announce_channel(data.hub_id)
        record_event(ctx, events.NUMBER_RECONNECT_NEEDED, {"hub_id": str(data.hub_id)})
    return ReconnectOut(changed=bool(changed))


# --- The renewal of Meta's permission (WHATSAPP-G12) -------------------------------------------------------------

#: Inside this many days (or past the deadline) the owner is told even without Meta's verdict.
LAST_CALL = timedelta(days=3)


@operation("whatsapp.number.renewal", kind="command", permission=PERMISSION, input=RenewalIn, output=RenewalOut)
def number_renewal(ctx: OperationContext, data: RenewalIn) -> RenewalOut:
    """Write how a renewal ended: the fresh token and its deadline, or the mark «needs reconnecting» when Meta said
    no (or gave no verdict and the deadline is too close to wait). The owner is to be told the first time in an
    incident: the alert says to whom; ``whatsapp.number.alerted`` notes it once the mail left."""
    number = PhoneNumber.objects.select_for_update().select_related("hub").filter(pk=data.number_id).first()
    if number is None or not number.is_active:
        return RenewalOut(needs_reconnect=False)
    was_marked = number.needs_reconnect
    if data.outcome == "renewed":
        number.access_token = data.token.get_secret_value()
        number.token_expires_at = data.expires_at
        number.needs_reconnect = False
        number.reconnect_alerted_at = None
        number.save(
            update_fields=["access_token", "token_expires_at", "needs_reconnect", "reconnect_alerted_at", "updated_at"]
        )
        if was_marked:
            announce_channel(number.hub_id)
        return RenewalOut(needs_reconnect=False)
    out_of_runway = number.token_expires_at is not None and number.token_expires_at <= timezone.now() + LAST_CALL
    if data.outcome == "unverified" and not out_of_runway:
        return RenewalOut(needs_reconnect=was_marked)
    if not was_marked:
        number.needs_reconnect = True
        number.save(update_fields=["needs_reconnect", "updated_at"])
        announce_channel(number.hub_id)
        record_event(ctx, events.NUMBER_RECONNECT_NEEDED, {"hub_id": str(number.hub_id)})
    if number.reconnect_alerted_at is not None:
        return RenewalOut(needs_reconnect=True)
    owners = HubMember.objects.select_related("user").filter(hub_id=number.hub_id, role=HubMember.Role.OWNER)
    owner = owners.first()
    if owner is None or not owner.user.email:
        logger.error("whatsapp.token.no_owner_to_tell hub_id=%s", number.hub_id)
        return RenewalOut(needs_reconnect=True)
    alert = ReconnectAlert(
        to=owner.user.email,
        language=owner.user.language or settings.LANGUAGE_CODE,
        business=number.hub.name,
        number=number.display_phone,
        slug=number.hub.slug,
    )
    return RenewalOut(needs_reconnect=True, alert=alert)


@operation("whatsapp.number.alerted", kind="command", permission=PERMISSION, input=AlertedIn, output=AlertedOut)
def number_alerted(ctx: OperationContext, data: AlertedIn) -> AlertedOut:
    """The owner was told: no other mail in this incident."""
    alerted = PhoneNumber.objects.filter(pk=data.number_id, reconnect_alerted_at__isnull=True).update(
        reconnect_alerted_at=timezone.now()
    )
    return AlertedOut(alerted=bool(alerted))


# --- Connecting a number (WHATSAPP-G01, WHATSAPP-G02) -----------------------------------------------------------


@operation(
    "whatsapp.number.connect", kind="command", permission=PERMISSION, input=NumberConnectIn, output=NumberConnectOut
)
def number_connect(ctx: OperationContext, data: NumberConnectIn) -> NumberConnectOut:
    """Keep the number Meta just let the business use: its permission and PIN encrypted, active, without the mark
    «needs reconnecting». A number has one owner in the whole platform: one another business had moves here, and
    that business learns it lost it. The business's previous number stops and forgets its permission."""
    now = timezone.now()
    number = PhoneNumber.objects.select_for_update().filter(phone_number_id=data.phone_number_id).first()
    moved_from = number.hub_id if number is not None and number.hub_id != data.hub_id else None
    previous = PhoneNumber.objects.select_for_update().filter(hub_id=data.hub_id, is_active=True)
    for old in previous.exclude(phone_number_id=data.phone_number_id):
        _stop(old, now)
    if number is None:
        number = PhoneNumber(phone_number_id=data.phone_number_id)
    number.hub_id = data.hub_id
    number.display_phone = data.display_phone[:32]
    number.display_name = data.display_name[:200]
    number.waba_id = data.waba_id
    number.business_id = data.business_id
    number.access_token = data.token.get_secret_value()
    number.registration_pin = data.pin.get_secret_value()
    number.is_on_biz_app = data.is_on_biz_app
    number.token_expires_at = data.expires_at
    number.is_active = True
    number.needs_reconnect = False
    number.reconnect_alerted_at = None
    number.connected_at = now
    number.disconnected_at = None
    number.save()
    announce_channel(data.hub_id)
    if moved_from is not None:
        logger.warning("whatsapp.number.moved from_hub_id=%s to_hub_id=%s", moved_from, data.hub_id)
        announce_channel(moved_from)
    record_event(
        ctx,
        events.NUMBER_CONNECTED,
        {
            "hub_id": str(data.hub_id),
            "moved_from": str(moved_from) if moved_from else None,
            "is_on_biz_app": data.is_on_biz_app,
        },
    )
    return NumberConnectOut(moved_from=moved_from)


def _stop(number: PhoneNumber, now) -> None:
    """The number takes and sends nothing more and forgets Meta's permission; its PIN stays, to register it again."""
    number.is_active = False
    number.access_token = ""
    number.needs_reconnect = False
    number.reconnect_alerted_at = None
    number.disconnected_at = now
    number.save(
        update_fields=[
            "is_active", "access_token", "needs_reconnect", "reconnect_alerted_at", "disconnected_at", "updated_at"
        ]
    )


@operation(
    "whatsapp.number.disconnect", kind="command", permission=PERMISSION, input=DisconnectIn, output=NumberDisconnectOut
)
def number_disconnect(ctx: OperationContext, data: DisconnectIn) -> NumberDisconnectOut:
    """Stop the business's number: what Meta reports of it is discarded from now on and nothing is sent with it.
    Says the account and the permission just forgotten, so the app is unsubscribed at Meta after the COMMIT unless
    another connected number still uses that account."""
    hub = queries.known_hub(data.hub, live=False)
    if hub is None:
        raise queries.unknown_hub()
    number = PhoneNumber.objects.select_for_update().filter(hub=hub, is_active=True).first()
    if number is None:
        return NumberDisconnectOut(disconnected=False)
    token = number.access_token
    _stop(number, timezone.now())
    in_use = PhoneNumber.objects.filter(waba_id=number.waba_id, is_active=True).exists()
    announce_channel(hub.id)
    record_event(ctx, events.NUMBER_DISCONNECTED, {"hub_id": str(hub.id)})
    return NumberDisconnectOut(
        disconnected=True, waba_id=number.waba_id, token=token or None, account_in_use=in_use
    )


# --- The retention (WHATSAPP-G14) --------------------------------------------------------------------------------


@operation("whatsapp.retention.purge", kind="command", permission=PERMISSION, input=PurgeIn, output=PurgeOut)
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
