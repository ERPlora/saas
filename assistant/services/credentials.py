"""A provider's key, kept encrypted with its hint.

- ``assistant.credential.save`` / ``.delete``: typing another key is a rotation. A change that types no key never
  writes the stored token again (an unreadable one stays as it was, waiting for its key to come back or to be typed
  again).
- ``assistant.credential.import``: the platform keeps a provider's key from the environment
  (``import_ai_keys_from_env``), adding the provider of its API if missing; a key already kept stays unless forced.
"""

from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from assistant import crypto, events
from assistant.models import AIProvider, AIProviderCredential
from assistant.queries import staff_with
from assistant.schemas import (
    CredentialDeleteIn,
    CredentialDeleteOut,
    CredentialImportIn,
    CredentialImportOut,
    CredentialIn,
    CredentialOut,
)
from assistant.services.encryption import _encryption_missing


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
def credential_save(ctx: OperationContext, data: CredentialIn) -> dict:  # noqa: C901, PLR0912
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
    slug = data.kind
    provider = AIProvider.objects.filter(slug=slug).first()
    credential = (
        AIProviderCredential.objects.select_for_update().filter(provider=provider, label=data.label).first()
        if provider is not None
        else None
    )
    if credential is not None and not data.force:
        return {"provider": slug, "action": "kept", "label": data.label, "masked_key": credential.masked_key}
    action = "created" if credential is None else "rotated"
    result = {"provider": slug, "action": action, "label": data.label, "masked_key": f"…{plaintext[-4:]}"}
    if data.dry_run:
        return result
    if not crypto.configured():
        raise _encryption_missing(ctx)
    if provider is None:
        provider = AIProvider.objects.create(slug=slug, name=AIProvider.Kind(data.kind).label, kind=data.kind)
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
