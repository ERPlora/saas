"""Which model answers, and the route of a turn.

- ``assistant.policy.show``: which model answers and which one is the fallback, with the models that
  can be chosen (available, of an enabled provider).
- ``assistant.route.resolve``: the models a turn tries, in order (the one that answers, then its
  fallback), each with its provider's key; read again on every turn, so a change applies to the next one.
"""

from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.operations import INTERNAL, operation

from assistant.models import AIModel, AIRoutingPolicy
from assistant.queries.gates import staff_with
from assistant.schemas import NoInput, PolicyShowOut, RouteIn, RouteOut


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
    ai=INTERNAL,  # staff
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
        "reasoning_effort": model.reasoning_effort,
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
    ai=INTERNAL,  # platform
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
            api_key = model.provider.api_key
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
            if can_answer(model) and (api_key := model.provider.api_key):
                candidates.append(route_candidate(model, api_key))
        if not candidates:
            raise provider_not_configured()
    return {"candidates": candidates}
