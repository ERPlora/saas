"""The writes of the AI gateway, each an operation (``@operation``, ``kind="command"``) in its own transaction, with
its event in the outbox.

The admin calls them as the member of the staff who clicks (``assistant.admin.staff_context``): each one checks
the model permission of Django that backs it, so a member of the staff without it is refused here too, not only
on the page. The commands call them as the platform (``platform_context``).

- ``assistant.credential.save`` / ``.delete`` (ASSISTANT-G26, G16): a provider's key, kept encrypted with its hint;
  typing another one is a rotation. A change that types no key never writes the stored token again (an unreadable
  one stays as it was, waiting for its key to come back or to be typed again).
- ``assistant.model.select`` (G24, G14): the provider keeps exactly the models ticked among those its API listed,
  except the ones the policy uses.
- ``assistant.policy.update`` (G27, G17, G10, G60): the model that answers and the fallback one, each available and
  of an enabled provider, and different.
- ``assistant.credential.import`` (G02, G21): the platform keeps a provider's key from the environment
  (``import_ai_keys_from_env``), adding the provider of its API if missing; a key already kept stays unless forced.
- ``assistant.encryption.rotate`` (G03, G41): every value kept with ``FERNET_KEY`` (the providers' keys and
  WhatsApp's tokens and PINs, ``encrypted_columns``) written again with the current key, so the previous one can go.
- ``assistant.model.try`` (G61): a member of the staff tried a model from the admin; it stays in the audit trail (an
  access to the model) with how long the message was and how many tools it offered, never the message.
- ``assistant.message.claim`` / ``.release`` (G51): a message of the plan's monthly allowance (a demo's own few),
  taken before the model is called and given back if the turn failed before answering.
- ``assistant.usage.record`` (G29, G52): what a turn, an embedding or the voice spent (tokens, dictations, characters
  read aloud) and its cost in USD.
- ``assistant.report.send`` (G58): the report of an answer, mailed to the support mailbox; nothing kept.
"""

import logging
from datetime import timedelta

from auditlog.models import LogEntry
from django.apps import apps
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db.models import F, TextField, Value
from django.db.models.functions import Cast
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

import whatsapp.fields
from assistant import crypto, events, fields, queries
from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy, AssistantUsage
from assistant.queries import choosable_models, staff_with
from hubs.models import Hub
from assistant.schemas import (
    Caller,
    ClaimOut,
    MessageReleaseIn,
    ReportOut,
    ReportSendIn,
    UsageOut,
    UsageRecordIn,
    CredentialDeleteIn,
    CredentialDeleteOut,
    CredentialImportIn,
    CredentialImportOut,
    CredentialIn,
    CredentialOut,
    EncryptionRotateIn,
    EncryptionRotateOut,
    ModelSelectIn,
    ModelSelectOut,
    ModelTryIn,
    ModelTryOut,
    PolicyIn,
    PolicyOut,
)

logger = logging.getLogger(__name__)


def platform_context() -> OperationContext:
    """The platform acting on the gateway (its commands, the Hub's doors)."""
    return system_context(Scope("platform", "assistant"))


def _encryption_missing(ctx: OperationContext) -> OperationError:
    with translation.override(ctx.language):
        return OperationError(
            _("The key of the credentials is not configured: no provider key can be kept."),
            code="assistant.encryption_not_configured",
            status=503,
        )


def _credential_out(credential: AIProviderCredential) -> dict:
    return {
        "id": credential.pk,
        "provider": credential.provider_id,
        "label": credential.label,
        "is_active": credential.is_active,
        "masked_key": credential.masked_key,
        "rotated_at": credential.rotated_at,
    }


