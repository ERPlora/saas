"""The schemas of the Store (``billing.store.catalog``): the modules on sale and what the chosen business has."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema

from billing.schemas.common import Interval
from billing.schemas.subscription_changes import ScheduledChangeOut
from hubs.schemas.plan_catalog import PlanOut


class StoreCatalogIn(Schema):
    """The business the Store sells to (only its owner buys for it)."""

    hub_id: UUID


class StoreModuleOut(Schema):
    """A paid module on sale, or one the chosen business still has (``apps.Module``: only commercial; the Store
    joins it by ``slug`` with ``apps.app.list``, and its own ``name``/``summary``/``icon_svg`` paint a module
    whose app the catalog no longer lists), and what the chosen business has of it."""

    slug: str
    tier: str
    #: Net prices in euro cents, VAT excluded; ``price_annual_cents`` 0 = no annual option.
    price_monthly_cents: int
    price_annual_cents: int
    #: The business has it now: bought, or included in its plan (a cancelled one until it ends).
    owned: bool
    #: ``plan`` (included in it) or ``purchase``; ``None`` when it does not have it.
    source: Literal["plan", "purchase"] | None
    #: Cancelled: it works until then (``billing.module.keep`` undoes it, charging nothing now).
    valid_until: datetime | None
    #: Sold to new buyers. A module off sale is only listed to the business that still has it,
    #: which may cancel it but neither buy nor keep it again.
    on_sale: bool
    #: The catalog's name, summary and icon of its app in the person's language (``apps.App``, listed or
    #: not: a retired app's module is still had); the slug, nothing and the fallback icon without its app.
    name: str
    summary: str
    icon_svg: str


class StoreSubscriptionOut(Schema):
    """The plan of the business as the Store needs it to say what each button does."""

    plan: str
    billing_interval: Interval
    status: str
    #: Stripe bills the business already: a change is confirmed with its proration
    #: (``billing.checkout.confirm``, ``billing.plan.change``); otherwise it pays in the Embedded Checkout.
    paying: bool
    cancel_at_period_end: bool
    current_period_end: datetime | None
    #: The plan the business tries while ``trial_end`` lasts (every sign-up tries Starter).
    trial_plan: str | None
    trial_end: datetime | None
    #: A downgrade waiting for the end of the period: the card of the current plan offers to keep it.
    scheduled_change: ScheduledChangeOut | None = None


class StoreCatalogOut(Schema):
    hub_id: UUID
    #: ``None`` for a business without a plan yet.
    subscription: StoreSubscriptionOut | None
    modules: list[StoreModuleOut]
    #: The paid plans the business may move to (slugs, in display order): the ones sold at sign-up while Stripe
    #: does not bill it; the ``upgrade_only`` ones too once it pays (``billing.queries.offered_plans``).
    offered_plans: list[str]
    #: The billings each offered plan is sold with: the ones it has a Stripe price for. A billing without one
    #: is refused at checkout (``billing.not_on_sale``), so the Store says so instead of selling it.
    sold_intervals: dict[str, list[Interval]]
    #: The internal plans the business is offered, and the one it has: ``hubs.plan.list`` lists only the public ones.
    internal_plans: list[PlanOut]
