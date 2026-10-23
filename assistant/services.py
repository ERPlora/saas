"""The writes of the AI gateway, each an operation (``@operation``, ``kind="command"``) in its own transaction, with
its event in the outbox.

The admin calls them as the member of the staff who clicks (``assistant.admin.staff_context``): each one checks
the model permission of Django that backs it, so a member of the staff without it is refused here too, not only
on the page. The commands call them as the platform (``platform_context``).

- ``assistant.credential.save`` / ``.delete`` (ASSISTANT-G26, G16): a provider's key, kept encrypted with its hint;
  typing another one is a rotation. A change that types no key never writes the stored token again (an unreadable
  one stays as it was, waiting for its key to come back or to be typed again).
"""

from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from assistant import crypto, events
from assistant.models import AIProvider, AIProviderCredential
from assistant.schemas import CredentialDeleteIn, CredentialDeleteOut, CredentialIn, CredentialOut


def platform_context() -> OperationContext:
    """The platform acting on the gateway (its commands, the Hub's doors)."""
    return system_context(Scope("platform", "assistant"))


def staff_with(ctx: OperationContext, permission: str):
    """The active member of the staff running ``ctx`` who holds ``permission``; anybody else, 403."""
    user = ctx.actor
    if not (
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and user.has_perm(permission)
    ):
        with translation.override(ctx.language):
            raise PermissionDenied(
                _("Only ERPlora's staff with this permission configure the AI."), code="assistant.staff_only"
            )
    return user


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
