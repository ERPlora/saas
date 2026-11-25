"""Reading Meta's webhook: what each change means for a business, before anything is stored.

Pure: no database, no network. A webhook may carry changes of several numbers and businesses; each is read by its
``field`` (https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components):

- ``messages``: what a customer wrote (``messages``, with the profile name in ``contacts``) and the
  delivery statuses of what the business sent (``statuses``);
- ``smb_message_echoes``: what the owner answered from the WhatsApp Business app (coexistence): the
  business speaking, filed under the customer (``to``);
- ``history``: the 180 days the owner agreed to share when connecting (``history[].threads``: inside a thread,
  what the customer did not write is the business's), and the follow-up with the recent media of the backlog
  (``messages`` with the id of an earlier ``media_placeholder``);
- ``message_template_status_update`` and ``template_category_update``: Meta's verdict on a template;
- anything else (``smb_app_state_sync``: the contacts of the business app, account and quality notices) is not
  kept.

A message becomes the body of the Hub's door 1 without ``hub`` and the attachment's address (which names the row
it is kept in); a status, door 2's. Nothing here logs: the caller counts what was skipped.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

#: The message types whose object carries an attachment Meta serves by its id.
MEDIA_TYPES = ("image", "video", "audio", "document", "sticker")
PLACEHOLDER = "media_placeholder"
STATUSES = ("sent", "delivered", "read", "failed")
#: Meta's template states the Hub shows as they are; the rest map to one of them, or to «gone» (``None``).
HUB_VERDICTS = ("APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED")
_VERDICT_ALIASES = {"FLAGGED": "APPROVED", "REINSTATED": "APPROVED", "IN_APPEAL": "REJECTED"}
_GONE = frozenset({"DELETED", "PENDING_DELETION", "ARCHIVED"})


@dataclass(frozen=True)
class Message:
    phone_number_id: str
    wa_message_id: str
    contact: str
    body: dict
    media_id: str = ""
    placeholder: bool = False
    follow_up: bool = False


@dataclass(frozen=True)
class Status:
    phone_number_id: str
    wa_message_id: str
    status: str
    error: dict | None
    status_at: str | None


@dataclass(frozen=True)
class Verdict:
    waba_id: str
    meta_id: str
    name: str
    language: str
    status: str
    reason: str = ""
    category: str = ""


@dataclass(frozen=True)
class _Filing:
    """The customer a message is filed under, and how it got here."""

    customer: str
    direction: str
    source: str
    contact_name: str = ""
    follow_up: bool = False


@dataclass
class Parsed:
    messages: list[Message] = field(default_factory=list)
    statuses: list[Status] = field(default_factory=list)
    verdicts: list[Verdict] = field(default_factory=list)
    history_declined: list[str] = field(default_factory=list)
    skipped: int = 0


def hub_verdict(meta_status: str) -> str | None:
    """Meta's state of a template as the Hub shows it; ``None`` when Meta no longer has it."""
    status = str(meta_status or "").upper()
    if status in _GONE:
        return None
    if status in HUB_VERDICTS:
        return status
    return _VERDICT_ALIASES.get(status, "PENDING")


def parse(payload) -> Parsed:
    parsed = Parsed()
    for entry in _list(_dict(payload).get("entry")):
        entry = _dict(entry)
        waba_id = str(entry.get("id") or "")
        for change in _list(entry.get("changes")):
            change = _dict(change)
            _change(parsed, waba_id, str(change.get("field") or ""), _dict(change.get("value")))
    return parsed


def _change(parsed: Parsed, waba_id: str, kind: str, value: dict) -> None:
    if kind in ("message_template_status_update", "template_category_update"):
        verdict = _verdict(waba_id, kind, value)
        if verdict is not None:
            parsed.verdicts.append(verdict)
        return
    metadata = _dict(value.get("metadata"))
    phone_number_id = _text(metadata, "phone_number_id")
    if not phone_number_id:
        return
    if kind == "messages":
        _customers(parsed, phone_number_id, value)
    elif kind == "smb_message_echoes":
        _echoes(parsed, phone_number_id, value)
    elif kind == "history":
        _history(parsed, phone_number_id, _digits(metadata.get("display_phone_number")), value)


def _customers(parsed: Parsed, phone_number_id: str, value: dict) -> None:
    names = {
        _text(contact, "wa_id"): _text(_dict(contact.get("profile")), "name")
        for contact in _dicts(value.get("contacts"))
    }
    for message in _dicts(value.get("messages")):
        sender = _text(message, "from")
        _keep(parsed, _message(phone_number_id, message, _Filing(sender, "inbound", "live", names.get(sender, ""))))
    for status in _dicts(value.get("statuses")):
        _keep_status(parsed, phone_number_id, status)


def _echoes(parsed: Parsed, phone_number_id: str, value: dict) -> None:
    for message in _dicts(value.get("message_echoes")):
        _keep(parsed, _message(phone_number_id, message, _Filing(_text(message, "to"), "outbound", "live")))


