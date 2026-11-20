"""What waits for the Hub (``Delivery``): its push to the Hub's doors 1 and 2, and its forgetting through door 6.

- ``whatsapp.delivery.claim`` / ``whatsapp.delivery.record`` / ``whatsapp.delivery.hold``: the push of what is parked
  to the Hub's doors 1 and 2, leased so two processes never push the same thing at once, each business's messages in
  the order they arrived (``queries.behind_a_waiting_message``), retried with a growing wait, and given back unpushed
  (held behind a message of their business the Hub did not take, or a worker asked to stop). What makes a delivery
  due or moves its wait wakes the ``saas-worker`` after the COMMIT (``wake_the_worker``, saas#305);
- ``whatsapp.delivery.due_now``: the staff's «Push to the Hub now»;
- ``whatsapp.message.erase``: door 6, what is kept of a customer's number for a business is forgotten.
"""

import logging
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, on_commit, operation
from live.outbox import record_event

from whatsapp import events, queries
from whatsapp.models import Delivery, Send
from whatsapp.schemas import (
    ClaimedDelivery,
    ClaimIn,
    ClaimOut,
    DueNowIn,
    DueNowOut,
    EraseIn,
    EraseOut,
    HoldIn,
    HoldOut,
    RecordIn,
    RecordOut,
)
from whatsapp.services.platform_actor import PERMISSION

logger = logging.getLogger("whatsapp.services")

#: How long a claimed delivery is held for its push before another run may take it again: longer than the slowest
#: claim takes to push (``hub_client.LONGEST_CALL``, 10 s a call): Meta's webhook, 20 calls (200 s); a pass of
#: ``whatsapp_deliver``, 50 s. A claim whose run died is retried once it ends.
LEASE = timedelta(minutes=5)
#: The first wait after the Hub did not take a delivery; each next one doubles, up to ``LONGEST_WAIT``.
FIRST_WAIT = timedelta(seconds=30)
LONGEST_WAIT = timedelta(hours=1)
#: The lock of a business's deliveries, which each claim holds until its COMMIT (``pg_try_advisory_xact_lock`` of two
#: keys: this namespace and the business): a claim never takes a message of a business while another claim of it has
#: an older one locked and leased but not committed yet, which it would skip (``SKIP LOCKED``) without seeing it wait.
CLAIM_LOCK = "erplora.saas.whatsapp_delivery"
#: The channel the ``saas-worker`` LISTENs on (``base.worker``): a delivery due or whose wait moved, after the COMMIT.
DELIVERY_CHANNEL = "whatsapp_delivery"
IN_ORDER_ATTEMPTS = queries.IN_ORDER_ATTEMPTS


def media_url(delivery_id: UUID) -> str:
    """Where the business's people open an attachment: erplora.com's own origin (the only one the Hub accepts)."""
    return f"{settings.WHATSAPP_MEDIA_BASE_URL}/whatsapp/media/{delivery_id}"


def retry_wait(attempts: int) -> timedelta:
    return min(FIRST_WAIT * (2 ** max(attempts - 1, 0)), LONGEST_WAIT)


