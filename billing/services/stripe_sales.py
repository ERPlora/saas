"""What a business buys in Stripe: who may buy it (its owner, who is its payer), the plan or module sold at its net
price and the tax rates that charge it, the statuses of a Stripe subscription and its live items."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload

from apps.models import Module
from billing import queries, stripe_service, vat, vat_breakdown
from billing.money import to_cents
from billing.queries.catalog import plan_price_id
from billing.services import payment_gates, sale_tax
from billing.stripe_tax_rates import tax_rate_specs_for
from hubs.queries import access_control
from hubs.services import refusals
from hubs.models import Hub, HubMember, Plan, Subscription, SubscriptionItem

logger = logging.getLogger("billing.services")


#: A simplified invoice is allowed up to 400 € with VAT (RD 1619/2012, art. 4.1); above it the invoice
#: names the buyer, so the sale needs the payer's tax id first.
SIMPLIFIED_INVOICE_LIMIT = Decimal("400.00")
PAID_STATUSES = frozenset({"active", "trialing"})
DUNNING_STATUSES = frozenset({"past_due", "unpaid"})
ENDED_STATUSES = frozenset({"canceled", "incomplete_expired"})
#: Stripe failure codes that mean the CARD will not pay again as it is (the bank refused it, or it is no
#: longer valid): «Pay» waits until the card changes.
CARD_REFUSED_CODES = frozenset(
    {
        "card_declined",
        "expired_card",
        "incorrect_cvc",
        "incorrect_number",
        "invalid_cvc",
        "invalid_expiry_month",
        "invalid_expiry_year",
        "invalid_number",
        "card_not_supported",
    }
)


@dataclass(frozen=True)
class Sale:
    """What is sold, at which Stripe price and net amount, and as which tax category."""

    kind: str  # "plan" | "module"
    slug: str
    interval: str
    price_id: str
    net: Decimal
    category_key: str
    plan: Plan | None = None
    module: Module | None = None


def _owned(ctx: OperationContext, hub_id) -> tuple[Hub, Subscription | None]:
    """The business ``hub_id`` if the account OWNS it (what a business pays is its owner's:
    404 without access, 403 for another role), locked, and its subscription; a deleted one buys nothing.

    And the account is its PAYER: an accepted transfer leaves the previous owner's payer, card
    and Stripe customer on the business, and a new owner must not charge, read or cancel them (409
    ``billing.payer_required``): they say who pays first (``hubs.billing_profile.update`` gives the business
    a payer of theirs). A subscription still billed to the previous payer's customer is kept with the new owner's
    card first («Keep it with my card», ``billing.plan.take_over``)."""
    user = access_control.account_of(ctx)
    member = access_control.access(user, hub_id, HubMember.Role.OWNER, lock=True)
    refusals.refuse_to_change(member.hub)
    hub = Hub.objects.select_related("billing_profile").get(pk=member.hub_id)
    subscription = (
        Subscription.objects.select_related("plan", "trial_plan")
        .filter(hub=hub)
        .first()
    )
    profile = hub.billing_profile
    if profile is None or profile.owner_id != user.pk:
        raise Conflict(
            _(
                "Say who pays for this business first: its billing details are another account's."
            ),
            code="billing.payer_required",
        )
    billed_to = subscription.stripe_customer_id if _paying(subscription) else ""
    if billed_to and billed_to != profile.stripe_customer_id:
        logger.warning(
            "[BILLING] Hub %s is billed to customer %s, not to its payer's (%s)",
            hub.id,
            billed_to,
            profile.stripe_customer_id or "none",
        )
        raise Conflict(
            _(
                "This business's plan is still paid with its previous owner's card: keep it with yours in Billing first."
            ),
            code="billing.payer_required",
        )
    return hub, subscription


def _paying(subscription: Subscription | None) -> bool:
    return (
        bool(subscription and subscription.stripe_subscription_id)
        and subscription.status not in ENDED_STATUSES
    )


def _require_paid_up(hub: Hub, subscription: Subscription | None) -> None:
    """A business with an unpaid invoice buys nothing more until it pays it."""
    unpaid = subscription is not None and subscription.status in DUNNING_STATUSES
    if unpaid or hub.status == Hub.Status.SUSPENDED:
        raise Conflict(
            _(
                "This business has an unpaid invoice: pay it before buying or changing anything."
            ),
            code="billing.invoice_unpaid",
        )


def _not_on_sale(what: str) -> Conflict:
    logger.error(
        "[BILLING] %s has no Stripe price for this billing: it cannot be sold", what
    )
    return Conflict(
        _("This cannot be bought right now. Contact support."),
        code="billing.not_on_sale",
    )


def _upgrade_only() -> Conflict:
    """Pro, Enterprise and Max (``upgrade_only``) are an upgrade of a business that already pays;
    the Store does not offer them to a Free one (``billing.store.catalog``'s ``offered_plans``)."""
    return Conflict(
        _(
            "This plan is an upgrade of a paid plan: start with one of the plans sold at sign-up."
        ),
        code="billing.plan_upgrade_only",
    )


def _plan_net(plan: Plan, interval: str) -> Decimal:
    return Decimal((plan.price_annual if interval == "year" else plan.price_monthly) or 0)


def _module_net(module: Module, interval: str) -> Decimal:
    return Decimal(module.price_annual_cents if interval == "year" else module.price_monthly_cents) / 100


def plan_sale(hub: Hub | None, slug: str, interval: str) -> Sale:
    """The plan ``slug`` as ``hub`` buys it; without a business, as any business nobody marked."""
    plan = queries.plan_on_sale(slug, hub)
    if plan is None:
        reason = _("There is no plan with this identifier.")
        raise InvalidPayload(reason, fields={"plan": reason})
    if not to_cents(plan.price_monthly or 0):
        raise Conflict(
            _(
                "Free is not bought: to go back to it, cancel the plan and it ends with its period."
            ),
            code="billing.plan_is_free",
        )
    price_id = plan_price_id(plan, interval)
    if not price_id:
        raise _not_on_sale(f"Plan {plan.slug} ({interval})")
    return Sale(
        "plan",
        plan.slug,
        interval,
        price_id,
        _plan_net(plan, interval),
        vat.SAAS_SUBSCRIPTION_CATEGORY,
        plan=plan,
    )


def module_sale(slug: str, interval: str, *, module: Module | None = None) -> Sale:
    module = module or queries.module_on_sale(slug)
    if module is None:
        reason = _("There is no module with this identifier on sale.")
        raise InvalidPayload(reason, fields={"module": reason})
    price_id = (
        module.stripe_price_id_annual
        if interval == "year"
        else module.stripe_price_id_monthly
    )
    if not price_id:
        raise _not_on_sale(f"Module {module.slug} ({interval})")
    return Sale(
        "module",
        module.slug,
        interval,
        price_id,
        _module_net(module, interval),
        vat.SOFTWARE_LICENSE_CATEGORY,
        module=module,
    )


def _owns_module(subscription: Subscription | None, slug: str) -> bool:
    if subscription is None:
        return False
    item = SubscriptionItem.objects.filter(
        subscription=subscription, module_slug=slug
    ).first()
    return item is not None and item.is_live(timezone.now())


def _require_module_not_owned(subscription: Subscription | None, slug: str) -> None:
    if _owns_module(subscription, slug):
        raise Conflict(
            _("This business already has this module."), code="billing.module_owned"
        )


def _renewing_modules_net(subscription: Subscription, interval: str) -> Decimal:
    """The modules the business bought, at ``interval``'s prices: one cancelled, or that left the catalogue, is not
    charged again."""
    renewing = SubscriptionItem.objects.filter(
        subscription=subscription, source=SubscriptionItem.Source.PURCHASE, valid_until__isnull=True
    )
    modules = Module.objects.filter(slug__in=renewing.values("module_slug"))
    return sum((_module_net(module, interval) for module in modules), Decimal("0"))


def _recurring_net(
    subscription: Subscription | None,
    interval: str,
    *,
    plan: Plan | None = None,
    adding: Sale | None = None,
) -> Decimal:
    """What a renewal of the business charges, net, once ``adding`` is in: the plan and its bought modules,
    at ``interval``'s prices (the full invoice decides on the whole renewal, not one line of it)."""
    if plan is None and _paying(subscription):
        plan = subscription.plan
    total = _plan_net(plan, interval) if plan is not None else Decimal("0")
    if subscription is not None:
        total += _renewing_modules_net(subscription, interval)
    if adding is not None and adding.kind == "module":
        total += adding.net
    return total


def price_sale(hub: Hub, sale: Sale, *, recurring_net: Decimal, renewing: bool = False) -> list[str]:
    """The Stripe ``TaxRate`` ids that charge OUR tax on ``sale``, after the guards that refuse it: no
    location (409 ``billing.billing_location_required``), a payer ERPlora does not sell to (unless ``renewing``),
    a UK consumer, a territory without a rule, and a renewal over the simplified-invoice limit without the payer's
    tax id (409 ``billing.tax_id_required``)."""
    quote = sale_tax.sale_quote(
        hub, category_key=sale.category_key, price=sale.net, what=sale.kind, renewing=renewing
    )
    rate = Decimal(quote.rate or 0) if quote.is_subject else Decimal("0")
    gross = vat_breakdown.add_vat(recurring_net, rate) if rate else recurring_net
    profile = hub.billing_profile
    if gross > SIMPLIFIED_INVOICE_LIMIT and not (profile.tax_id or "").strip():
        logger.info(
            "[BILLING] %s of hub %s needs the payer's tax id: %s € with VAT",
            sale.kind,
            hub.id,
            gross,
        )
        raise Conflict(
            _(
                "Above 400 € with VAT the invoice must name the buyer: add the payer's tax ID before paying."
            ),
            code="billing.tax_id_required",
        )
    with payment_gates.stripe_errors():
        return stripe_service.tax_rate_ids(tax_rate_specs_for(quote))


def _live(subscription: Subscription) -> dict:
    with payment_gates.stripe_errors():
        return stripe_service.retrieve_subscription(subscription.stripe_subscription_id)


def _live_items(live: dict) -> list[dict]:
    return list(((live.get("items") or {}).get("data")) or [])


def _plan_item(live: dict) -> dict | None:
    for item in _live_items(live):
        if queries.plan_for_price(item["price"]["id"]) is not None:
            return item
    return None


#: Stripe's cap of items per subscription (the plan and 19 modules).
MAX_ITEMS = 20


def _require_room(live: dict, adding: int = 1) -> None:
    if len(_live_items(live)) + adding > MAX_ITEMS:
        raise Conflict(
            _(
                "This business has as many modules as one subscription can bill. Contact support."
            ),
            code="billing.too_many_items",
        )


def _item_sale(subscription: Subscription, line: dict) -> Sale | None:
    """What an item of the live subscription sells (its plan or its module, at its interval), or ``None`` for
    a price no plan nor module has."""
    price_id = (line.get("price") or {}).get("id", "")
    found = queries.plan_for_price(price_id)
    if found is not None:
        plan, interval = found
        return Sale(
            "plan",
            plan.slug,
            interval,
            price_id,
            _plan_net(plan, interval),
            vat.SAAS_SUBSCRIPTION_CATEGORY,
            plan=plan,
        )
    found = queries.module_for_price(price_id)
    if found is not None:
        module, interval = found
        return Sale(
            "module",
            module.slug,
            interval,
            price_id,
            _module_net(module, interval),
            vat.SOFTWARE_LICENSE_CATEGORY,
            module=module,
        )
    logger.warning(
        "[BILLING] Item %s of %s bills price %s, which no plan nor module has: its rate is left alone",
        line.get("id"),
        subscription.stripe_subscription_id,
        price_id,
    )
    return None
