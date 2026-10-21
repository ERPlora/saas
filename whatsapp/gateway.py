"""What erplora.com does for a business's WhatsApp, step by step: the commands of ``services`` around the calls to
Meta (``meta``) and to the Hub (``hub_client``), so that no transaction waits for a third party. No ORM here.

- ``ingest``: Meta's webhook, parked (``whatsapp.webhook.ingest``) and pushed at once to the Hub of each business
  it touched (WHATSAPP-G07);
- ``deliver``: what waits for the Hub, pushed to its doors 1 and 2 and recorded as the Hub answered
  (FIX-SAAS-WHATSAPP-GATEWAY-DOORS). Contract: 200 taken; 422 the body does not hold (never retried); anything
  else (404 ``app_inactive``, a Hub without the door, 5xx, no answer) kept and retried with a growing wait.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from whatsapp import hub_client, services
from whatsapp.schemas import ClaimIn, IngestIn, IngestOut, RecordIn

logger = logging.getLogger(__name__)

#: How many deliveries the webhook pushes before answering Meta (the rest, ``whatsapp_deliver``).
WEBHOOK_DELIVERIES = 20
#: How long a status waits for the Hub's key of its message before it is taken as a message the Hub never sent.
STATUS_KEY_WAIT = timedelta(minutes=10)
_COUNTED = {"delivered": "delivered", "retry": "retried", "refused": "refused", "drop": "dropped"}


def ingest(payload: dict) -> IngestOut:
    """Park what Meta reported and push it to the Hub now; what the Hub does not take waits for its retry."""
    out = services.webhook_ingest(services.platform_context(), IngestIn(payload=payload))
    if out.hub_ids:
        try:
            deliver(out.hub_ids, limit=WEBHOOK_DELIVERIES)
        except Exception:  # noqa: BLE001 - parked and committed: whatsapp_deliver retries it
            logger.exception("whatsapp.deliver.crashed")
    return out


def deliver(hub_ids=None, *, limit: int = 50) -> dict[str, int]:
    """Push what is due (of ``hub_ids``, or of every business) and record each answer."""
    counts = dict.fromkeys(_COUNTED.values(), 0)
    ctx = services.platform_context()
    claimed = services.delivery_claim(ctx, ClaimIn(hub_ids=hub_ids, limit=limit)).deliveries
    for delivery in claimed:
        outcome, error = _push(delivery)
        services.delivery_record(ctx, RecordIn(id=delivery.id, revision=delivery.revision, outcome=outcome, error=error))
        counts[_COUNTED[outcome]] += 1
    return counts


def _push(delivery) -> tuple[str, str]:
    if delivery.kind == "status" and not delivery.body.get("client_message_id"):
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
