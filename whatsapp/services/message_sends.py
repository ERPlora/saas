"""Door 5, ``whatsapp.message.claim`` / ``whatsapp.message.record``: a send by its ``Idempotency-Key``. The claim
reserves the month's place atomically (``UPDATE … WHERE used < limit``) before Meta is called, so two sends at once
can never both pass the cap, and a key already sent answers its first id."""

from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from hubs.queries import plan_catalog
from whatsapp import events, queries
from whatsapp.models import PhoneNumber, Send, Template, Usage
from whatsapp.schemas import SendClaimIn, SendClaimOut, SendRecordIn, SendRecordOut
from whatsapp.services.channel_snapshot import announce_channel
from whatsapp.services.platform_actor import PERMISSION

#: How long a send whose call did not end is taken as still on its way (Meta cuts a send at 30 s; the Hub's
#: retries span minutes). Past it, the same key sends again, in the place it already took.
IN_FLIGHT = timedelta(minutes=2)


def in_progress() -> OperationError:
    return OperationError(
        "This message is already being sent: retry with the same key.", code="whatsapp.send_in_progress", status=503
    )


@operation(
    "whatsapp.message.claim",
    kind="command",
    permission=PERMISSION,
    input=SendClaimIn,
    output=SendClaimOut,
    ai=INTERNAL,  # hub
)
def message_claim(ctx: OperationContext, data: SendClaimIn) -> SendClaimOut:
    """Take the place of a send in the month's allowance before Meta is called, or say why it does not leave: the
    cap is returned, not raised, so the Hub's snapshot with the month's real usage survives the refusal."""
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
            # Nothing leaves and the key stays free (a later month, or a bigger plan, sends it).
            send.delete()
            _announce_cap(hub.id, month)
            return SendClaimOut(
                outcome="refused",
                status=409,
                code="whatsapp.cap_reached",
                message="The plan's WhatsApp messages of this month are spent.",
                hub_id=hub.id,
            )
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
    plan = plan_catalog.effective_plan(hub_id, now)
    limit = plan.whatsapp_messages_per_month if plan is not None else 0
    usage, _ = Usage.objects.get_or_create(hub_id=hub_id, month=month)
    return Usage.objects.filter(pk=usage.pk, used__lt=limit).update(used=F("used") + 1) == 1


def _announce_cap(hub_id: UUID, month: str) -> None:
    """A send refused at the cap tells the Hub the month's real usage: it offered «Send», so its snapshot said less
    (one behind, or a send whose record never ran). Once per figure: refused again at the same usage (the snapshot
    already says it, or is on its way and ``reconcile_hub_states`` retries it), nothing is bumped nor pushed. One
    ``UPDATE``, which a concurrent refusal waits on and then finds told."""
    told = Usage.objects.filter(hub_id=hub_id, month=month).exclude(cap_announced_usage=F("used"))
    if told.update(cap_announced_usage=F("used")):
        announce_channel(hub_id)


@operation(
    "whatsapp.message.record",
    kind="command",
    permission=PERMISSION,
    input=SendRecordIn,
    output=SendRecordOut,
    ai=INTERNAL,  # hub
)
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
