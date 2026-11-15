"""The subscriptions of an account's businesses, their card and what cancelling the plan will do:
``billing.subscription.list``, ``billing.payment_method.get`` and ``billing.plan.cancel_preview``."""

import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.text import get_text_list
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, INTERNAL, operation

from apps import queries as app_queries
from apps.models import Module
from billing import stripe_service, vat
from billing.models import Invoice, PaymentFailure, PlanChangeSchedule
from billing.money import from_cents, to_cents
from billing.queries.invoices import CARD_CACHE_SECONDS, _billing_account, _owned_hub_ids
from billing.queries.tax import Payer, _vat_status_on_file, payer_of
from billing.schemas import (
    HubIn,
    PaymentMethodIn,
    PaymentMethodOut,
    PlanCancelPreviewOut,
    SubscriptionListIn,
    SubscriptionListOut,
)
from hubs import queries as hub_queries
from hubs import services as hub_services
from hubs.models import Hub, HubMember, Plan, Subscription


logger = logging.getLogger("billing.queries")


# --- Subscriptions -----------------------------------------------------------------------------------

#: A Stripe subscription that ended bills nothing: the business is back on Free.
ENDED_SUBSCRIPTIONS = ("canceled", "incomplete_expired")


def _module_price(module: Module | None, interval: str) -> int | None:
    if module is None:
        return None
    return module.price_annual_cents if interval == "year" else module.price_monthly_cents


def _plan_price(plan: Plan, interval: str) -> int:
    return to_cents((plan.price_annual if interval == "year" else plan.price_monthly) or 0)


def _with_vat_cents(parts: list[tuple[int, str]], payer: Payer) -> int | None:
    """What net amounts cost with VAT for this payer (``parts``: ``(cents, category)``), as the checkout
    prices them; ``None`` while the payer's place is unknown or has no rule."""
    if not payer.has_location:
        return None
    verified = _vat_status_on_file(payer.tax_id, payer.country) == "verified"
    total = 0
    for cents, category in parts:
        quote = vat.quote_vat(
            from_cents(cents),
            customer_country=payer.country,
            customer_postal_code=payer.postal_code,
            customer_tax_id=payer.tax_id,
            customer_tax_id_type=payer.tax_id_type,
            customer_tax_id_verified=verified,
            category_key=category,
        )
        if quote is None:
            return None
        total += to_cents(quote.base + quote.tax)
    return total


def _next_invoice_cents(plan: Plan | None, interval: str, renewing: list[Module | None], payer: Payer) -> int | None:
    """What the next invoice costs with VAT: the plan and the modules that renew, at their prices of ``interval``.
    ``None`` when that cannot be told: the payer's place is unknown, or the plan left the catalogue."""
    if plan is None:
        return None
    plan_cents = _plan_price(plan, interval)
    parts = [(plan_cents, vat.SAAS_SUBSCRIPTION_CATEGORY)] if plan_cents else []
    for module in renewing:
        if price := _module_price(module, interval):
            parts.append((price, vat.SOFTWARE_LICENSE_CATEGORY))
    return _with_vat_cents(parts, payer)


def scheduled_change_of(hub_id) -> dict | None:
    """The downgrade that waits for the end of the period of a business («Starter from 1 Nov»), if any."""
    pending = PlanChangeSchedule.objects.filter(hub_id=hub_id).first()
    if pending is None:
        return None
    return {"plan": pending.plan_slug, "interval": pending.interval, "starts_at": pending.starts_at}


