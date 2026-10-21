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
- ``erase``: door 6;
- ``submit_template``: door 8 (WHATSAPP-G15). Meta's rules checked first (``templates.check``), then claim (the key)
  → Meta → record. Meta saying it already has that name in that language (a first call whose answer was lost) adopts
  its id and edits it. Every «not taken» is a 409 whose key is free to try again;
- ``delete_template``: door 9 (WHATSAPP-G17). Only that template in that language, by its id at Meta (the body's,
  the mirror's or Meta's own list's); Meta not having it is the 404 ``whatsapp.template_not_found`` the Hub reads as
  deleted;
- ``sync_templates``: Meta's list read again into the mirror, page by page (a verdict on a template the mirror lacks);
- ``renew_tokens``: the daily renewal of Meta's permission (WHATSAPP-G12): exchange → record → the owner's mail;
- ``config`` / ``connect`` / ``disconnect``: doors 10–12 (WHATSAPP-G11, G01, G02). Connecting is all of Meta's steps
  first (the code's exchange, the account's numbers, the app's subscription, the registration or, for a number of the
  WhatsApp Business app, its history) and only then the number is kept: a step Meta refused saves nothing. The
  history is the one step that does not undo it (the number works without it; the log says so).

What a door answers is ``(status, body)``: the body of a 2xx, or the single error envelope.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from live.errors import OperationError

from whatsapp import emails, hub_client, meta, queries, services, templates
from whatsapp.schemas import (
    AlertedIn,
    ClaimIn,
    ConfigIn,
    ConnectIn,
    ConnectingIn,
    DisconnectIn,
    EraseIn,
    IngestIn,
    IngestOut,
    NumberConnectIn,
    ReconnectIn,
    RecordIn,
    RenewalDueIn,
    RenewalIn,
    SendClaimIn,
    SendIn,
    SendRecordIn,
    TemplateAccountIn,
    TemplateClaimIn,
    TemplateDeleteIn,
    TemplateForgetIn,
    TemplateIn,
    TemplateRecordIn,
    TemplateSyncIn,
)

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
    for hub_id in out.template_hubs:
        try:
            sync_templates(hub_id)
        except Exception:  # noqa: BLE001 - the verdicts are written: the next one reads the list again
            logger.exception("whatsapp.template.sync_crashed hub_id=%s", hub_id)
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


# --- Doors 8 and 9: templates -----------------------------------------------------------------------------------

#: Meta's subcode for «a template with this name already exists in this language».
TEMPLATE_EXISTS = 2388024
#: The fields of Meta's list the mirror keeps; a page and how many pages one read follows at most.
LIST_FIELDS = "id,name,language,category,status,rejected_reason,components"
PAGE_SIZE = 100
MAX_PAGES = 20


def submit_template(data: TemplateIn, key: str) -> tuple[int, dict]:
    try:
        clean = templates.check(data)
    except templates.Invalid as invalid:
        return 409, envelope("whatsapp.template_invalid", str(invalid))
    ctx = services.platform_context()
    claim = services.template_claim(ctx, TemplateClaimIn(hub=data.hub, key=key))
    if claim.outcome == "done":
        return 200, {"meta_id": claim.meta_id, "status": claim.status}
    token = claim.token.get_secret_value()
    try:
        meta_id, answer = _register(claim.waba_id, token, clean, data.meta_id)
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        services.template_record(ctx, TemplateRecordIn(submission_id=claim.submission_id, outcome="released"))
        return _template_failure(failure, claim.hub_id, data.hub, "register")
    mirror = templates.mirror(
        clean, meta_id=meta_id, status=str(answer.get("status") or ""), category=str(answer.get("category") or "")
    )
    services.template_record(ctx, TemplateRecordIn(submission_id=claim.submission_id, outcome="done", mirror=mirror))
    return 200, {"meta_id": meta_id, "status": mirror["status"]}


def _register(waba_id: str, token: str, clean: templates.Clean, meta_id: str) -> tuple[str, dict]:
    """Create the template at Meta, or edit the one it has (``meta_id``); its id and Meta's answer."""
    if meta_id:
        return meta_id, _edit(meta_id, token, clean)
    named = {"parameter_format": "NAMED"} if clean.named else {}
    body = {"name": clean.name, "language": clean.language, "category": clean.category, **named}
    try:
        answer = meta.post(
            f"{waba_id}/message_templates", token=token, json={**body, "components": templates.components(clean)}
        )
    except meta.MetaRefused as refused:
        found = _find(waba_id, token, clean.name, clean.language) if refused.subcode == TEMPLATE_EXISTS else ""
        if not found:
            raise
        return found, _edit(found, token, clean)
    found = str(answer.get("id") or "")
    if not found:
        raise meta.MetaUnreachable("Meta took the template without its id.", sent=True)
    return found, answer


def _edit(meta_id: str, token: str, clean: templates.Clean) -> dict:
    """An edit goes back through Meta's review: its answer (``{"success": true}``) carries no verdict, so it is
    pending until Meta says otherwise."""
    named = {"parameter_format": "NAMED"} if clean.named else {}
    body = {"category": clean.category, "components": templates.components(clean), **named}
    meta.post(meta_id, token=token, json=body)
    return {"status": "PENDING"}


def _find(waba_id: str, token: str, name: str, language: str) -> str:
    """The id at Meta of ``name`` in ``language`` (``""`` when Meta does not list it)."""
    answer = meta.get(f"{waba_id}/message_templates", token=token, params={"name": name, "fields": "id,name,language"})
    for item in answer.get("data") or []:
        if isinstance(item, dict) and item.get("name") == name and item.get("language") == language:
            return str(item.get("id") or "")
    return ""


def _template_failure(failure: Exception, hub_id, hub: str, what: str) -> tuple[int, dict]:
    """A template call Meta did not take, as the Hub reads it: always a 409 with Meta's reason (nothing changed)."""
    if isinstance(failure, meta.MetaUnreachable):
        logger.warning("whatsapp.template.unreachable hub=%s what=%s sent=%s", hub, what, failure.sent)
        return 409, envelope("whatsapp.meta_unreachable", "Meta could not be reached: nothing changed. Retry later.")
    refused = failure
    reason = refused.user_message or refused.title or refused.message or f"Meta refused it (HTTP {refused.status})."
    logger.warning(
        "whatsapp.template.refused hub=%s what=%s meta_status=%s meta_code=%s meta_subcode=%s",
        hub, what, refused.status, refused.code, refused.subcode,
    )
    if refused.rate_limited:
        return 409, envelope("whatsapp.meta_rate_limited", reason)
    if refused.code in NOT_CONNECTED:
        if refused.code == EXPIRED_PERMISSION:
            services.number_reconnect_needed(services.platform_context(), ReconnectIn(hub_id=hub_id))
        return 409, envelope("whatsapp.not_connected", reason)
    if what == "delete":
        return 409, envelope("whatsapp.meta_rejected", reason)
    return 409, envelope("whatsapp.template_invalid", reason)


def delete_template(data: TemplateDeleteIn) -> tuple[int, dict]:
    ctx = services.platform_context()
    account = queries.template_account(ctx, TemplateAccountIn(hub=data.hub, name=data.name, language=data.language))
    token = account.token.get_secret_value()
    gone = (404, envelope("whatsapp.template_not_found", "Meta does not have this template."))
    forget = TemplateForgetIn(hub_id=account.hub_id, name=data.name, language=data.language)
    try:
        meta_id = data.meta_id or account.meta_id or _find(account.waba_id, token, data.name, data.language)
        if not meta_id:
            services.template_forget(ctx, forget)
            return gone
        try:
            meta.delete(
                f"{account.waba_id}/message_templates", token=token, params={"hsm_id": meta_id, "name": data.name}
            )
        except meta.MetaRefused as refused:
            if refused.rate_limited or refused.code in NOT_CONNECTED:
                raise
            if _find(account.waba_id, token, data.name, data.language):
                raise
            services.template_forget(ctx, forget)
            return gone
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        return _template_failure(failure, account.hub_id, data.hub, "delete")
    services.template_forget(ctx, forget)
    return 200, {"deleted": True}


def sync_templates(hub_id) -> bool:
    """Read the business's templates from Meta into the mirror; whether the list came whole. Meta unreachable or
    refusing leaves the mirror as it was (and says so in the log)."""
    ctx = services.platform_context()
    try:
        account = queries.template_account(ctx, TemplateAccountIn(hub_id=hub_id))
    except OperationError:
        return False
    token = account.token.get_secret_value()
    items: list[dict] = []
    params = {"fields": LIST_FIELDS, "limit": PAGE_SIZE}
    complete = False
    try:
        for _ in range(MAX_PAGES):
            answer = meta.get(f"{account.waba_id}/message_templates", token=token, params=params)
            read = (templates.from_meta(item) for item in answer.get("data") or [] if isinstance(item, dict))
            items.extend(mirror for mirror in read if mirror is not None)
            paging = answer.get("paging") if isinstance(answer.get("paging"), dict) else {}
            after = (paging.get("cursors") or {}).get("after") if isinstance(paging.get("cursors"), dict) else None
            if not paging.get("next") or not after:
                complete = True
                break
            params = {**params, "after": after}
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        logger.warning("whatsapp.template.sync_failed hub_id=%s reason=%s", hub_id, type(failure).__name__)
        if isinstance(failure, meta.MetaRefused) and failure.code == EXPIRED_PERMISSION:
            services.number_reconnect_needed(ctx, ReconnectIn(hub_id=hub_id))
    if items or complete:
        services.template_sync(ctx, TemplateSyncIn(hub_id=hub_id, items=items, complete=complete))
    return complete


# --- The renewal of Meta's permission (WHATSAPP-G12) -------------------------------------------------------------

#: A number with less than this left and still not renewed after the round is an error in the log.
ALARM = timedelta(days=7)


def renew_tokens() -> dict[str, int]:
    """Renew every permission due; ``NotConfigured`` (Meta's app not set) before anything is read."""
    meta.app_credentials()
    ctx = services.platform_context()
    counts = {"renewed": 0, "needs_reconnect": 0, "unverified": 0, "alerted": 0, "failed": 0}
    running_out = 0
    for number in queries.renewal_due(ctx, RenewalDueIn()).numbers:
        try:
            outcome, token, expires_at = _renew(number.token.get_secret_value())
            out = services.number_renewal(
                ctx, RenewalIn(number_id=number.id, outcome=outcome, token=token, expires_at=expires_at)
            )
        except Exception:  # noqa: BLE001 - one number's surprise never stops the others; tomorrow tries again
            logger.exception("whatsapp.token.renewal_crashed number_id=%s", number.id)
            counts["failed"] += 1
            outcome, out = "failed", None
        else:
            counts["needs_reconnect" if out.needs_reconnect else outcome] += 1
            if out.alert is not None and emails.send_reconnect(**out.alert.model_dump()):
                services.number_alerted(ctx, AlertedIn(number_id=number.id))
                counts["alerted"] += 1
        if outcome != "renewed" and number.expires_at <= timezone.now() + ALARM:
            running_out += 1
    if running_out:
        logger.error("whatsapp.token.running_out numbers=%s days_left_under=%s", running_out, ALARM.days)
    return counts


def _renew(token: str) -> tuple[str, str | None, object]:
    """Meta's exchange of ``token``: ``("renewed", fresh, deadline)``, ``("refused", …)`` when Meta said no, or
    ``("unverified", …)`` without a verdict (not reached, throttled, an answer without a token)."""
    try:
        answer = meta.exchange_token(token)
    except meta.MetaRefused as refused:
        logger.warning("whatsapp.token.refused meta_status=%s meta_code=%s", refused.status, refused.code)
        return ("unverified" if refused.rate_limited else "refused"), None, None
    except meta.MetaUnreachable:
        return "unverified", None, None
    fresh = str(answer.get("access_token") or "")
    if not fresh:
        logger.warning("whatsapp.token.no_token_in_answer")
        return "unverified", None, None
    try:
        expires_at = meta.token_expiry(fresh)
    except (meta.MetaRefused, meta.MetaUnreachable):
        seconds = answer.get("expires_in")
        expires_at = timezone.now() + timedelta(seconds=int(seconds)) if isinstance(seconds, int) and seconds > 0 else None
    return "renewed", fresh, expires_at


# --- Doors 10–12: connecting a number (WHATSAPP-G11, WHATSAPP-G01, WHATSAPP-G02) --------------------------------

#: Embedded Signup's event of a number of the WhatsApp Business app (coexistence): never registered again.
COEXISTENCE = "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"
#: What Meta is asked to bring of a coexistence number: its contacts and chats, then its history.
SYNC_KINDS = ("smb_app_state_sync", "history")


def configured() -> bool:
    try:
        meta.app_credentials()
    except meta.NotConfigured:
        return False
    return bool(str(getattr(settings, "WHATSAPP_CONFIG_ID", "") or "").strip())


def config(data: ConfigIn) -> tuple[int, dict]:
    """What the Hub's screen opens Meta's window with: public ids only, never the app's secret."""
    queries.number_connecting(services.platform_context(), ConnectingIn(hub=data.hub))
    on = configured()
    return 200, {
        "configured": on,
        "app_id": str(settings.WHATSAPP_APP_ID).strip() if on else "",
        "config_id": str(settings.WHATSAPP_CONFIG_ID).strip() if on else "",
        "graph_version": settings.WHATSAPP_GRAPH_VERSION,
    }


class _NotTaken(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.answer = (status, envelope(code, message))


def connect(data: ConnectIn) -> tuple[int, dict]:
    ctx = services.platform_context()
    hub_id = queries.number_connecting(ctx, ConnectingIn(hub=data.hub)).hub_id
    if not configured():
        logger.error("whatsapp.connect.not_configured hub=%s", data.hub)
        return 503, envelope("whatsapp.not_configured", "WhatsApp is not configured on erplora.com yet.")
    coexistence = data.event == COEXISTENCE
    try:
        token, expires_at = _business_token(data.code)
        chosen = _chosen_number(data.waba_id, token, data.phone_number_id)
        meta.post(f"{data.waba_id}/subscribed_apps", token=token)
        pin = queries.number_connecting(ctx, ConnectingIn(hub=data.hub, phone_number_id=chosen["id"])).pin
        pin = pin.get_secret_value()
        if not coexistence:
            pin = pin or f"{secrets.randbelow(10**6):06d}"
            meta.post(f"{chosen['id']}/register", token=token, json={"messaging_product": "whatsapp", "pin": pin})
    except _NotTaken as not_taken:
        return not_taken.answer
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        return _connect_failure(failure, data.hub)
    history = _ask_history(chosen["id"], token) if coexistence else False
    services.number_connect(
        ctx,
        NumberConnectIn(
            hub_id=hub_id,
            phone_number_id=chosen["id"],
            display_phone=str(chosen.get("display_phone_number") or ""),
            display_name=str(chosen.get("verified_name") or ""),
            waba_id=data.waba_id,
            business_id=data.business_id,
            token=token,
            expires_at=expires_at,
            pin=pin,
            is_on_biz_app=coexistence,
        ),
    )
    display = str(chosen.get("display_phone_number") or "")
    return 200, {
        "connected": True,
        "phone_number": queries.e164(display),
        "display_name": str(chosen.get("verified_name") or "")[:200],
        "history_requested": history,
    }


def _business_token(code: str):
    answer = meta.exchange_code(code)
    token = str(answer.get("access_token") or "")
    if not token:
        logger.warning("whatsapp.connect.no_token_in_answer")
        raise _NotTaken(502, "whatsapp.meta_no_token", "Meta answered without the business's permission. Try again.")
    try:
        expires_at = meta.token_expiry(token)
    except (meta.MetaRefused, meta.MetaUnreachable):
        seconds = answer.get("expires_in")
        expires_at = timezone.now() + timedelta(seconds=seconds) if isinstance(seconds, int) and seconds > 0 else None
    return token, expires_at


def _chosen_number(waba_id: str, token: str, phone_number_id: str) -> dict:
    """The account's number the window chose; without one named, the account's only number. Never another."""
    answer = meta.get(f"{waba_id}/phone_numbers", token=token, params={"fields": "id,display_phone_number,verified_name"})
    numbers = [item for item in answer.get("data") or [] if isinstance(item, dict) and item.get("id")]
    if phone_number_id:
        for item in numbers:
            if str(item["id"]) == phone_number_id:
                return {**item, "id": str(item["id"])}
        raise _NotTaken(
            409, "whatsapp.number_not_in_account", "The number chosen in Meta's window is not in that account."
        )
    if len(numbers) == 1:
        return {**numbers[0], "id": str(numbers[0]["id"])}
    if not numbers:
        raise _NotTaken(409, "whatsapp.number_not_in_account", "That WhatsApp Business account has no number.")
    raise _NotTaken(
        409, "whatsapp.number_not_chosen", "That account has several numbers: choose one in Meta's window."
    )


def _ask_history(phone_number_id: str, token: str) -> bool:
    """Ask Meta for the contacts, the chats and the history of a coexistence number (they reach the Hub through the
    webhook). Meta allows it only right after connecting: a refusal is logged, never undoes the connection."""
    try:
        for kind in SYNC_KINDS:
            meta.post(f"{phone_number_id}/smb_app_data", token=token, json={"messaging_product": "whatsapp", "sync_type": kind})
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        logger.error("whatsapp.connect.history_not_requested phone_number_id=%s error=%s", phone_number_id, type(failure).__name__)
        return False
    return True


def _connect_failure(failure: Exception, hub: str) -> tuple[int, dict]:
    if isinstance(failure, meta.MetaUnreachable):
        logger.warning("whatsapp.connect.unreachable hub=%s sent=%s", hub, failure.sent)
        return 503, envelope("whatsapp.meta_unreachable", "Meta could not be reached: nothing was saved. Try again.")
    refused = failure
    logger.warning(
        "whatsapp.connect.refused hub=%s meta_status=%s meta_code=%s meta_subcode=%s",
        hub, refused.status, refused.code, refused.subcode,
    )
    reason = refused.user_message or refused.title or refused.message or f"Meta refused it (HTTP {refused.status})."
    if refused.rate_limited:
        return 429, envelope("whatsapp.meta_rate_limited", reason)
    return 409, envelope("whatsapp.meta_rejected", reason)


def disconnect(data: DisconnectIn) -> tuple[int, dict]:
    out = services.number_disconnect(services.platform_context(), data)
    if out.disconnected and out.token is not None and not out.account_in_use:
        try:
            meta.delete(f"{out.waba_id}/subscribed_apps", token=out.token.get_secret_value())
        except (meta.MetaRefused, meta.MetaUnreachable) as failure:
            # Disconnected here already: what Meta still reports of that number is discarded.
            logger.warning("whatsapp.disconnect.unsubscribe_failed hub=%s error=%s", data.hub, type(failure).__name__)
    return 200, {"disconnected": out.disconnected}
