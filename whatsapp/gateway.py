"""What erplora.com does for a business's WhatsApp, step by step: the commands of ``services`` around the calls to
Meta (``meta``) and to the Hub (``hub_client``), so that no transaction waits for a third party. No ORM here.

- ``ingest``: Meta's webhook, parked (``whatsapp.webhook.ingest``) and pushed at once to the Hub of each business
  it touched (WHATSAPP-G07);
- ``deliver``: what waits for the Hub, pushed to its doors 1 and 2 and recorded as the Hub answered
  (FIX-SAAS-WHATSAPP-GATEWAY-DOORS). Contract: 200 taken; 422 the body does not hold (never retried); anything
  else (404 ``app_inactive``, a Hub without the door, 5xx, no answer) kept and retried with a growing wait;
- ``send``: door 5. Claim (the month's place, by the key) → Meta, outside any transaction → record how it ended.
  Meta's refusal frees the place and the key; no answer keeps both (``unknown``: the same key sends again only after
  ``services.IN_FLIGHT``); a 2xx without Meta's id is sent for good, never again (saas#2653);
- ``erase``: door 6.

What a door answers is ``(status, body)``: the body of a 2xx, or the single error envelope.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from whatsapp import hub_client, meta, services
from whatsapp.schemas import ClaimIn, EraseIn, IngestIn, IngestOut, RecordIn, SendClaimIn, SendIn, SendRecordIn

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


# --- Door 5: send -----------------------------------------------------------------------------------------------

#: Meta's codes of a send it refused, by what the Hub is told (its 409 codes; any other is ``meta_rejected``).
WINDOW_CLOSED = frozenset({131047, 470})
RECIPIENT_BLOCKED = frozenset({131021, 131026, 131030, 131049, 131050})
NOT_CONNECTED = frozenset({10, 190, 200, 131031, 133010})
EXPIRED_PERMISSION = 190


def envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def send(data: SendIn, key: str) -> tuple[int, dict]:
    ctx = services.platform_context()
    template = data.template
    claim = services.message_claim(
        ctx,
        SendClaimIn(
            hub=data.hub,
            key=key,
            template_name=template.name if template else "",
            template_language=template.language if template else "",
        ),
    )
    if claim.outcome == "sent":
        return _sent(claim.wa_message_id)
    try:
        answer = meta.post(
            f"{claim.phone_number_id}/messages",
            token=claim.token.get_secret_value(),
            json=_meta_message(data),
            timeout=meta.SEND_TIMEOUT,
        )
    except meta.MetaRefused as refused:
        services.message_record(
            ctx,
            SendRecordIn(send_id=claim.send_id, outcome="released", needs_reconnect=refused.code == EXPIRED_PERMISSION),
        )
        logger.warning("whatsapp.send.refused hub=%s meta_status=%s meta_code=%s", data.hub, refused.status, refused.code)
        return _refusal(refused)
    except meta.MetaUnreachable as unreachable:
        if unreachable.sent:
            services.message_record(ctx, SendRecordIn(send_id=claim.send_id, outcome="unknown"))
            logger.warning("whatsapp.send.unknown hub=%s", data.hub)
            return 502, envelope(
                "whatsapp.meta_unknown", "Meta gave no answer: the message may have left. Retry with the same key."
            )
        services.message_record(ctx, SendRecordIn(send_id=claim.send_id, outcome="released"))
        return 503, envelope("whatsapp.meta_unreachable", "Meta could not be reached: nothing left. Retry later.")
    accepted = answer.get("messages")
    first = accepted[0] if isinstance(accepted, list) and accepted and isinstance(accepted[0], dict) else {}
    wa_message_id = str(first.get("id") or "")[:255]
    services.message_record(ctx, SendRecordIn(send_id=claim.send_id, outcome="sent", wa_message_id=wa_message_id))
    return _sent(wa_message_id)


def _sent(wa_message_id: str) -> tuple[int, dict]:
    if not wa_message_id:
        return 502, envelope(
            "whatsapp.meta_no_id", "Meta accepted the message without its id: it is not sent again with this key."
        )
    return 200, {"wa_message_id": wa_message_id}


def _meta_message(data: SendIn) -> dict:
    message = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": data.to.lstrip("+")}
    if data.type == "text":
        return {**message, "type": "text", "text": {"preview_url": False, "body": data.text}}
    template = {"name": data.template.name, "language": {"code": data.template.language}}
    if data.template.variables:
        parameters = [{"type": "text", "text": value} for value in data.template.variables]
        template["components"] = [{"type": "body", "parameters": parameters}]
    return {**message, "type": "template", "template": template}


def _refusal(refused: meta.MetaRefused) -> tuple[int, dict]:
    reason = ": ".join(part for part in (refused.message, refused.detail) if part) or f"Meta refused it (HTTP {refused.status})."
    if refused.rate_limited:
        return 429, envelope("whatsapp.meta_rate_limited", reason)
    code = refused.code
    if code in WINDOW_CLOSED:
        name = "whatsapp.window_closed"
    elif code in RECIPIENT_BLOCKED:
        name = "whatsapp.recipient_blocked"
    elif code is not None and 132000 <= code < 133000:
        name = "whatsapp.template_not_approved"
    elif code in NOT_CONNECTED:
        name = "whatsapp.not_connected"
    else:
        name = "whatsapp.meta_rejected"
    return 409, envelope(name, reason)


# --- Door 6: erase ----------------------------------------------------------------------------------------------


def erase(data: EraseIn) -> tuple[int, dict]:
    out = services.message_erase(services.platform_context(), data)
    return 200, out.model_dump()