def _subscription_row(  # noqa: PLR0913, PLR0917
    subscription: Subscription, user, owned: set, unpaid: dict, modules: dict, scheduled: dict, next_plans: dict
) -> dict:
    hub = subscription.hub
    plan = subscription.plan
    interval = subscription.billing_interval
    plan_cents = _plan_price(plan, interval)
    items = []
    renewing = []
    now = timezone.now()
    for item in subscription.items.all():
        if not item.is_live(now):
            # A cancelled module whose period ended is gone, as in the Hub's snapshot and in the store.
            continue
        module = modules.get(item.module_slug)
        items.append(
            {
                "slug": item.module_slug,
                "interval": interval,
                "price_cents": _module_price(module, interval),
                "source": item.source,
                "valid_until": item.valid_until,
            }
        )
        if item.source == "purchase" and item.valid_until is None:
            renewing.append(module)
    cancelling = subscription.cancel_at_period_end
    scheduled_change = scheduled.get(hub.id)
    next_invoice = None
    if not cancelling:
        # A downgrade that waits starts on that very date: Stripe's next phase bills the new items.
        next_plan, next_interval = (
            (next_plans.get(scheduled_change["plan"]), scheduled_change["interval"])
            if scheduled_change
            else (plan, interval)
        )
        next_invoice = {
            "date": subscription.current_period_end,
            "total_cents": _next_invoice_cents(next_plan, next_interval, renewing, payer_of(hub)),
            "currency": "EUR",
        }
    profile = hub.billing_profile
    # Charged to the card of another account: the payer before a hand-over.
    elsewhere = profile is None or profile.owner_id != user.pk or subscription.stripe_customer_id != profile.stripe_customer_id
    writable = hub.id in owned and hub_queries.is_writable(hub)
    manages = writable and not elsewhere
    unpaid_id = unpaid.get(hub.id)
    # A cancellation, or a downgrade that waits for the end of the period, is undone with «Keep the plan» until
    # that date: it leads the row.
    undoable = cancelling or scheduled_change is not None
    can = {
        "take_over": writable and elsewhere,
        "change_plan": manages and unpaid_id is None,
        "cancel_plan": manages and not cancelling,
        "keep_plan": manages and undoable,
        "view_invoice": unpaid_id is not None,
        "view_invoices": True,
    }
    order = ["view_invoice", "take_over",
             *(["keep_plan", "change_plan", "cancel_plan"] if undoable else ["change_plan", "cancel_plan"]),
             "view_invoices"]
    return {
        "business": {"id": hub.id, "name": hub.name},
        "plan": {"slug": plan.slug, "name": plan.translated("name"), "interval": interval, "price_cents": plan_cents},
        "modules": items,
        "next_invoice": next_invoice,
        "status": subscription.status,
        "status_label": str(Subscription.Status(subscription.status).label),
        "cancelling": cancelling,
        "ends_at": subscription.current_period_end if cancelling else None,
        "cancel_requested": subscription.cancel_requested_at is not None,
        "unpaid_invoice_id": unpaid_id,
        "scheduled_change": scheduled_change,
        "paid_by_another_account": elsewhere and hub.id in owned,
        "actions": [action for action in order if can[action]],
        "can": can,
    }


@operation(
    "billing.subscription.list",
    kind="query",
    permission="billing.view",
    input=SubscriptionListIn,
    output=SubscriptionListOut,
    expose_api=True,
    ai=AI(
        description="What each business of the account pays ERPlora: plan, modules, price and next invoice.",
        asks={
            "en": ("how much do I pay per month?", "when's my next invoice?", "what plan is each of my businesses on?"),
            "es": ("¿cuánto pago al mes?", "¿cuándo me cobráis la próxima vez?", "¿qué plan tiene cada negocio?"),
        },
    ),
)
def subscription_list(ctx: OperationContext, data: SubscriptionListIn) -> dict:
    """One row per business of the account that Stripe bills (it owns it or pays it): the plan and modules at
    their net price, the next invoice with VAT (the new plan's, with a downgrade that waits) and what the row's
    buttons do. Filtered
    by business and by status for an integration, which reads it with a ``billing.read`` key."""
    user = _billing_account(ctx)
    owned = set(_owned_hub_ids(user).values_list("hub_id", flat=True))
    subscriptions = (
        Subscription.objects.select_related("hub__billing_profile", "plan")
        .prefetch_related("items")
        .filter(Q(hub_id__in=owned) | Q(hub__billing_profile__owner=user))
        .exclude(stripe_subscription_id="")
        .exclude(status__in=ENDED_SUBSCRIPTIONS)
        .exclude(hub__status=Hub.Status.DELETED)
        .order_by("hub__name", "hub_id")
    )
    if data.hub_id is not None:
        subscriptions = subscriptions.filter(hub_id=data.hub_id)
    if data.status is not None:
        subscriptions = subscriptions.filter(status=data.status)
    total = subscriptions.count()
    page = list(subscriptions[data.offset : data.offset + data.limit])
    unpaid = {}
    for hub_id, invoice_id in (
        Invoice.objects.filter(
            hub_id__in=[s.hub_id for s in page], kind=Invoice.Kind.INVOICE, payment_status=Invoice.PaymentStatus.OPEN
        )
        .order_by("-billed_at")
        .values_list("hub_id", "id")
    ):
        unpaid[hub_id] = invoice_id
    slugs = {item.module_slug for subscription in page for item in subscription.items.all()}
    modules = {module.slug: module for module in Module.objects.filter(slug__in=slugs)}
    with translation.override(ctx.language):
        scheduled = {
            change.hub_id: {"plan": change.plan_slug, "interval": change.interval, "starts_at": change.starts_at}
            for change in PlanChangeSchedule.objects.filter(hub_id__in=[s.hub_id for s in page])
        }
        next_plans = Plan.objects.in_bulk({change["plan"] for change in scheduled.values()}, field_name="slug")
        rows = [
            _subscription_row(subscription, user, owned, unpaid, modules, scheduled, next_plans)
            for subscription in page
        ]
    return {"rows": rows, "total": total, "limit": data.limit, "offset": data.offset}


