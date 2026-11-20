"""The business's templates at Meta.

- ``submit_template``: door 8. Meta's rules checked first (``templates.check``, a header's file
  included), then claim (the key) → the header's file to Meta (``meta.upload_sample``), when it has one → Meta →
  record. Meta saying it already has that name in that language (a first call whose answer was lost) adopts its id
  and edits it. Every «not taken» is a 409 whose key is free to try again, the upload's too (Meta's 190 is
  ``whatsapp.reconnect_needed`` and marks the number, as in door 5); a file header without Meta's app configured
  is 503 ``whatsapp.not_configured``, its key free again;
- ``delete_template``: door 9. Only that template in that language, by its id at Meta (the body's,
  the mirror's or Meta's own list's); Meta not having it is the 404 ``whatsapp.template_not_found`` the Hub reads as
  deleted;
- ``sync_templates``: Meta's list read again into the mirror, page by page (a verdict on a template the mirror lacks).
"""

import logging

from live.errors import OperationError

from whatsapp import meta, queries, services, templates
from whatsapp.gateway.answers import EXPIRED_PERMISSION, NOT_CONNECTED, envelope
from whatsapp.schemas import (
    ReconnectIn,
    TemplateAccountIn,
    TemplateClaimIn,
    TemplateDeleteIn,
    TemplateForgetIn,
    TemplateIn,
    TemplateRecordIn,
    TemplateSyncIn,
)

logger = logging.getLogger("whatsapp.gateway")

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
    released = TemplateRecordIn(submission_id=claim.submission_id, outcome="released")
    try:
        handle = _sample_handle(token, clean.sample, data.hub)
    except meta.NotConfigured:
        logger.error("whatsapp.template.not_configured hub=%s missing=WHATSAPP_APP_ID", data.hub)
        services.template_record(ctx, released)
        return 503, _NOT_CONFIGURED
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        services.template_record(ctx, released)
        return _template_failure(failure, claim.hub_id, data.hub, "upload")
    try:
        meta_id, answer = _register(claim.waba_id, token, clean, data.meta_id, handle)
    except (meta.MetaRefused, meta.MetaUnreachable) as failure:
        services.template_record(ctx, released)
        return _template_failure(failure, claim.hub_id, data.hub, "register")
    mirror = templates.mirror(
        clean, meta_id=meta_id, status=str(answer.get("status") or ""), category=str(answer.get("category") or "")
    )
    services.template_record(ctx, TemplateRecordIn(submission_id=claim.submission_id, outcome="done", mirror=mirror))
    return 200, {"meta_id": meta_id, "status": mirror["status"]}


_NOT_CONFIGURED = envelope("whatsapp.not_configured", "WhatsApp is not configured on erplora.com yet.")


def _sample_handle(token: str, sample: templates.Sample | None, hub: str) -> str:
    """The ``header_handle`` of a file header's sample, uploaded to Meta now (Meta asks for it on every edit too);
    ``""`` for a template without one."""
    if sample is None:
        return ""
    handle = meta.upload_sample(token, name=sample.name, mime_type=sample.mime_type, content=sample.content)
    logger.info("whatsapp.template.sample_uploaded hub=%s type=%s bytes=%s", hub, sample.mime_type, len(sample.content))
    return handle


def _register(
    waba_id: str, token: str, clean: templates.Clean, meta_id: str, header_handle: str = ""
) -> tuple[str, dict]:
    """Create the template at Meta, or edit the one it has (``meta_id``); its id and Meta's answer."""
    if meta_id:
        return meta_id, _edit(meta_id, token, clean, header_handle)
    named = {"parameter_format": "NAMED"} if clean.named else {}
    body = {"name": clean.name, "language": clean.language, "category": clean.category, **named}
    components = templates.components(clean, header_handle)
    try:
        answer = meta.post(f"{waba_id}/message_templates", token=token, json={**body, "components": components})
    except meta.MetaRefused as refused:
        found = _find(waba_id, token, clean.name, clean.language) if refused.subcode == TEMPLATE_EXISTS else ""
        if not found:
            raise
        return found, _edit(found, token, clean, header_handle)
    found = str(answer.get("id") or "")
    if not found:
        raise meta.MetaUnreachable("Meta took the template without its id.", sent=True)
    return found, answer


def _edit(meta_id: str, token: str, clean: templates.Clean, header_handle: str = "") -> dict:
    """An edit goes back through Meta's review: its answer (``{"success": true}``) carries no verdict, so it is
    pending until Meta says otherwise."""
    named = {"parameter_format": "NAMED"} if clean.named else {}
    body = {"category": clean.category, "components": templates.components(clean, header_handle), **named}
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
    if refused.code == EXPIRED_PERMISSION:
        services.number_reconnect_needed(services.platform_context(), ReconnectIn(hub_id=hub_id))
        return 409, envelope("whatsapp.reconnect_needed", reason)
    if refused.code in NOT_CONNECTED:
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