@operation(
    "assistant.credential.save",
    kind="command",
    permission="assistant.manage",
    input=CredentialIn,
    output=CredentialOut,
    ai=INTERNAL,  # staff
)
def credential_save(ctx: OperationContext, data: CredentialIn) -> dict:
    """Add a provider's key (``add_aiprovidercredential``) or change one (``change_aiprovidercredential``): its
    label, whether it is active and, if a key is typed, the key itself (a rotation). 422 ``assistant.key_required``
    for a new one without key, 409 ``assistant.label_taken``, 503 ``assistant.encryption_not_configured``."""
    user = staff_with(
        ctx,
        "assistant.change_aiprovidercredential" if data.id else "assistant.add_aiprovidercredential",
    )
    with translation.override(ctx.language):
        provider = AIProvider.objects.filter(pk=data.provider).first()
        if provider is None:
            raise NotFound(_("This provider does not exist."), code="assistant.provider_unknown")
        if data.id is None and data.api_key is None:
            raise OperationError(
                _("Type the provider's key."),
                code="assistant.key_required",
                status=422,
                fields={"api_key": _("Type the provider's key.")},
            )
        taken = AIProviderCredential.objects.filter(provider=provider, label=data.label)
        if data.id is not None:
            taken = taken.exclude(pk=data.id)
        if taken.exists():
            raise Conflict(
                _("This provider already has a key with that label."),
                code="assistant.label_taken",
                fields={"label": _("This provider already has a key with that label.")},
            )
        if data.api_key is not None and not crypto.configured():
            raise _encryption_missing(ctx)

        if data.id is None:
            credential = AIProviderCredential(provider=provider, created_by=user)
        else:
            credential = AIProviderCredential.objects.select_for_update().filter(pk=data.id, provider=provider).first()
            if credential is None:
                raise NotFound(_("This key does not exist."), code="assistant.credential_unknown")

    credential.label = data.label
    credential.is_active = data.is_active
    credential.updated_by = user
    rotated = False
    if data.api_key is not None:
        plaintext = data.api_key.get_secret_value()
        rotated = credential.pk is not None and not credential._state.adding
        credential.api_key = plaintext
        credential.key_hint = plaintext[-4:]
        if rotated:
            credential.rotated_at = timezone.now()
    if credential._state.adding:
        credential.save()
    else:
        fields = ["label", "is_active", "updated_by", "updated_at"]
        if data.api_key is not None:
            fields += ["api_key", "key_hint", "rotated_at"]
        credential.save(update_fields=fields)
    record_event(
        ctx,
        events.CREDENTIAL_SAVED,
        {"provider": str(provider.pk), "credential": str(credential.pk), "rotated": rotated},
    )
    return _credential_out(credential)


@operation(
    "assistant.credential.delete",
    kind="command",
    permission="assistant.manage",
    input=CredentialDeleteIn,
    output=CredentialDeleteOut,
    ai=INTERNAL,  # staff
)
def credential_delete(ctx: OperationContext, data: CredentialDeleteIn) -> dict:
    """Forget a provider's key (``delete_aiprovidercredential``): its models answer with another active key of the
    provider, or not at all. 404 ``assistant.credential_unknown``."""
    staff_with(ctx, "assistant.delete_aiprovidercredential")
    credential = AIProviderCredential.objects.filter(pk=data.id).first()
    if credential is None:
        with translation.override(ctx.language):
            raise NotFound(_("This key does not exist."), code="assistant.credential_unknown")
    provider_id = credential.provider_id
    credential.delete()
    record_event(ctx, events.CREDENTIAL_DELETED, {"provider": str(provider_id), "credential": str(data.id)})
    return {"deleted": True}


def policy_model_ids() -> set:
    """The models the policy uses: never deleted by a choice."""
    policy = AIRoutingPolicy.objects.filter(slot=AIRoutingPolicy.SLOT).first()
    if policy is None:
        return set()
    return {pk for pk in (policy.active_model_id, policy.fallback_model_id) if pk}


@operation(
    "assistant.model.select",
    kind="command",
    permission="assistant.manage",
    input=ModelSelectIn,
    output=ModelSelectOut,
    ai=INTERNAL,  # staff
)
def model_select(ctx: OperationContext, data: ModelSelectIn) -> dict:
    """Keep exactly the ticked models of a provider (``add_aimodel`` and ``delete_aimodel``): the ticked ones among
    those its API listed are created available (or made available again, their name kept); every other model of the
    provider is deleted, except the ones the policy uses. 404 ``assistant.provider_unknown``."""
    staff_with(ctx, "assistant.add_aimodel", "assistant.delete_aimodel")
    with translation.override(ctx.language):
        provider = AIProvider.objects.filter(pk=data.provider).first()
        if provider is None:
            raise NotFound(_("This provider does not exist."), code="assistant.provider_unknown")
    listed = {item.model_id: item for item in data.listed}
    ticked = [model_id for model_id in dict.fromkeys(data.selected) if model_id in listed]
    counts = {"created": 0, "kept": 0, "deleted": 0, "protected": 0}
    for model_id in ticked:
        item = listed[model_id]
        model = AIModel.objects.filter(provider=provider, model_id=model_id).first()
        if model is None:
            AIModel.objects.create(
                provider=provider,
                model_id=model_id,
                display_name=item.display_name or model_id,
                context_window=item.context_window,
                is_available=True,
            )
            counts["created"] += 1
            continue
        model.is_available = True
        if not model.context_window and item.context_window:
            model.context_window = item.context_window
        model.save(update_fields=["is_available", "context_window", "updated_at"])
        counts["kept"] += 1
    in_use = policy_model_ids()
    for model in AIModel.objects.filter(provider=provider).exclude(model_id__in=ticked):
        if model.pk in in_use:
            counts["protected"] += 1
            continue
        model.delete()
        counts["deleted"] += 1
    record_event(ctx, events.MODEL_SELECTED, {"provider": str(provider.pk), **counts})
    return counts