# --- Payment details --------------------------------------------------------------------------------


def card_cache_key(customer_id: str) -> str:
    return f"billing.card.{customer_id}"


def _card_of(customer_id: str, subscription_id: str) -> tuple[dict | None, bool]:
    """The card of a payer, ``(card, unavailable)``: kept ``CARD_CACHE_SECONDS``; Stripe away is
    ``unavailable`` (never cached, never invented)."""
    key = card_cache_key(customer_id)
    kept = cache.get(key)
    if kept is not None:
        return kept.get("card"), False
    try:
        card = stripe_service.payment_card(subscription_id=subscription_id, customer_id=customer_id)
    except (stripe_service.StripeUnavailable, stripe_service.StripeNotConfigured, stripe_service.StripeRefused):
        logger.warning("[BILLING] Stripe did not give the card of customer %s", customer_id)
        return None, True
    cache.set(key, {"card": card}, CARD_CACHE_SECONDS)
    return card, False


@operation(
    "billing.payment_method.get",
    kind="query",
    permission="billing.view",
    input=PaymentMethodIn,
    output=PaymentMethodOut,
    ai=AI(
        description="The card each payer of the account's businesses pays with, and its last failed charge.",
        asks={
            "en": (
                "which card am I paying with?",
                "why did my last payment fail?",
                "what card is on file for the bar?",
            ),
            "es": (
                "¿con qué tarjeta estoy pagando?",
                "¿por qué falló el último cobro?",
                "¿qué tarjeta tiene puesta la peluquería?",
            ),
        },
    ),
)
def payment_method_get(ctx: OperationContext, data: PaymentMethodIn) -> dict:
    """The card of each of the account's payers (one Stripe customer per business's payer), the businesses it
    pays and its last failed charge. Read from Stripe (the subscription's card, else the customer's default),
    kept a few minutes; changing it is Stripe's Customer Portal (``billing.portal.open``)."""
    user = _billing_account(ctx)
    hubs = (
        Hub.objects.select_related("billing_profile", "subscription")
        .filter(billing_profile__owner=user)
        .exclude(billing_profile__stripe_customer_id="")
        .exclude(status=Hub.Status.DELETED)
        .order_by("name", "id")
    )
    if data.hub_id is not None:
        hubs = hubs.filter(pk=data.hub_id)
    customers: dict[str, list[Hub]] = {}
    for hub in hubs:
        customers.setdefault(hub.billing_profile.stripe_customer_id, []).append(hub)
    methods = []
    for customer, businesses in customers.items():
        billed = [
            hub
            for hub in businesses
            if getattr(hub, "subscription", None) is not None
            and hub.subscription.stripe_subscription_id
            and hub.subscription.status not in ENDED_SUBSCRIPTIONS
        ]
        paying = billed[0].subscription.stripe_subscription_id if billed else ""
        card, unavailable = _card_of(customer, paying)
        failure = (
            PaymentFailure.objects.select_related("hub")
            .filter(hub__in=businesses, resolved_at__isnull=True)
            .order_by("-failed_at")
            .first()
        )
        methods.append(
            {
                # The card pays the businesses Stripe bills; a Free one on the same payer is not paid with it.
                # With none billed, the ones it is kept for.
                "businesses": [{"id": hub.id, "name": hub.name} for hub in billed or businesses],
                "card": card,
                "unavailable": unavailable,
                "last_failure": {"at": failure.failed_at, "business": failure.hub.name} if failure else None,
            }
        )
    return {"methods": methods}


