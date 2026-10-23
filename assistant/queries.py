"""The reads of the AI gateway, each an operation (``@operation``, ``kind="query"``) in a read-only transaction.

- ``assistant.provider.connection`` (ASSISTANT-G24): what the client of a provider needs to list its models: its
  API, its address and its usable key, the most recent active one that opens (a ``SecretStr``).
- ``assistant.policy.show`` (G27, G60): which model answers and which one is the fallback, with the models that
  can be chosen (available, of an enabled provider).
- ``assistant.route.resolve`` (G45, G39): the models a turn tries, in order (the one that answers, then its
  fallback), each with its usable key; read again on every turn, so a change applies to the next one.
- ``assistant.caller.resolve`` (G42): the business (or the demo) a call of the Hub names, if its people can use the
  assistant now.
- ``assistant.usage.show`` (G05, G50, G51): what a business (or a demo) spent of its allowance: the plan's monthly
  messages (a demo, its own few for its whole life).

``staff_with`` is the gate every operation of the staff passes: an active member of the staff holding the model
permission of Django that backs it.
"""

from datetime import date, datetime
from datetime import timezone as dt_timezone
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.operations import operation
from live.slugs import is_demo_slug, validate_hub_slug

from assistant.models import AIModel, AIProvider, AIProviderCredential, AIRoutingPolicy, AssistantUsage
from assistant.schemas import (
    Caller,
    CallerIn,
    ConnectionOut,
    NoInput,
    PolicyShowOut,
    ProviderRef,
    RouteIn,
    RouteOut,
    ServiceConnectionOut,
    UsageOut,
)
from hubs import queries as hubs_queries
from hubs.models import Hub


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


# --- The Hub's turn (part 2): who calls and what it spent (ASSISTANT-G42, G05, G50, G51) -------------------------

#: The states of a business whose people use the assistant: working, or with a payment pending (its grace days).
WORKING = (Hub.Status.ACTIVE, Hub.Status.PAST_DUE)


def platform_only(ctx: OperationContext) -> None:
    """Only the platform (the Hub's doors, the commands) runs this operation."""
    if ctx.actor != "system":
        with translation.override(ctx.language):
            raise PermissionDenied(_("Only the platform asks this."), code="assistant.platform_only")


def unknown_hub() -> NotFound:
    return NotFound("No business the SaaS knows goes by that hub.", code="hub_unknown")


@operation(
    "assistant.caller.resolve",
    kind="query",
    permission="assistant.manage",
    input=CallerIn,
    output=Caller,
)
def caller_resolve(ctx: OperationContext, data: CallerIn) -> dict:
    """The business (or the demo) a call of the Hub names in ``hub`` (the platform only): a business by its address
    or its id (the UUID's own spelling), a demo by its ``demo-…`` address. 404 ``hub_unknown`` (unknown or purged),
    403 ``hub_inactive`` (preparing, suspended or being deleted: its people cannot be in it)."""
    platform_only(ctx)
    ref = data.hub.strip()
    if is_demo_slug(ref):
        try:
            slug = validate_hub_slug(ref.lower(), allow_demo=True)
        except ValueError:
            raise unknown_hub() from None
        return {"hub_id": None, "demo": slug, "slug": slug}
    try:
        key = UUID(ref)
    except ValueError:
        key = None
    named = Q(id=key) if key is not None and str(key) == ref else Q(slug=ref)
    hub = Hub.objects.filter(named).exclude(status=Hub.Status.DELETED).first()
    if hub is None:
        raise unknown_hub()
    if hub.status not in WORKING:
        raise PermissionDenied("The business does not work now: its people cannot use the assistant.", code="hub_inactive")
    return {"hub_id": hub.id, "demo": "", "slug": hub.slug}


def month_of(now: datetime) -> date:
    """The first day of ``now``'s calendar month in UTC: the window of the allowance."""
    return now.astimezone(dt_timezone.utc).date().replace(day=1)


def resets_at(month: date) -> datetime:
    """When the allowance of ``month`` comes back: 00:00 UTC on the first day of the next month."""
    year, following = (month.year + 1, 1) if month.month == 12 else (month.year, month.month + 1)
    return datetime(year, following, 1, tzinfo=dt_timezone.utc)


def monthly_limit(caller: Caller, now: datetime) -> int:
    """The messages the caller may send: a demo, its own few for its whole life; a business, its plan's this month
    (``Plan.assistant_messages_per_month`` of the plan whose rights it has now, its trial's included; 0 = none)."""
    if caller.demo:
        return settings.ASSISTANT_DEMO_MESSAGES
    plan = hubs_queries.effective_plan(caller.hub_id, now)
    return plan.assistant_messages_per_month if plan is not None else 0


def usage_row(caller: Caller, now: datetime):
    """The caller's row of usage now (a business's this month, a demo's only one), or ``None`` before its first use."""
    if caller.demo:
        return AssistantUsage.objects.filter(demo=caller.demo).first()
    return AssistantUsage.objects.filter(hub_id=caller.hub_id, month=month_of(now)).first()


def usage_of(caller: Caller, now: datetime) -> dict:
    row = usage_row(caller, now)
    return {
        "used": row.messages if row is not None else 0,
        "limit": monthly_limit(caller, now),
        "resets_at": None if caller.demo else resets_at(month_of(now)),
        "demo": bool(caller.demo),
    }


@operation(
    "assistant.usage.show",
    kind="query",
    permission="assistant.manage",
    input=Caller,
    output=UsageOut,
)
def usage_show(ctx: OperationContext, data: Caller) -> dict:
    """What the caller spent of its allowance now (the platform: the Hub's ``usage`` door and every turn's last
    frame; the staff: ``view_assistantusage``)."""
    if ctx.actor != "system":
        staff_with(ctx, "assistant.view_assistantusage")
    return usage_of(data, timezone.now())


@operation(
    "assistant.service.connection",
    kind="query",
    permission="assistant.manage",
    input=NoInput,
    output=ServiceConnectionOut,
)
def service_connection(ctx: OperationContext, data: NoInput) -> dict:
    """The address and the usable key of the services' provider (``ASSISTANT_SERVICE_PROVIDER``), which computes the
    embeddings and the voice (the platform only). 409 ``assistant.provider_not_configured`` if it does not exist, is
    off, speaks another API than OpenAI's or has no active key that opens."""
    platform_only(ctx)
    provider = AIProvider.objects.filter(
        slug=settings.ASSISTANT_SERVICE_PROVIDER, is_enabled=True, kind=AIProvider.Kind.OPENAI
    ).first()
    api_key = usable_key(provider) if provider is not None else ""
    if not api_key:
        with translation.override(ctx.language):
            raise Conflict(
                _("The provider of the embeddings and the voice is not configured: add OpenAI with its key."),
                code="assistant.provider_not_configured",
            )
    return {"provider": provider.slug, "base_url": provider.api_base, "api_key": api_key}