@operation(
    "assistant.policy.update",
    kind="command",
    permission="assistant.manage",
    input=PolicyIn,
    output=PolicyOut,
    ai=INTERNAL,  # staff
)
def policy_update(ctx: OperationContext, data: PolicyIn) -> dict:
    """Choose the model that answers and the fallback one (``change_airoutingpolicy``). 422
    ``assistant.model_unavailable`` (a model that is off, of a provider that is off, or unknown),
    ``assistant.fallback_is_active`` and ``assistant.fallback_without_model``."""
    user = staff_with(ctx, "assistant.change_airoutingpolicy")
    with translation.override(ctx.language):
        usable = {model.pk for model in choosable_models()}
        for field, chosen in (("active_model", data.active_model), ("fallback_model", data.fallback_model)):
            if chosen is not None and chosen not in usable:
                message = _("This model cannot answer: it is off, its provider is off or it does not exist.")
                raise OperationError(message, code="assistant.model_unavailable", status=422, fields={field: message})
        if data.fallback_model is not None and data.active_model is None:
            message = _("Choose the model that answers before its fallback.")
            raise OperationError(
                message, code="assistant.fallback_without_model", status=422, fields={"fallback_model": message}
            )
        if data.fallback_model is not None and data.fallback_model == data.active_model:
            message = _("The fallback model must be another model.")
            raise OperationError(
                message, code="assistant.fallback_is_active", status=422, fields={"fallback_model": message}
            )
    policy = AIRoutingPolicy.objects.select_for_update().filter(slot=AIRoutingPolicy.SLOT).first() or AIRoutingPolicy.solo()
    policy.active_model_id = data.active_model
    policy.fallback_model_id = data.fallback_model
    policy.updated_by = user
    policy.save()
    record_event(
        ctx,
        events.POLICY_UPDATED,
        {
            "active_model": str(data.active_model) if data.active_model else None,
            "fallback_model": str(data.fallback_model) if data.fallback_model else None,
        },
    )
    return {"active_model": policy.active_model_id, "fallback_model": policy.fallback_model_id, "updated_at": policy.updated_at}


@operation(
    "assistant.model.try",
    kind="command",
    permission="assistant.manage",
    input=ModelTryIn,
    output=ModelTryOut,
    ai=INTERNAL,  # staff
)
def model_try(ctx: OperationContext, data: ModelTryIn) -> dict:
    """Record that the member of the staff tried a model (``change_airoutingpolicy``, the permission that chooses
    which model answers): an access in the audit trail and ``assistant.model.tried``, with the message's length and
    the number of tools, never the message. 404 ``assistant.model_unknown``."""
    user = staff_with(ctx, "assistant.change_airoutingpolicy")
    with translation.override(ctx.language):
        model = AIModel.objects.filter(pk=data.model).first()
        if model is None:
            raise NotFound(_("This model does not exist."), code="assistant.model_unknown")
    tried = {"prompt_chars": data.prompt_chars, "tools": data.tools}
    LogEntry.objects.log_create(
        model,
        force_log=True,
        action=LogEntry.Action.ACCESS,
        actor=user,
        remote_addr=getattr(ctx.request, "META", {}).get("REMOTE_ADDR"),
        additional_data={"tried": True, **tried},
    )
    record_event(ctx, events.MODEL_TRIED, {"model": str(model.pk), **tried})
    return {"recorded": True}