# --- What cancelling the plan will do -----------------------------------------------------------------


def _cancellable(ctx: OperationContext, hub_id) -> tuple[Hub, Subscription]:
    """The business ``hub_id`` whose plan its account may cancel, and its subscription: what ``billing.plan.cancel``
    refuses, refused alike (``services._owned`` and its «nothing to cancel»), so the preview of a cancel that cannot be
    done reaches the model as the refusal, never as a card. Read without locking: nothing is written."""
    user = hub_queries.account_of(ctx)
    member = hub_queries.access(user, hub_id, HubMember.Role.OWNER)
    if not hub_queries.is_writable(member.hub):
        raise hub_services.business_deleted()
    hub = Hub.objects.select_related("billing_profile").get(pk=member.hub_id)
    subscription = Subscription.objects.select_related("plan", "trial_plan").filter(hub=hub).first()
    profile = hub.billing_profile
    if profile is None or profile.owner_id != user.pk:
        raise Conflict(
            _("Say who pays for this business first: its billing details are another account's."),
            code="billing.payer_required",
        )
    paying = (
        subscription is not None
        and bool(subscription.stripe_subscription_id)
        and subscription.status not in hub_queries.ENDED_STATUSES
    )
    if paying and subscription.stripe_customer_id != profile.stripe_customer_id:
        raise Conflict(
            _("This business's plan is still paid with its previous owner's card: keep it with yours in Billing first."),
            code="billing.payer_required",
        )
    if not paying:
        raise Conflict(_("This business is on Free: there is nothing to cancel."), code="billing.nothing_to_cancel")
    return hub, subscription


@operation(
    "billing.plan.cancel_preview",
    kind="query",
    permission="billing.pay",
    input=HubIn,
    output=PlanCancelPreviewOut,
    ai=INTERNAL,  # preview
)
def plan_cancel_preview(ctx: OperationContext, params: HubIn) -> dict:
    """What cancelling the plan of a business will do, as Billing's «Cancel the plan» dialog says it:
    it stays on its plan until the last day of its period (the business's own day), then moves to Free and is not
    charged again; the modules it has turn off that day; what Free covers against the people it has now; an unpaid
    invoice stays owed. ``billing.plan.cancel`` shows it on its card from the panel's assistant (its
    ``preview``). Only the owner who pays reads it, as only they cancel; never asks Stripe."""
    hub, subscription = _cancellable(ctx, params.hub_id)
    now = timezone.now()
    language = ctx.language or settings.LANGUAGE_CODE
    with translation.override(language):
        live_slugs = sorted(item.module_slug for item in subscription.items.all() if item.is_live(now))
        cards = app_queries.cards_of(live_slugs, language)
        names = sorted(cards[slug]["name"] if slug in cards else slug for slug in live_slugs)
        free = hub_queries.free_plan()
        owed = (
            Invoice.objects.filter(
                hub=hub, kind=Invoice.Kind.INVOICE, payment_status=Invoice.PaymentStatus.OPEN
            )
            .order_by("-billed_at")
            .first()
        )
        period_end = subscription.current_period_end
        return {
            "hub_id": hub.id,
            "plan": subscription.plan.translated("name", language),
            "paid_until": timezone.localtime(period_end, ZoneInfo(hub.timezone)).date() if period_end else None,
            "then": free.translated("name", language) if free is not None else "",
            "modules": get_text_list(names, _("and")),
            "free_users": (free.max_users or None) if free is not None else None,
            "free_devices": (free.max_devices or None) if free is not None else None,
            "people": hub_queries.seats_of(hub, now)["used"],
            "unpaid_cents": owed.total_cents if owed is not None else None,
            "currency": owed.currency if owed is not None else "EUR",
        }