def _history(parsed: Parsed, phone_number_id: str, business: str, value: dict) -> None:
    for chunk in _dicts(value.get("history")):
        if chunk.get("errors"):
            parsed.history_declined.append(phone_number_id)
        for thread in _dicts(chunk.get("threads")):
            _thread(parsed, phone_number_id, thread)
    if value.get("errors"):
        parsed.history_declined.append(phone_number_id)
    _follow_up(parsed, phone_number_id, business, value)


def _thread(parsed: Parsed, phone_number_id: str, thread: dict) -> None:
    customer = _text(thread, "id")
    for message in _dicts(thread.get("messages")):
        direction = "inbound" if _text(message, "from") == customer else "outbound"
        _keep(parsed, _message(phone_number_id, message, _Filing(customer, direction, "history")))


def _follow_up(parsed: Parsed, phone_number_id: str, business: str, value: dict) -> None:
    """The backlog's recent media: top-level messages, with the same ids as their placeholders."""
    for message in _dicts(value.get("messages")):
        sender = _text(message, "from")
        if business and _digits(sender) == business:
            parsed.skipped += 1
        else:
            _keep(parsed, _message(phone_number_id, message, _Filing(sender, "inbound", "history", follow_up=True)))


def _keep(parsed: Parsed, message: Message | None) -> None:
    if message is None:
        parsed.skipped += 1
    else:
        parsed.messages.append(message)


def _message(phone_number_id: str, message: dict, filing: _Filing) -> Message | None:
    wa_message_id = _text(message, "id")
    if not wa_message_id or not filing.customer:
        return None
    kind = _text(message, "type") or "text"
    media_id, media = "", None
    text = ""
    reply = None
    reply_to = _text(_dict(message.get("context")), "id")
    content = _dict(message.get(kind))
    if kind == "text":
        text = _text(content, "body")
    elif kind in MEDIA_TYPES:
        media_id = _text(content, "id")
        text = _text(content, "caption")
        media = {"mime_type": _text(content, "mime_type"), "filename": _text(content, "filename"), "caption": text}
    elif kind == "button":
        reply = {"id": _text(content, "payload"), "title": _text(content, "text")}
        text = reply["title"]
    elif kind == "interactive":
        tapped = _dict(content.get(_text(content, "type")))
        reply = {"id": _text(tapped, "id"), "title": _text(tapped, "title")}
        text = reply["title"]
    elif kind == "reaction":
        text = _text(content, "emoji")
        reply_to = _text(content, "message_id") or reply_to
    body = {
        "wa_message_id": wa_message_id,
        "from": filing.customer,
        "contact_name": filing.contact_name,
        "direction": filing.direction,
        "source": filing.source,
        "type": kind,
        "text": text,
        "media": media,
        "reply_to": reply_to,
        "reply": reply,
        "sent_at": _when(message.get("timestamp")),
        "payload": message,
    }
    return Message(
        phone_number_id=phone_number_id,
        wa_message_id=wa_message_id,
        contact=filing.customer,
        body=body,
        media_id=media_id,
        placeholder=kind == PLACEHOLDER,
        follow_up=filing.follow_up,
    )


def _keep_status(parsed: Parsed, phone_number_id: str, status: dict) -> None:
    wa_message_id = str(status.get("id") or "")
    state = str(status.get("status") or "")
    if not wa_message_id or state not in STATUSES:
        parsed.skipped += 1
        return
    error = None
    if state == "failed":
        first = _dict((_list(status.get("errors")) or [{}])[0])
        reason = str(first.get("title") or first.get("message") or "")
        detail = str(_dict(first.get("error_data")).get("details") or "")
        error = {
            "code": str(first.get("code") or ""),
            "message": (f"{reason}: {detail}" if reason and detail else reason or detail)[:500],
        }
    parsed.statuses.append(
        Status(
            phone_number_id=phone_number_id,
            wa_message_id=wa_message_id,
            status=state,
            error=error,
            status_at=_when(status.get("timestamp")),
        )
    )


def _verdict(waba_id: str, kind: str, value: dict) -> Verdict | None:
    meta_id = str(value.get("message_template_id") or "")
    name = str(value.get("message_template_name") or "")
    if not waba_id or not (meta_id or name):
        return None
    reason = str(value.get("reason") or "")
    return Verdict(
        waba_id=waba_id,
        meta_id=meta_id,
        name=name,
        language=str(value.get("message_template_language") or ""),
        status=str(value.get("event") or "") if kind == "message_template_status_update" else "",
        reason="" if reason.upper() == "NONE" else reason[:500],
        category=str(value.get("new_category") or ""),
    )


def _when(timestamp) -> str | None:
    try:
        seconds = int(str(timestamp))
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _dicts(value) -> list[dict]:
    """The objects of a list of Meta's, with ``{}`` in the place of what is not one."""
    return [_dict(item) for item in _list(value)]


def _text(source: dict, key: str) -> str:
    return str(source.get(key) or "")
