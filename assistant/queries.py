"""The reads of the AI gateway, each an operation (``@operation``, ``kind="query"``) in a read-only transaction.

- ``assistant.provider.connection`` (ASSISTANT-G24): what the client of a provider needs to list its models: its
  API, its address and its usable key, the most recent active one that opens (a ``SecretStr``).
- ``assistant.policy.show`` (G27, G60): which model answers and which one is the fallback, with the models that
  can be chosen (available, of an enabled provider).

``staff_with`` is the gate every operation of the staff passes: an active member of the staff holding the model
permission of Django that backs it.
"""

from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import operation

from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy
from assistant.schemas import ConnectionOut, NoInput, PolicyShowOut, ProviderRef


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


def choosable_models():
    """The models that may answer: available, of an enabled provider."""
    return (
        AIModel.objects.filter(is_available=True, provider__is_enabled=True)
        .select_related("provider")
        .order_by("provider__name", "display_name", "model_id")
    )


def model_label(model: AIModel) -> str:
    return f"{model.provider.name} · {model.display_name} ({model.model_id})"


@operation(
    "assistant.policy.show",
    kind="query",
    permission="assistant.manage",
    input=NoInput,
    output=PolicyShowOut,
)
def policy_show(ctx: OperationContext, data: NoInput) -> dict:
    """The policy and the models that can be chosen (``view_airoutingpolicy``)."""
    staff_with(ctx, "assistant.view_airoutingpolicy")
    policy = AIRoutingPolicy.objects.filter(slot=AIRoutingPolicy.SLOT).select_related("updated_by").first()
    return {
        "active_model": policy.active_model_id if policy else None,
        "fallback_model": policy.fallback_model_id if policy else None,
        "updated_at": policy.updated_at if policy else None,
        "updated_by": policy.updated_by.email if policy and policy.updated_by else "",
        "choices": [{"id": model.pk, "label": model_label(model)} for model in choosable_models()],
    }
