"""Door 5: send. Claim (the month's place, by the key) → Meta, outside any transaction → record how it ended. The
cap refuses before Meta (409 ``whatsapp.cap_reached``), the claim committed so the Hub gets the month's real usage
in its snapshot (once per figure, WHATSAPP-F05).
Meta's refusal frees the place and the key; no answer keeps both (``unknown``: the same key sends again only after
``message_sends.IN_FLIGHT``); a 2xx without Meta's id is sent for good, never again. Meta's 190 (the
permission expired or withdrawn) is ``whatsapp.reconnect_needed`` and marks the number «needs reconnecting». A
template whose header is a photo, a video or a document carries its file (``templates.send_sample``: 409
``whatsapp.template_invalid`` before the claim when Meta would refuse it); after the claim it is uploaded to the
number (``meta.upload_media``) and the message names its id. The upload sends no message: its refusal or silence
frees the place and the key (the same 409 with a name, or 503 ``whatsapp.meta_unreachable``).
"""

import logging
from uuid import UUID

from live.context import OperationContext

from whatsapp import meta, templates
from whatsapp.gateway.answers import (
    EXPIRED_PERMISSION,
    NOT_CONNECTED,
    RECIPIENT_BLOCKED,
    WINDOW_CLOSED,
    envelope,
)
from whatsapp.schemas import SendClaimIn, SendClaimOut, SendIn, SendRecordIn
from whatsapp.services import message_sends, platform_actor

logger = logging.getLogger("whatsapp.gateway")


def send(data: SendIn, key: str) -> tuple[int, dict]:
    ctx = platform_actor.platform_context()
    template = data.template
    try:
        sample = templates.send_sample(template) if template is not None else None
    except templates.Invalid as invalid:
        return 409, envelope("whatsapp.template_invalid", str(invalid))
    claim = message_sends.message_claim(
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
    if claim.outcome == "refused":
        return claim.status, envelope(claim.code, claim.message)
    try:
        media_id = _upload(claim, sample)
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        return _upload_failed(ctx, claim.send_id, data.hub, failure)
    try:
        answer = meta.post(
            f"{claim.phone_number_id}/messages",
            token=claim.token.get_secret_value(),
            json=_meta_message(data, sample, media_id),
            timeout=meta.SEND_TIMEOUT,
        )
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        return _send_failed(ctx, claim.send_id, data.hub, failure)
    accepted = answer.get("messages")
    first = accepted[0] if isinstance(accepted, list) and accepted and isinstance(accepted[0], dict) else {}
    wa_message_id = str(first.get("id") or "")[:255]
    message_sends.message_record(ctx, SendRecordIn(send_id=claim.send_id, outcome="sent", wa_message_id=wa_message_id))
    return _sent(wa_message_id)


def _upload(claim: SendClaimOut, sample: templates.Sample | None) -> str:
    """The id of the header's file, uploaded to the business's number; ``""`` for a message without one."""
    if sample is None:
        return ""
    return meta.upload_media(
        claim.phone_number_id,
        claim.token.get_secret_value(),
        name=sample.name,
        mime_type=sample.mime_type,
        content=sample.content,
    )


def _upload_failed(ctx: OperationContext, send_id: UUID, hub: str, failure: Exception) -> tuple[int, dict]:
    """Uploading sends no message: whatever happened to it, the place and the key are free and nothing left."""
    _release(ctx, send_id, failure)
    if isinstance(failure, meta.MetaRefused):
        logger.warning("whatsapp.send.upload_refused hub=%s meta_code=%s", hub, failure.code)
        return _refusal(failure)
    logger.warning("whatsapp.send.upload_unreachable hub=%s", hub)
    return 503, envelope("whatsapp.meta_unreachable", "Meta did not take the header's file: nothing left. Retry later.")


def _send_failed(ctx: OperationContext, send_id: UUID, hub: str, failure: Exception) -> tuple[int, dict]:
    if isinstance(failure, meta.MetaUnreachable) and failure.sent:
        message_sends.message_record(ctx, SendRecordIn(send_id=send_id, outcome="unknown"))
        logger.warning("whatsapp.send.unknown hub=%s", hub)
        return 502, envelope(
            "whatsapp.meta_unknown", "Meta gave no answer: the message may have left. Retry with the same key."
        )
    _release(ctx, send_id, failure)
    if isinstance(failure, meta.MetaRefused):
        logger.warning("whatsapp.send.refused hub=%s meta_status=%s meta_code=%s", hub, failure.status, failure.code)
        return _refusal(failure)
    return 503, envelope("whatsapp.meta_unreachable", "Meta could not be reached: nothing left. Retry later.")


def _release(ctx: OperationContext, send_id: UUID, failure: Exception) -> None:
    """Nothing left: the place and the key are free. Meta's 190 marks the number «needs reconnecting»."""
    expired = isinstance(failure, meta.MetaRefused) and failure.code == EXPIRED_PERMISSION
    message_sends.message_record(ctx, SendRecordIn(send_id=send_id, outcome="released", needs_reconnect=expired))


def _sent(wa_message_id: str) -> tuple[int, dict]:
    if not wa_message_id:
        return 502, envelope(
            "whatsapp.meta_no_id", "Meta accepted the message without its id: it is not sent again with this key."
        )
    return 200, {"wa_message_id": wa_message_id}


def _meta_message(data: SendIn, sample: templates.Sample | None = None, media_id: str = "") -> dict:
    """Meta's message: a text, or a template with its header's file (uploaded first, by its id) and its values."""
    message = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": data.to.lstrip("+")}
    if data.type == "text":
        return {**message, "type": "text", "text": {"preview_url": False, "body": data.text}}
    template = {"name": data.template.name, "language": {"code": data.template.language}}
    components = []
    if sample is not None:
        kind = data.template.header_format.strip().lower()
        media = {"id": media_id, **({"filename": sample.name} if kind == "document" else {})}
        components.append({"type": "header", "parameters": [{"type": kind, kind: media}]})
    if data.template.variables:
        parameters = [{"type": "text", "text": value} for value in data.template.variables]
        components.append({"type": "body", "parameters": parameters})
    if components:
        template["components"] = components
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
    elif code == EXPIRED_PERMISSION:
        name = "whatsapp.reconnect_needed"
    elif code in NOT_CONNECTED:
        name = "whatsapp.not_connected"
    else:
        name = "whatsapp.meta_rejected"
    return 409, envelope(name, reason)