@operation(
    "assistant.credential.import",
    kind="command",
    permission="assistant.manage",
    input=CredentialImportIn,
    output=CredentialImportOut,
    ai=INTERNAL,  # staff
)
def credential_import(ctx: OperationContext, data: CredentialImportIn) -> dict:
    """Keep a provider's key as the platform (``import_ai_keys_from_env``): the provider whose identifier is its API,
    added if missing; the key with ``label`` is created, or replaced and turned on with ``force``, or kept as it is.
    ``dry_run`` says the same and writes nothing. 403 to anyone but the platform (the staff use the admin), 503
    ``assistant.encryption_not_configured``."""
    if ctx.actor != "system":
        with translation.override(ctx.language):
            raise PermissionDenied(_("Only the platform loads the keys of the environment."), code="assistant.platform_only")
    plaintext = data.api_key.get_secret_value().strip()
    provider = AIProvider.objects.filter(slug=data.kind).first()
    credential = (
        AIProviderCredential.objects.select_for_update().filter(provider=provider, label=data.label).first()
        if provider is not None
        else None
    )
    if credential is not None and not data.force:
        return {"provider": data.kind, "action": "kept", "label": data.label, "masked_key": credential.masked_key}
    action = "created" if credential is None else "rotated"
    result = {"provider": data.kind, "action": action, "label": data.label, "masked_key": f"…{plaintext[-4:]}"}
    if data.dry_run:
        return result
    if not crypto.configured():
        raise _encryption_missing(ctx)
    if provider is None:
        provider = AIProvider.objects.create(slug=data.kind, name=AIProvider.Kind(data.kind).label, kind=data.kind)
    if credential is None:
        credential = AIProviderCredential(provider=provider, label=data.label)
    else:
        credential.rotated_at = timezone.now()
    credential.api_key = plaintext
    credential.key_hint = plaintext[-4:]
    credential.is_active = True
    credential.save()
    record_event(
        ctx,
        events.CREDENTIAL_SAVED,
        {"provider": str(provider.pk), "credential": str(credential.pk), "rotated": action == "rotated"},
    )
    return result


#: The field classes whose columns keep their value with ``FERNET_KEY`` (MultiFernet with ``FERNET_KEY_PREVIOUS``),
#: all rotated together. A new encrypted field class goes here, or the guard of the tests fails (#1016). The fiscal
#: documents are kept with their own key (``FISCAL_DOCUMENTS_KEY``, ``fiscal.crypto``) and are not rotated here.
ROTATED_FIELD_CLASSES = (fields.EncryptedTextField, whatsapp.fields.EncryptedTextField)


def encrypted_columns() -> list[tuple[type, str]]:
    """Every ``(model, field name)`` kept with ``FERNET_KEY``, derived from the models (never a hand-written list)."""
    found = [
        (model, field.name)
        for model in apps.get_models()
        for field in model._meta.concrete_fields
        if type(field) in ROTATED_FIELD_CLASSES
    ]
    return sorted(found, key=lambda column: (column[0]._meta.label, column[1]))


@operation(
    "assistant.encryption.rotate",
    kind="command",
    permission="assistant.manage",
    input=EncryptionRotateIn,
    output=EncryptionRotateOut,
    ai=INTERNAL,  # staff
)
def encryption_rotate(ctx: OperationContext, data: EncryptionRotateIn) -> dict:
    """Write every value kept with ``FERNET_KEY`` again with the current key (``rotate_encryption_keys``, the
    platform only). Each token is rotated as it is, without the value leaving ``assistant.crypto`` nor the row being
    saved (no date of the row moves); one already of the current key is left alone, and one no live key opens is
    never written and is reported. ``dry_run`` counts and writes nothing. 503 ``assistant.encryption_not_configured``."""
    if ctx.actor != "system":
        with translation.override(ctx.language):
            raise PermissionDenied(_("Only the platform rotates the key of the credentials."), code="assistant.platform_only")
    if not crypto.configured():
        raise _encryption_missing(ctx)
    columns = []
    for model, name in encrypted_columns():
        rotated, current, unreadable = 0, 0, []
        rows = model._default_manager.annotate(token=Cast(name, TextField())).exclude(token="").values_list("pk", "token")
        for pk, token in rows.order_by("pk"):
            if crypto.is_current(token):
                current += 1
                continue
            try:
                fresh = crypto.rotate(token)
            except crypto.Undecryptable:
                unreadable.append(str(pk))
                continue
            rotated += 1
            if not data.dry_run:
                model._default_manager.filter(pk=pk).update(**{name: Value(fresh, output_field=TextField())})
        columns.append(
            {"column": f"{model._meta.label}.{name}", "rotated": rotated, "current": current, "unreadable": unreadable}
        )
    totals = {
        "rotated": sum(column["rotated"] for column in columns),
        "current": sum(column["current"] for column in columns),
        "unreadable": sum(len(column["unreadable"]) for column in columns),
    }
    if not data.dry_run:
        record_event(ctx, events.ENCRYPTION_ROTATED, totals)
    return {"columns": columns, **totals}


