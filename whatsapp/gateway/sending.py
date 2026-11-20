"""Door 5: send. Claim (the month's place, by the key) → Meta, outside any transaction → record how it ended. The
cap refuses before Meta (409 ``whatsapp.cap_reached``), the claim committed so the Hub gets the month's real usage
in its snapshot (once per figure, WHATSAPP-F05).
Meta's refusal frees the place and the key; no answer keeps both (``unknown``: the same key sends again only after
``services.IN_FLIGHT``); a 2xx without Meta's id is sent for good, never again. Meta's 190 (the
permission expired or withdrawn) is ``whatsapp.reconnect_needed`` and marks the number «needs reconnecting». A
template whose header is a photo, a video or a document carries its file (``templates.send_sample``: 409
``whatsapp.template_invalid`` before the claim when Meta would refuse it); after the claim it is uploaded to the
number (``meta.upload_media``) and the message names its id. The upload sends no message: its refusal or silence
frees the place and the key (the same 409 with a name, or 503 ``whatsapp.meta_unreachable``).
"""

import logging

from whatsapp import meta, services, templates
from whatsapp.gateway.answers import (
    EXPIRED_PERMISSION,
    NOT_CONNECTED,
    RECIPIENT_BLOCKED,
    WINDOW_CLOSED,
    envelope,
)
from whatsapp.schemas import SendClaimIn, SendIn, SendRecordIn

logger = logging.getLogger("whatsapp.gateway")


def send(data: SendIn, key: str) -> tuple[int, dict]:  # noqa: PLR0911
    ctx = services.platform_context()
    template = data.template
    try:
        sample = templates.send_sample(template) if template is not None else None
    except templates.Invalid as invalid:
        return 409, envelope("whatsapp.template_invalid", str(invalid))
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
    if claim.outcome == "refused":
        return claim.status, envelope(claim.code, claim.message)
    token = claim.token.get_secret_value()
    media_id = ""
    if sample is not None:
        # Uploading sends no message: whatever happens to it, the place and the key are free and nothing left.
        try:
            media_id = meta.upload_media(
                claim.phone_number_id, token, name=sample.name, mime_type=sample.mime_type, content=sample.content
            )
        except meta.MetaRefused as refused:
            services.message_record(
                ctx,
                SendRecordIn(send_id=claim.send_id, outcome="released", needs_reconnect=refused.code == EXPIRED_PERMISSION),
            )
            logger.warning("whatsapp.send.upload_refused hub=%s meta_code=%s", data.hub, refused.code)
            return _refusal(refused)
        except meta.MetaUnreachable:
            services.message_record(ctx, SendRecordIn(send_id=claim.send_id, outcome="released"))
            logger.warning("whatsapp.send.upload_unreachable hub=%s", data.hub)
            return 503, envelope(
                "whatsapp.meta_unreachable", "Meta did not take the header's file: nothing left. Retry later."
            )
    try:
        answer = meta.post(
            f"{claim.phone_number_id}/messages",
            token=token,
            json=_meta_message(data, sample, media_id),
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
