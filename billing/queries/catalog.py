"""What is sold and what Stripe bills for it, and the Store's catalog: ``billing.store.catalog``."""

from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext
from live.operations import AI, operation

from apps import queries as app_queries
from apps.icons import FALLBACK_ICON_SVG
from apps.models import Module
from billing.queries.subscriptions import scheduled_change_of
from billing.schemas.store import StoreCatalogIn, StoreCatalogOut
from hubs.queries import access_control, plan_catalog
from hubs.services import refusals
from hubs.models import HubMember, Plan, Subscription, SubscriptionItem


# --- What is sold, and what Stripe bills --------------------------------------------------------------


def plan_on_sale(slug: str, hub):
    """The active plan with that slug ``hub`` may be sold (``Plan.objects.offered_to``), or ``None``."""
    return Plan.objects.offered_to(hub).filter(slug=slug).first()


#: The billings a plan or module is sold with, in the order the Store offers them.
INTERVALS = ("month", "year")


def plan_price_id(plan: Plan, interval: str) -> str:
    """The Stripe price that bills ``plan`` with that billing, pasted in the admin; empty: not sold with it."""
    return plan.stripe_price_id_annual if interval == "year" else plan.stripe_price_id


def sold_intervals(plan: Plan) -> list[str]:
    """The billings ``plan`` is sold with: the ones it has a Stripe price for."""
    return [interval for interval in INTERVALS if plan_price_id(plan, interval)]


def module_on_sale(slug: str):
    """The paid module with that slug, while it is on sale (``apps.Module``), or ``None``."""
    return Module.objects.filter(slug=slug, is_active=True).first()