# --- The Hub's turn (part 2): the plan's messages and what each turn spent (ASSISTANT-G51, G29) -------------------

#: How long the row of a demo is kept after it started: a demo lives an hour, and its row is forgotten when a later
#: demo starts (no task needed).
DEMO_USAGE_KEPT = timedelta(days=1)


def _caller_payload(caller: Caller) -> dict:
    payload = {"hub": str(caller.hub_id) if caller.hub_id else None, "demo": caller.demo}
    if caller.user_id is not None:
        payload["user"] = str(caller.user_id)
    return payload


def _rows_of(caller: Caller, month):
    """The caller's rows that count ``month``: a business's or an account's of that month, a demo's only one."""
    if caller.demo:
        return AssistantUsage.objects.filter(demo=caller.demo)
    if caller.user_id is not None:
        return AssistantUsage.objects.filter(user_id=caller.user_id, month=month)
    return AssistantUsage.objects.filter(hub_id=caller.hub_id, month=month)


def _row_of(caller: Caller, now) -> AssistantUsage:
    """The caller's row of usage now (made the first time): a business's or an account's of this month, a demo's only
    one. A demo's first row forgets the rows of the demos that started more than a day ago."""
    if caller.demo:
        row, created = AssistantUsage.objects.get_or_create(demo=caller.demo, defaults={"month": queries.month_of(now)})
        if created:
            AssistantUsage.objects.exclude(demo="").filter(created_at__lt=now - DEMO_USAGE_KEPT).delete()
        return row
    if caller.user_id is not None:
        return AssistantUsage.objects.get_or_create(user_id=caller.user_id, month=queries.month_of(now))[0]
    return AssistantUsage.objects.get_or_create(hub_id=caller.hub_id, month=queries.month_of(now))[0]


@operation(
    "assistant.message.claim",
    kind="command",
    permission="assistant.manage",
    input=Caller,
    output=ClaimOut,
    ai=INTERNAL,  # platform
)
def message_claim(ctx: OperationContext, data: Caller) -> dict:
    """Take a message of the caller's allowance for a turn, before the model is called (the platform only): one
    ``UPDATE … WHERE messages < limit``, which a concurrent claim waits on and then evaluates again, so two turns
    never pass the last message together. Without one left nothing is taken and ``claimed`` is false."""
    queries.platform_only(ctx)
    now = timezone.now()
    limit = queries.monthly_limit(data, now)
    row = _row_of(data, now)
    claimed = AssistantUsage.objects.filter(pk=row.pk, messages__lt=limit).update(
        messages=F("messages") + 1, updated_at=now
    )
    row.refresh_from_db(fields=["messages", "month"])
    if claimed:
        record_event(ctx, events.MESSAGE_CLAIMED, {**_caller_payload(data), "used": row.messages, "limit": limit})
    return {
        "claimed": bool(claimed),
        "month": row.month,
        "used": row.messages,
        "limit": limit,
        "resets_at": None if data.demo else queries.resets_at(row.month),
        "demo": bool(data.demo),
    }


@operation(
    "assistant.message.release",
    kind="command",
    permission="assistant.manage",
    input=MessageReleaseIn,
    output=UsageOut,
    ai=INTERNAL,  # platform
)
def message_release(ctx: OperationContext, data: MessageReleaseIn) -> dict:
    """Give back the message a turn took in ``month``, when it failed before answering anything (the platform only):
    the person saw no answer, so it is not spent. Never below zero."""
    queries.platform_only(ctx)
    caller = data.caller
    rows = _rows_of(caller, data.month)
    if rows.filter(messages__gt=0).update(messages=F("messages") - 1, updated_at=timezone.now()):
        record_event(
            ctx,
            events.MESSAGE_RELEASED,
            {**_caller_payload(caller), "used": rows.values_list("messages", flat=True).first() or 0},
        )
    return queries.usage_of(caller, timezone.now())


