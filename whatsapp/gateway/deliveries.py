"""What Meta reports, on its way to the Hub.

- ``ingest``: Meta's webhook, parked (``whatsapp.webhook.ingest``) and pushed at once to the Hub of each business
  it touched;
- ``deliver``: what waits for the Hub, pushed to its doors 1 and 2 and recorded as the Hub answered. Contract: 200 taken; 422 the body does not hold (never retried); anything
  else (404 ``app_inactive``, a Hub without the door, 5xx, no answer) kept and retried with a growing wait. Each
  business's messages go in the order they arrived: once its Hub did not take one, the business's next messages of
  the batch are held with its wait, and the other businesses go on. ``deliver_pass`` is one pass of it under the
  lock of ``whatsapp_deliver``, for ``PASS_BUDGET`` at most: what the ``saas-worker`` runs when it wakes
  (``base.worker``, saas#305) and the command ``whatsapp_deliver`` by hand;
- ``erase``: door 6.
"""

import logging
import threading
from datetime import timedelta

from django.utils import timezone

from hubs.services.exclusive_runs import run_exclusively
from whatsapp import hub_client
from whatsapp.gateway.message_templates import sync_templates
from whatsapp.schemas import ClaimIn, EraseIn, HeldDelivery, HoldIn, IngestIn, IngestOut, RecordIn
from whatsapp.services import delivery_queue, meta_webhook, platform_actor

logger = logging.getLogger("whatsapp.gateway")

#: How many deliveries the webhook pushes before answering Meta (the rest, the ``saas-worker``).
WEBHOOK_DELIVERIES = 20
#: How long a pass of ``deliver_pass`` may push for: each batch claims only the rows whose calls fit in what is left
#: (``hub_client.LONGEST_CALL``, 10 s each at the Hub's slowest), so the pass's last call ends by 50 s, inside
#: ``delivery_queue.LEASE`` (5 min) of every row it claimed. The worker starts the next pass at once when more is due.
PASS_BUDGET = timedelta(seconds=50)
#: How long a status waits for the Hub's key of its message before it is taken as a message the Hub never sent.
STATUS_KEY_WAIT = timedelta(minutes=10)
_COUNTED = {"delivered": "delivered", "retry": "retried", "refused": "refused", "drop": "dropped"}
#: What a batch counts: each outcome, and ``held`` (claimed and given back without a push).
COUNTS = (*_COUNTED.values(), "held")


def ingest(payload: dict) -> IngestOut:
    """Park what Meta reported and push it to the Hub now; what the Hub does not take waits for its retry."""
    out = meta_webhook.webhook_ingest(platform_actor.platform_context(), IngestIn(payload=payload))
    if out.hub_ids:
        try:
            deliver(out.hub_ids, limit=WEBHOOK_DELIVERIES)
        except Exception:  # noqa: BLE001 - parked and committed: whatsapp_deliver retries it
            logger.exception("whatsapp.deliver.crashed")
    for hub_id in out.template_hubs:
        try:
            sync_templates(hub_id)
        except Exception:  # noqa: BLE001 - the verdicts are written: the next one reads the list again
            logger.exception("whatsapp.template.sync_crashed hub_id=%s", hub_id)
    return out


def deliver(hub_ids=None, *, limit: int = 50, stop: threading.Event | None = None) -> dict[str, int]:
    """Push what is due (of ``hub_ids``, or of every business) and record each answer, in the order it arrived.

    A message of a business whose Hub did not take an earlier message of this batch is held with that one's wait
    (``delivery_queue.IN_ORDER_ATTEMPTS`` failed tries at most): it never reaches the Hub before it. ``stop`` set (the
    worker asked to stop) ends the batch after the push in course and gives the rest back, due again at once."""
    counts = dict.fromkeys(COUNTS, 0)
    ctx = platform_actor.platform_context()
    claimed = delivery_queue.delivery_claim(ctx, ClaimIn(hub_ids=hub_ids, limit=limit)).deliveries
    failed: dict = {}
    held: dict = {}
    for index, delivery in enumerate(claimed):
        if stop is not None and stop.is_set():
            held.setdefault(None, []).extend(claimed[index:])
            break
        if delivery.kind == "message" and delivery.hub_id in failed:
            held.setdefault(failed[delivery.hub_id], []).append(delivery)
            continue
        outcome, error = _push(delivery)
        answer = delivery_queue.delivery_record(
            ctx, RecordIn(id=delivery.id, revision=delivery.revision, outcome=outcome, error=error)
        )
        counts[_COUNTED[outcome]] += 1
        if (
            delivery.kind == "message"
            and outcome == "retry"
            and answer.next_attempt_at is not None
            and answer.attempts < delivery_queue.IN_ORDER_ATTEMPTS
        ):
            failed[delivery.hub_id] = answer.next_attempt_at
    for until, deliveries in held.items():
        given_back = [HeldDelivery(id=delivery.id, revision=delivery.revision) for delivery in deliveries]
        delivery_queue.delivery_hold(ctx, HoldIn(deliveries=given_back, until=until))
        counts["held"] += len(deliveries)
    return counts


def push_for(budget: timedelta, stop: threading.Event | None = None) -> dict[str, int]:
    """Batch after batch while one comes full, each one only as big as the calls that still fit in ``budget``; a
    ``stop`` set ends it after the push in course."""
    now = timezone.now()
    ends = now + budget
    totals = dict.fromkeys(COUNTS, 0)
    while (room := int((ends - now) / hub_client.LONGEST_CALL)) > 0 and not (stop is not None and stop.is_set()):
        counts = deliver(limit=room, stop=stop)
        for key, value in counts.items():
            totals[key] += value
        if sum(counts.values()) < room:
            break
        now = timezone.now()
    return totals


def deliver_pass(stop: threading.Event | None = None) -> dict[str, int] | None:
    """One pass of what is due, under the lock of ``whatsapp_deliver``: two processes never run one at once.
    ``None``: another one holds the lock, and this one pushed nothing."""
    with run_exclusively("whatsapp_deliver") as mine:
        if not mine:
            return None
        return push_for(PASS_BUDGET, stop)


def _push(delivery) -> tuple[str, str]:
    if delivery.waits_for == "message":
        return "retry", "The owner's reply it is about has not reached the Hub yet."
    if delivery.waits_for == "key":
        if delivery.received_at < timezone.now() - STATUS_KEY_WAIT:
            return "drop", ""
        return "retry", "No message the Hub sent has this id yet."
    post = hub_client.post_inbound if delivery.kind == "message" else hub_client.post_status
    try:
        answer = post(delivery.body)
    except hub_client.Unreachable as unreachable:
        return "retry", str(unreachable)[:300]
    if answer.status == 200:
        return "delivered", ""
    error = answer.body.get("error") if isinstance(answer.body, dict) else None
    code = str(error.get("code") or "") if isinstance(error, dict) else ""
    reason = f"HTTP {answer.status} {code}".strip()
    return ("refused" if answer.status == 422 else "retry"), reason


def erase(data: EraseIn) -> tuple[int, dict]:
    out = delivery_queue.message_erase(platform_actor.platform_context(), data)
    return 200, out.model_dump()
