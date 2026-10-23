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
"""

from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, NotFound, OperationError
from live.operations import operation
from live.outbox import record_event

from assistant import crypto, events
from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy
from assistant.queries import choosable_models, staff_with
from assistant.schemas import (
    CredentialDeleteIn,
    CredentialDeleteOut,
    CredentialIn,
    CredentialOut,
    ModelSelectIn,
    ModelSelectOut,
    PolicyIn,
    PolicyOut,
)


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
