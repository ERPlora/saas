"""Doors 10–12: ``config`` / ``connect`` / ``disconnect``. Connecting is all of Meta's steps
first (the code's exchange, the account's numbers, the app's subscription, the registration or, for a number of the
WhatsApp Business app, its history) and only then the number is kept: a step Meta refused saves nothing. The
history is the one step that does not undo it (the number works without it; the log says so).
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from whatsapp import meta, queries
from whatsapp.gateway.answers import envelope
from whatsapp.schemas import ConfigIn, ConnectIn, ConnectingIn, DisconnectIn, NumberConnectIn
from whatsapp.services import phone_numbers, platform_actor

logger = logging.getLogger("whatsapp.gateway")

#: Embedded Signup's event of a number of the WhatsApp Business app (coexistence): never registered again.
COEXISTENCE = "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"
#: What Meta is asked to bring of a coexistence number: its contacts and chats, then its history.
SYNC_KINDS = ("smb_app_state_sync", "history")


def configured() -> bool:
    try:
        meta.app_credentials()
    except meta.NotConfigured:
        return False
    return bool(str(getattr(settings, "WHATSAPP_CONFIG_ID", "") or "").strip()) and bool(meta.redirect_uri())


def config(data: ConfigIn) -> tuple[int, dict]:
    """What the Hub's screen opens Meta's window with: public ids only, never the app's secret."""
    queries.number_connecting(platform_actor.platform_context(), ConnectingIn(hub=data.hub))
    on = configured()
    return 200, {
        "configured": on,
        "app_id": str(settings.WHATSAPP_APP_ID).strip() if on else "",
        "config_id": str(settings.WHATSAPP_CONFIG_ID).strip() if on else "",
        "graph_version": settings.WHATSAPP_GRAPH_VERSION,
        # erplora.com's /whatsapp/return: Meta brings the window's code back there, and door 11 exchanges it with it.
        "redirect_uri": meta.redirect_uri() if on else "",
    }


class _NotTaken(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.answer = (status, envelope(code, message))


def connect(data: ConnectIn) -> tuple[int, dict]:
    ctx = platform_actor.platform_context()
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
    phone_numbers.number_connect(
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
    out = phone_numbers.number_disconnect(platform_actor.platform_context(), data)
    if out.disconnected and out.token is not None and not out.account_in_use:
        try:
            meta.delete(f"{out.waba_id}/subscribed_apps", token=out.token.get_secret_value())
        except (meta.MetaRefused, meta.MetaUnreachable) as failure:
            # Disconnected here already: what Meta still reports of that number is discarded.
            logger.warning("whatsapp.disconnect.unsubscribe_failed hub=%s error=%s", data.hub, type(failure).__name__)
    return 200, {"disconnected": out.disconnected}