def businesses_having_module(slug: str) -> list[str]:
    """The names of the businesses that have the bought module ``slug`` now (open-ended, or cancelled and still
    working): what Stripe bills or billed for this period (its row is not deleted)."""
    now = timezone.now()
    items = SubscriptionItem.objects.filter(
        module_slug=slug, source=SubscriptionItem.Source.PURCHASE
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
    return sorted(set(items.values_list("subscription__hub__name", flat=True)))


def plan_for_price(price_id: str):
    """``(plan, interval)`` of a Stripe price of a plan, or ``None`` when no plan has it."""
    if not price_id:
        return None
    plan = Plan.objects.filter(stripe_price_id=price_id).first()
    if plan is not None:
        return plan, "month"
    plan = Plan.objects.filter(stripe_price_id_annual=price_id).first()
    return (plan, "year") if plan is not None else None


def module_for_price(price_id: str):
    """``(module, interval)`` of a Stripe price of a module (retired ones too), or ``None``."""
    if not price_id:
        return None
    module = Module.objects.filter(stripe_price_id_monthly=price_id).first()
    if module is not None:
        return module, "month"
    module = Module.objects.filter(stripe_price_id_annual=price_id).first()
    return (module, "year") if module is not None else None


# --- The Store ----------------------------------------------------------------------------------------

#: Statuses of a Stripe subscription that bill nothing any more (``billing.services.stripe_sales.ENDED_STATUSES``).
_ENDED_STATUSES = frozenset({"canceled", "incomplete_expired"})


def is_paying(subscription: Subscription | None) -> bool:
    """Stripe bills the business already: it has a subscription there that has not ended."""
    return (
        subscription is not None
        and bool(subscription.stripe_subscription_id)
        and subscription.status not in _ENDED_STATUSES
    )


def offered_plans(hub, paying: bool):
    """The paid plans on sale ``hub`` may move to (the catalogue, ``hubs/0013``): the ones sold at sign-up
    while Stripe does not bill it (Free), the ``upgrade_only`` ones too once it pays. Free is not bought (a paid
    plan is cancelled to get it) and an ``internal_only`` plan only to a business the staff marked."""
    plans = Plan.objects.offered_to(hub).filter(price_monthly__gt=0)
    if not paying:
        plans = plans.filter(upgrade_only=False)
    return plans.order_by("display_order", "price_monthly")


@operation(
    "billing.store.catalog",
    kind="query",
    permission="billing.view",
    input=StoreCatalogIn,
    output=StoreCatalogOut,
    ai=AI(
        description="What the store sells a business, with prices, and what it already has.",
        asks={
            "en": (
                "what can I buy for the bar?",
                "how much would the inventory module cost me?",
                "what's for sale in the store?",
            ),
            "es": (
                "¿qué puedo comprar para el bar?",
                "¿cuánto me costaría añadir el módulo de stock?",
                "¿qué vende la tienda?",
            ),
        },
    ),
)
def store_catalog(ctx: OperationContext, params: StoreCatalogIn) -> dict:
    """What the Store sells the business and what it already has: every paid module on sale with its net
    prices in cents, whether the business owns it (bought or included in its plan; a cancelled one until it
    ends), the plan, its billing and whether Stripe bills it already, and the paid plans it may move to
    (``offered_plans``: no upgrade-only plan for a business Stripe does not bill; the internal ones only to a business
    the staff marked, with their card in ``internal_plans``). Only the owner buys for a business,
    so only the owner reads it; a deleted business buys nothing (409). Never asks Stripe."""
    member = access_control.access(access_control.account_of(ctx), params.hub_id, HubMember.Role.OWNER)
    if not access_control.is_writable(member.hub):
        raise refusals.business_deleted()
    subscription = (
        Subscription.objects.select_related("plan", "trial_plan").filter(hub_id=member.hub_id).first()
    )
    now = timezone.now()
    owned = {}
    if subscription is not None:
        for item in SubscriptionItem.objects.filter(subscription=subscription).order_by("module_slug"):
            if item.is_live(now):
                owned[item.module_slug] = item
    # On sale, and the ones the business has although they are not any more (taking a module off
    # sale stops new purchases, never the charge of who has it, so its owner still sees it to cancel it).
    rows = Module.objects.filter(Q(is_active=True) | Q(slug__in=owned)).order_by("slug")
    cards = app_queries.cards_of([row.slug for row in rows], ctx.language or "")
    modules = []
    for module in rows:
        item = owned.get(module.slug)
        card = cards.get(module.slug)
        modules.append(
            {
                "slug": module.slug,
                "tier": module.tier,
                "price_monthly_cents": module.price_monthly_cents,
                "price_annual_cents": module.price_annual_cents,
                "owned": item is not None,
                "source": item.source if item is not None else None,
                "valid_until": item.valid_until if item is not None else None,
                "on_sale": module.is_active,
                "name": card["name"] if card else module.slug,
                "summary": card["summary"] if card else "",
                "icon_svg": card["icon_svg"] if card else FALLBACK_ICON_SVG,
            }
        )
    plan = None
    paying = is_paying(subscription)
    if subscription is not None:
        plan = {
            "plan": subscription.plan.slug,
            "billing_interval": subscription.billing_interval,
            "status": subscription.status,
            "paying": paying,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "current_period_end": subscription.current_period_end,
            "trial_plan": subscription.trial_plan.slug if subscription.trial_plan_id else None,
            "trial_end": subscription.trial_end,
            "scheduled_change": scheduled_change_of(member.hub_id),
        }
    offered = list(offered_plans(member.hub, paying))
    # ``hubs.plan.list`` lists only the public plans: the internal ones the business is offered, and the one it
    # has even once it is not offered any more, come with their card.
    internal = [row for row in offered if row.internal_only]
    if subscription is not None and subscription.plan.internal_only and subscription.plan not in internal:
        internal.append(subscription.plan)
    return {
        "hub_id": member.hub_id,
        "subscription": plan,
        "modules": modules,
        "offered_plans": [row.slug for row in offered],
        "sold_intervals": {row.slug: sold_intervals(row) for row in offered},
        "internal_plans": [plan_catalog.plan_card(row, ctx.language or "") for row in internal],
    }