@operation(
    "assistant.usage.record",
    kind="command",
    permission="assistant.manage",
    input=UsageRecordIn,
    output=UsageOut,
    ai=INTERNAL,  # platform
)
def usage_record(ctx: OperationContext, data: UsageRecordIn) -> dict:
    """Add what a turn, an embedding or the voice spent to the caller's row of now (the platform only): tokens,
    dictations, characters read aloud and their cost in USD. Never a message: those are claimed."""
    queries.platform_only(ctx)
    now = timezone.now()
    row = _row_of(data.caller, now)
    spent = data.model_dump(exclude={"caller"})
    AssistantUsage.objects.filter(pk=row.pk).update(
        **{field: F(field) + value for field, value in spent.items()}, updated_at=now
    )
    record_event(ctx, events.USAGE_RECORDED, {**_caller_payload(data.caller), **{k: str(v) for k, v in spent.items()}})
    return queries.usage_of(data.caller, now)


# --- The report of an answer (ASSISTANT-G58) ----------------------------------------------------------------------

#: The characters of each text a report mails (the question, the answer, the comment).
REPORT_TEXT_MAX = 4000
#: A report of the same answer within this time mails nothing again (a double tap, a retry of the Hub).
REPORT_ONCE_SECONDS = 24 * 60 * 60


@operation(
    "assistant.report.send",
    kind="command",
    permission="assistant.manage",
    input=ReportSendIn,
    output=ReportOut,
    ai=INTERNAL,  # platform
)
def report_send(ctx: OperationContext, data: ReportSendIn) -> dict:
    """Mail the report of an answer to the support mailbox (the platform only), in English (the team's mail), with
    the business (the demo, or the account of the panel's own assistant), the reason, the comment, the question and
    the answer, each cut to ``REPORT_TEXT_MAX``; nothing is kept nor logged. The same answer (``message_id``) of the same business within a day is a ``duplicate``. A business
    that stopped working since the door resolved it gets the door's answer (404 ``hub_unknown``, 403 ``hub_inactive``)
    and nothing is mailed. 503 ``assistant.report_not_sent`` if the mail cannot leave. The event is written before the
    mail, so nothing that can undo the transaction comes after it: a mail that cannot leave undoes the event, and an
    event that cannot be written sends nothing. Whatever fails, the report can be sent again."""
    from django.core.cache import cache

    queries.platform_only(ctx)
    caller = data.caller
    if caller.demo:
        who, details = caller.demo, [("Demo", caller.demo)]
    elif caller.user_id is not None:
        email = get_user_model().objects.filter(pk=caller.user_id).values_list("email", flat=True).first()
        if email is None:
            raise NotFound(_("The account no longer exists."), code="assistant.account_unknown")
        who, details = email, [("Account", email)]
    else:
        hub = queries.working(Hub.objects.filter(pk=caller.hub_id).first())
        who, details = hub.name, [("Business", f"{hub.name} ({hub.slug}, {hub.id})")]
    key = f"demo:{caller.demo}" if caller.demo else f"user:{caller.user_id}" if caller.user_id else caller.hub_id
    once = f"assistant:report:{key}:{data.message_id}"
    if not cache.add(once, 1, REPORT_ONCE_SECONDS):
        return {"sent": False, "duplicate": True}
    try:
        record_event(ctx, events.REPORT_SENT, {**_caller_payload(caller), "reason": data.reason})
        _mail_report(ctx, who, details, data)
    except BaseException:
        cache.delete(once)
        raise
    return {"sent": True, "duplicate": False}


def _mail_report(ctx: OperationContext, who: str, details: list[tuple[str, str]], data: ReportSendIn) -> None:
    """The report's mail to the support mailbox; 503 ``assistant.report_not_sent`` if it cannot leave."""
    from base.emails import branded_message

    lines = [
        *(f"{label}: {value}" for label, value in details),
        f"Reason: {data.reason}",
        f"Message: {data.message_id}",
        "",
        "Comment:",
        data.comment[:REPORT_TEXT_MAX] or "—",
        "",
        "Question:",
        data.question[:REPORT_TEXT_MAX] or "—",
        "",
        "Answer:",
        data.answer[:REPORT_TEXT_MAX],
    ]
    try:
        branded_message(f"[Assistant report] {who} · {data.reason}", lines, [settings.SUPPORT_EMAIL], language="en").send()
    except Exception:  # noqa: BLE001 - any failure of the mail backend is answered, not raised
        logger.exception("assistant.report_mail_failed")
        with translation.override(ctx.language):
            raise OperationError(
                _("The report could not be sent: try again in a moment."), code="assistant.report_not_sent", status=503
            ) from None
