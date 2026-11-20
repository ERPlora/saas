"""The usable keys of the providers.

- ``assistant.provider.connection``: what the client of a provider needs to list its models: its
  API, its address and its usable key, the most recent active one that opens (a ``SecretStr``).
- ``assistant.service.connection``: the address and the usable key of the services' provider, which computes the
  embeddings and transcribes the dictation.
"""

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import INTERNAL, operation

from assistant.models import AIProvider, AIProviderCredential
from assistant.queries.gates import platform_only, staff_with
from assistant.schemas import ConnectionOut, NoInput, ProviderRef, ServiceConnectionOut


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
    ai=INTERNAL,  # staff
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


@operation(
    "assistant.service.connection",
    kind="query",
    permission="assistant.manage",
    input=NoInput,
    output=ServiceConnectionOut,
    ai=INTERNAL,  # platform
)
def service_connection(ctx: OperationContext, data: NoInput) -> dict:
    """The address and the usable key of the services' provider (``ASSISTANT_SERVICE_PROVIDER``), which computes the
    embeddings and transcribes the dictation (the platform only). 409 ``assistant.provider_not_configured`` if it does not exist, is
    off, speaks another API than OpenAI's or has no active key that opens."""
    platform_only(ctx)
    service = services_provider()
    if service is None:
        with translation.override(ctx.language):
            raise Conflict(
                _("The provider of the embeddings and the voice is not configured: add OpenAI with its key."),
                code="assistant.provider_not_configured",
            )
    return service


def services_provider() -> dict | None:
    """The services' provider with its usable key, or ``None`` if it does not exist, is off, speaks another API than
    OpenAI's or has no active key that opens."""
    provider = AIProvider.objects.filter(
        slug=settings.ASSISTANT_SERVICE_PROVIDER, is_enabled=True, kind=AIProvider.Kind.OPENAI
    ).first()
    api_key = usable_key(provider) if provider is not None else ""
    if not api_key:
        return None
    return {"provider": provider.slug, "base_url": provider.api_base, "api_key": api_key}
