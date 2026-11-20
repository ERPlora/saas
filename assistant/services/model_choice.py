"""Which models a provider keeps, which one answers and which one stands in for it, and a model tried from the admin.

- ``assistant.model.select``: the provider keeps exactly the models ticked among those its API listed, except the
  ones the policy uses.
- ``assistant.policy.update``: the model that answers and the fallback one, each available and of an enabled
  provider, and different.
- ``assistant.model.try``: a member of the staff tried a model from the admin; it stays in the audit trail (an access
  to the model) with how long the message was and how many tools it offered, never the message.
"""

from auditlog.models import LogEntry
from django.utils import translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import INTERNAL, operation
from live.outbox import record_event

from assistant import events
from assistant.models import AIModel, AIProvider, AIRoutingPolicy
from assistant.queries import choosable_models, staff_with
from assistant.schemas import ModelSelectIn, ModelSelectOut, ModelTryIn, ModelTryOut, PolicyIn, PolicyOut


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
