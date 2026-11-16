"""The plans on sale, the plan whose rights a business has, and the modules each plan includes."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.utils import translation
from live.context import OperationContext
from live.operations import AI, operation

from apps.models import Module
from hubs.models import Plan, Subscription
from hubs.schemas import PlanListIn, PlanListOut


@operation(
    "hubs.plan.list",
    kind="query",
    permission=None,
    input=PlanListIn,
    output=PlanListOut,
    expose_api=True,
    ai=AI(
        description="The plans ERPlora sells, with their prices and what each one includes.",
        asks={
            "en": ("what plans do you have?", "how much is Standard?", "what does the Starter plan include?"),
            "es": ("¿qué planes hay?", "¿cuánto cuesta el Standard?", "¿qué incluye el plan Starter?"),
        },
    ),
)
def plan_list(ctx: OperationContext, data: PlanListIn) -> dict[str, Any]:
    """The plans on sale (``Plan.objects.public()``), by display order then price.

    Each plan's features end with its real trial, except an upgrade's: an upgrade grants none. Rows
    that are only a visual separator («───») are dropped.
    """
    plans = list(Plan.objects.public().order_by("display_order", "price_monthly"))
    signable = [plan for plan in plans if not plan.upgrade_only]
    cheapest = min(
        signable,
        key=lambda plan: (plan.price_monthly, plan.display_order),
        default=None,
    )
    trial_days = Plan.objects.signup_trial_days()["trial_days_max"] or 0
    with translation.override(ctx.language):
        rows = [plan_card(plan, ctx.language) for plan in plans]
    return {
        "signup_trial_days": trial_days,
        "cheapest_slug": cheapest.slug if cheapest else None,
        "plans": rows,
    }


def plan_card(plan: Plan, language: str) -> dict[str, Any]:
    """A plan as ``hubs.plan.list`` gives it (``PlanOut``), in ``language``."""
    features = [
        feature
        for feature in plan.translated("features", language)
        if str(feature).strip().strip("─").strip()
    ]
    if not plan.upgrade_only and plan.trial_label:
        features.append(plan.trial_label)
    return {
        "slug": plan.slug,
        "name": plan.translated("name", language),
        "description": plan.translated("description", language),
        "price_monthly": plan.price_monthly,
        "price_annual": plan.price_annual,
        "features": features,
        "featured_label": plan.translated("featured_label", language),
        "max_users": plan.max_users,
        "max_devices": plan.max_devices,
        "trial_period_days": plan.trial_period_days,
        "has_trial": plan.has_trial(),
        "support_level_label": plan.support_level_label,
        "included_level_label": plan.included_level_label,
        "resources_label": plan.resources_label,
        "assistant_messages_per_month": plan.assistant_messages_per_month,
        "whatsapp_messages_per_month": plan.whatsapp_messages_per_month,
        "max_apps": plan.max_apps,
        "includes_custom_domain": plan.includes_custom_domain,
        "upgrade_only": plan.upgrade_only,
        "internal_only": plan.internal_only,
    }


def plan_ref(plan: Plan) -> dict[str, Any]:
    """``plan`` as a business carries it (``PlanRefOut``), in the active language."""
    return {
        "slug": plan.slug,
        "name": plan.translated("name"),
        "price_monthly": plan.price_monthly,
        "max_devices": plan.max_devices,
        "max_apps": plan.max_apps,
    }


def free_plan() -> Plan | None:
    """The permanent Free plan (0 €) a business is born on, or ``None`` if it is not seeded."""
    return (
        Plan.objects.public().filter(price_monthly=0).order_by("display_order").first()
    )


def trial_plan() -> Plan | None:
    """The plan a Free business is born trying (Starter), if it is on sale with a trial."""
    return Plan.objects.public().filter(slug="starter", trial_period_days__gt=0).first()


#: The module tiers from the lowest: ``Plan.included_level`` and ``apps.Module.tier`` share the names.
LEVELS = [Plan.IncludedLevel.FREE, Plan.IncludedLevel.BASIC, Plan.IncludedLevel.PRO, Plan.IncludedLevel.ENTERPRISE]


def modules_included_in(plan: Plan | None) -> list[str]:
    """The paid modules ``plan`` includes, by slug: every ``apps.Module`` whose tier its ``included_level`` reaches.

    A module taken off sale (``is_active`` off) stays included: that switch stops new purchases, not the rights
    the plans give."""
    if plan is None or plan.included_level not in LEVELS:
        return []
    reached = LEVELS[: LEVELS.index(plan.included_level) + 1]
    return list(Module.objects.filter(tier__in=reached).order_by("slug").values_list("slug", flat=True))


def _effective_plan(subscription: Subscription | None, now: datetime) -> Plan | None:
    return subscription.effective_plan(now) if subscription else free_plan()


def effective_plan(hub_id: UUID, now: datetime) -> Plan | None:
    """The plan whose rights the business has at ``now`` (its trial's while it lasts; Free without a subscription):
    the one its snapshot carries, and whose ``whatsapp_messages_per_month`` erplora.com counts its sends against."""
    subscription = Subscription.objects.select_related("plan", "trial_plan").filter(hub_id=hub_id).first()
    return _effective_plan(subscription, now)