def wake_the_worker() -> None:
    """Tell the ``saas-worker`` a delivery is due or its wait moved, so it reads again when to wake; called after the
    COMMIT (``on_commit``), so it never wakes for a row it cannot see yet nor for one rolled back."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify(%s, '')", [DELIVERY_CHANNEL])


@operation(
    "whatsapp.delivery.claim",
    kind="command",
    permission=PERMISSION,
    input=ClaimIn,
    output=ClaimOut,
    ai=INTERNAL,  # hub
)
def delivery_claim(ctx: OperationContext, data: ClaimIn) -> ClaimOut:
    """Lease what is due (oldest first) for ``LEASE``: another run skips it meanwhile (a row it holds locked, by
    ``SKIP LOCKED``; one it leased, by its time). A message waiting behind an older one of its business is left
    (``queries.behind_a_waiting_message``), and so is every business another claim is taking now (``CLAIM_LOCK``,
    held until this COMMIT): it goes in the next turn."""
    now = timezone.now()
    due = Delivery.objects.filter(delivered_at__isnull=True, next_attempt_at__lte=now).exclude(
        queries.behind_a_waiting_message(now)
    )
    if data.hub_ids is not None:
        due = due.filter(hub_id__in=data.hub_ids)
    oldest = due.order_by("received_at", "id").values_list("hub_id", flat=True)[: data.limit]
    mine = _lock_businesses(sorted(set(oldest), key=str))
    rows = list(
        due.filter(hub_id__in=mine)
        .select_for_update(skip_locked=True, of=("self",))
        .select_related("hub")
        .order_by("received_at", "id")[: data.limit]
    )
    Delivery.objects.filter(pk__in=[row.pk for row in rows]).update(next_attempt_at=now + LEASE)
    statuses = [row for row in rows if row.kind == Delivery.Kind.STATUS]
    keys, replies = _client_keys(statuses), _phone_replies(statuses)
    return ClaimOut(
        deliveries=[
            ClaimedDelivery(
                id=row.id,
                hub_id=row.hub_id,
                kind=row.kind,
                revision=row.revision,
                received_at=row.received_at,
                body=_door_body(row, keys),
                waits_for=_waits_for(row, keys, replies),
            )
            for row in rows
        ]
    )


def _lock_businesses(hub_ids: list[UUID]) -> list[UUID]:
    """The businesses of ``hub_ids`` whose ``CLAIM_LOCK`` this transaction took (never waiting for one another claim
    holds; the ones it holds already, again)."""
    if not hub_ids:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT hub FROM unnest(%s::uuid[]) AS hub WHERE pg_try_advisory_xact_lock(hashtext(%s), hashtext(hub::text))",
            [hub_ids, CLAIM_LOCK],
        )
        return [hub for (hub,) in cursor.fetchall()]


def _client_keys(statuses: list[Delivery]) -> dict[tuple[UUID, str], str]:
    """The Hub's key (its ``Idempotency-Key``) of each message whose status is pushed: door 2 always carries it."""
    if not statuses:
        return {}
    sends = Send.objects.filter(
        hub_id__in={row.hub_id for row in statuses}, wa_message_id__in={row.wa_message_id for row in statuses}
    ).values_list("hub_id", "wa_message_id", "idempotency_key")
    return {(hub_id, wa_message_id): key for hub_id, wa_message_id, key in sends}


def _phone_replies(statuses: list[Delivery]) -> dict[tuple[UUID, str], bool]:
    """The owner's replies from the phone (Meta's echoes) erplora.com hands the Hub as the business's messages, by
    WhatsApp id: whether the Hub took each. One the Hub refused (422) is not here: its status has nowhere to go."""
    if not statuses:
        return {}
    replies = Delivery.objects.filter(
        kind=Delivery.Kind.MESSAGE,
        body__direction="outbound",
        hub_id__in={row.hub_id for row in statuses},
        wa_message_id__in={row.wa_message_id for row in statuses},
    ).exclude(delivered_at__isnull=True, next_attempt_at__isnull=True)
    return {
        (hub_id, wa_message_id): delivered_at is not None
        for hub_id, wa_message_id, delivered_at in replies.values_list("hub_id", "wa_message_id", "delivered_at")
    }


def _waits_for(row: Delivery, keys: dict[tuple[UUID, str], str], replies: dict[tuple[UUID, str], bool]) -> str:
    """What a status still needs before door 2: nothing with the Hub's key, or for a reply the Hub took (it keeps
    those without a key of its own); the reply itself while it is on its way; else the key (a send's answer can be
    stored a moment after Meta's status arrives)."""
    if row.kind != Delivery.Kind.STATUS or (row.hub_id, row.wa_message_id) in keys:
        return ""
    taken = replies.get((row.hub_id, row.wa_message_id))
    return "key" if taken is None else "" if taken else "message"


