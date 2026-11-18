"""Schemas of the plans on sale."""

from decimal import Decimal

from ninja import Schema


class PlanListIn(Schema):
    pass


class PlanOut(Schema):
    """A plan on sale in the caller's language; prices are net (VAT excluded), in euros."""

    slug: str
    name: str
    description: str
    price_monthly: Decimal
    price_annual: Decimal
    #: The plan's features, ending with its trial when a sign-up gets one.
    features: list[str]
    featured_label: str
    #: 0 = unlimited.
    max_users: int
    max_devices: int
    trial_period_days: int
    has_trial: bool
    support_level_label: str
    included_level_label: str
    #: How much room the plan has, relative to the full tier («Basic, for one device», «Double»…).
    resources_label: str
    #: Requests to the AI assistant the plan includes each month (one request = one message); 0 = none.
    assistant_messages_per_month: int
    #: WhatsApp messages the plan includes each month; 0 = none.
    whatsapp_messages_per_month: int
    #: Apps the business may choose to turn on at once, the ones they require aside (the cap the Hub applies);
    #: 0 = no limit.
    max_apps: int
    #: Whether the business's public website may go on a domain of its own (HUBS-F17); never the app.
    includes_custom_domain: bool
    upgrade_only: bool
    internal_only: bool


class PlanListOut(Schema):
    #: The longest trial a sign-up gets on a plan on sale (0 = none).
    signup_trial_days: int
    #: The cheapest plan a visitor can sign up for (never an upgrade-only one).
    cheapest_slug: str | None
    plans: list[PlanOut]
