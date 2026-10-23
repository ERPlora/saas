"""The reads of the AI gateway, each an operation (``@operation``, ``kind="query"``) in a read-only transaction.

- ``assistant.provider.connection`` (ASSISTANT-G24): what the client of a provider needs to list its models: its
  API, its address and its usable key, the most recent active one that opens (a ``SecretStr``).

``staff_with`` is the gate every operation of the staff passes: an active member of the staff holding the model
permission of Django that backs it.
"""

from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import operation

from assistant.models import AIProvider, AIProviderCredential
from assistant.schemas import ConnectionOut, ProviderRef


def staff_with(ctx: OperationContext, *permissions: str):
    """The active member of the staff running ``ctx`` who holds every one of ``permissions``; anybody else, 403."""
    user = ctx.actor
    if not (
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and all(user.has_perm(permission) for permission in permissions)
    ):
        with translation.override(ctx.language):
            raise PermissionDenied(
                _("Only ERPlora's staff with this permission configure the AI."), code="assistant.staff_only"
            )
    return user


def usable_key(provider: AIProvider) -> str:
    """The most recent active key of ``provider`` that opens, or ``""``."""
    for credential in AIProviderCredential.objects.filter(provider=provider, is_active=True).order_by("-updated_at"):
        if credential.is_readable:
            return credential.api_key
    return ""


@operation(
    "assistant.provider.connection",
    kind="query",
    permission="assistant.manage",
    input=ProviderRef,
    output=ConnectionOut,
)
def provider_connection(ctx: OperationContext, data: ProviderRef) -> dict:
    """The API, address and usable key of a provider (``view_aiprovider``). 404 ``assistant.provider_unknown``,
    409 ``assistant.no_key`` without an active key that opens."""
    staff_with(ctx, "assistant.view_aiprovider")
    with translation.override(ctx.language):
        provider = AIProvider.objects.filter(pk=data.id).first()
        if provider is None:
            raise NotFound(_("This provider does not exist."), code="assistant.provider_unknown")
        api_key = usable_key(provider)
        if not api_key:
            raise Conflict(
                _("This provider has no active key: add one on its page and try again."), code="assistant.no_key"
            )
    return {
        "id": provider.pk,
        "name": str(provider),
        "kind": provider.kind,
        "base_url": provider.api_base,
        "api_key": api_key,
        "existing": sorted(provider.models.values_list("model_id", flat=True)),
    }