def _door_body(row: Delivery, keys: dict[tuple[UUID, str], str]) -> dict:
    body = {"hub": row.hub.slug, **row.body}
    if row.kind == Delivery.Kind.STATUS:
        if (row.hub_id, row.wa_message_id) in keys:
            body["client_message_id"] = keys[(row.hub_id, row.wa_message_id)]
    elif body.get("media") is not None:
        body["media"] = {"url": media_url(row.id), **body["media"]} if row.media_id else None
    return body


@operation(
    "whatsapp.delivery.record",
    kind="command",
    permission=PERMISSION,
    input=RecordIn,
    output=RecordOut,
    ai=INTERNAL,  # hub
)
def delivery_record(ctx: OperationContext, data: RecordIn) -> RecordOut:
    row = Delivery.objects.select_for_update().filter(pk=data.id).first()
    if row is None:
        return RecordOut(outcome="gone")
    now = timezone.now()
    if row.revision != data.revision:
        # Its body moved on while the older one was being pushed: the newer one is due now.
        row.next_attempt_at = now
        row.save(update_fields=["next_attempt_at"])
        on_commit(wake_the_worker)
        return RecordOut(outcome="stale", next_attempt_at=now, attempts=row.attempts)
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
        if row.next_attempt_at is not None:
            on_commit(wake_the_worker)
            if row.kind == Delivery.Kind.MESSAGE and row.attempts == IN_ORDER_ATTEMPTS:
                # From now on the newer messages of the business go on without it (``queries.IN_ORDER_ATTEMPTS``).
                logger.warning(
                    "saas.worker.order_released hub=%s delivery=%s attempts=%s", row.hub_id, row.id, row.attempts
                )
    record_event(ctx, events.DELIVERY_RECORDED, {"delivery_id": str(data.id), "outcome": data.outcome})
    waits = data.outcome == "retry"
    return RecordOut(
        outcome=data.outcome, next_attempt_at=row.next_attempt_at if waits else None, attempts=row.attempts
    )


@operation(
    "whatsapp.delivery.hold",
    kind="command",
    permission=PERMISSION,
    input=HoldIn,
    output=HoldOut,
    ai=INTERNAL,  # worker
)
def delivery_hold(ctx: OperationContext, data: HoldIn) -> HoldOut:
    """Give claimed deliveries back without a push: due again at ``until`` (now when missing), no attempt counted. One
    whose body moved on meanwhile (another revision) is left as it is: it is due already."""
    claimed = Q(pk__in=[])
    for held in data.deliveries:
        claimed |= Q(pk=held.id, revision=held.revision)
    until = data.until or timezone.now()
    count = Delivery.objects.filter(claimed, delivered_at__isnull=True).update(next_attempt_at=until)
    if count:
        on_commit(wake_the_worker)
    return HoldOut(held=count)


@operation(
    "whatsapp.delivery.due_now",
    kind="command",
    permission=PERMISSION,
    input=DueNowIn,
    output=DueNowOut,
    ai=INTERNAL,  # hub
)
def delivery_due_now(ctx: OperationContext, data: DueNowIn) -> DueNowOut:
    """What still waits for the Hub among ``ids`` is due now, also one the Hub refused as it was (422), once the
    Hub is fixed. What the Hub already took is left as it is."""
    waiting = Delivery.objects.filter(pk__in=data.ids, delivered_at__isnull=True)
    hub_ids = sorted(set(waiting.values_list("hub_id", flat=True)), key=str)
    count = waiting.update(next_attempt_at=timezone.now())
    if count:
        on_commit(wake_the_worker)
    return DueNowOut(hub_ids=hub_ids, count=count)


@operation(
    "whatsapp.message.erase",
    kind="command",
    permission=PERMISSION,
    input=EraseIn,
    output=EraseOut,
    ai=INTERNAL,  # hub
)
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
