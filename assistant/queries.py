"""The reads of the AI gateway, each an operation (``@operation``, ``kind="query"``) in a read-only transaction.

- ``assistant.provider.connection`` (ASSISTANT-G24): what the client of a provider needs to list its models: its
  API, its address and its usable key, the most recent active one that opens (a ``SecretStr``).
- ``assistant.policy.show`` (G27, G60): which model answers and which one is the fallback, with the models that
  can be chosen (available, of an enabled provider).
- ``assistant.route.resolve`` (G45, G39): the models a turn tries, in order (the one that answers, then its
  fallback), each with its usable key; read again on every turn, so a change applies to the next one.

``staff_with`` is the gate every operation of the staff passes: an active member of the staff holding the model
permission of Django that backs it.
"""

from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.operations import operation

from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy
from assistant.schemas import ConnectionOut, NoInput, PolicyShowOut, ProviderRef, RouteIn, RouteOut


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


def route_candidate(model: AIModel, api_key: str) -> dict:
    return {
        "model": model.pk,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "provider": str(model.provider),
        "kind": model.provider.kind,
        "base_url": model.provider.api_base,
        "api_key": api_key,
        "price_input_per_1m": model.price_input_per_1m,
        "price_output_per_1m": model.price_output_per_1m,
        "supports_tools": model.supports_tools,
        "supports_vision": model.supports_vision,
    }


def can_answer(model: AIModel | None) -> bool:
    return model is not None and model.is_available and model.provider.is_enabled


def provider_not_configured() -> Conflict:
    return Conflict(
        _("No model can answer: the providers of the chosen models have no active key."),
        code="assistant.provider_not_configured",
    )


@operation(
    "assistant.route.resolve",
    kind="query",
    permission="assistant.manage",
    input=RouteIn,
    output=RouteOut,
)
def route_resolve(ctx: OperationContext, data: RouteIn) -> dict:
    """The models a turn tries, in order, with their keys: the platform's turns take the policy's (no ``model``);
    the staff try one model (``change_airoutingpolicy``). Without ``model``: 409 ``assistant.no_model`` when no
    model answers, 409 ``assistant.provider_not_configured`` when none of them can be used. With it: 422
    ``assistant.model_unavailable`` (unknown, off, or its provider off), 409 ``assistant.provider_not_configured``."""
    if ctx.actor != "system":
        staff_with(ctx, "assistant.change_airoutingpolicy")
    with translation.override(ctx.language):
        if data.model is not None:
            model = AIModel.objects.filter(pk=data.model).select_related("provider").first()
            if not can_answer(model):
                raise OperationError(
                    _("This model is off or its provider is: turn them on to use it."),
                    code="assistant.model_unavailable",
                    status=422,
                )
            api_key = usable_key(model.provider)
            if not api_key:
                raise provider_not_configured()
            return {"candidates": [route_candidate(model, api_key)]}

        policy = (
            AIRoutingPolicy.objects.filter(slot=AIRoutingPolicy.SLOT)
            .select_related("active_model__provider", "fallback_model__provider")
            .first()
        )
        if policy is None or policy.active_model is None:
            raise Conflict(
                _("No model answers yet: choose one on the page “Model that answers”."), code="assistant.no_model"
            )
        candidates = []
        for model in (policy.active_model, policy.fallback_model):
            if can_answer(model) and (api_key := usable_key(model.provider)):
                candidates.append(route_candidate(model, api_key))
        if not candidates:
            raise provider_not_configured()
    return {"candidates": candidates}
