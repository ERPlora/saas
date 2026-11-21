"""The schemas of changing the subscription of a business: another plan or billing, a module cancelled or kept,
the plan cancelled, and the subscription as Stripe left it."""

from datetime import date, datetime
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from billing.schemas.common import Interval, ModuleSlug


class PlanChangeIn(Schema):
    """Move a paying business to another plan or billing, at the previewed proration."""

    hub_id: UUID
    plan: str = Field(max_length=50)
    interval: Interval = "month"
    proration_date: int = Field(ge=0)
    #: Honoured when the business pays modules alone (Free): trial days instead of paying the plan now.
    promo_code: str = Field("", max_length=64)


class ModuleIn(Schema):
    hub_id: UUID
    module: ModuleSlug


class SubscriptionModuleOut(Schema):
    slug: str
    #: ``plan`` (included in it) or ``purchase``.
    source: str
    #: Cancelled: the module works until then.
    valid_until: datetime | None


class ScheduledChangeOut(Schema):
    """A plan change that starts with the next period (a downgrade)."""

    plan: str
    interval: Interval
    starts_at: datetime


class SubscriptionOut(Schema):
    """The subscription of a business after the change, as Stripe left it."""

    hub_id: UUID
    plan: str
    billing_interval: Interval
    status: str
    cancel_at_period_end: bool
    current_period_end: datetime | None
    trial_end: datetime | None
    modules: list[SubscriptionModuleOut]
    #: A downgrade waiting for the end of the period («Starter from 1 Nov»).
    scheduled_change: ScheduledChangeOut | None = None


class PlanCancelPreviewOut(Schema):
    """What cancelling the plan of a business will do, before it is confirmed (BILLING-F13, the «Cancel the plan»
    dialog): ``billing.plan.cancel`` shows it on its card from the panel's assistant (ASSISTANT-F25, step 5). The
    titles are what its card calls each datum; what is empty is left off it. Nothing is written, nothing asks Stripe."""

    hub_id: UUID = Field(description="The business whose plan would be cancelled.")
    plan: str = Field(title=gettext_noop("Current plan"), description="The plan it stays on until then, by its name.")
    paid_until: date | None = Field(
        title=gettext_noop("Paid until"),
        description="The last day of its period, the business's own day: then it is not charged again.",
    )
    then: str = Field(title=gettext_noop("Then it moves to"), description="The plan it moves to then: Free, by its name.")
    modules: str = Field(
        title=gettext_noop("Turned off that day"),
        description="The modules it has that turn off with the plan, by their names; empty = none.",
    )
    free_users: int | None = Field(
        title=gettext_noop("People on Free"), description="The people Free covers at a time; none = no limit."
    )
    free_devices: int | None = Field(
        title=gettext_noop("Devices on Free"), description="The devices Free covers at a time; none = no limit."
    )
    people: int = Field(
        title=gettext_noop("People in the business now"),
        description="Its members and live invitations, as Businesses counts its seats.",
    )
    unpaid_cents: int | None = Field(
        title=gettext_noop("Unpaid invoice, still owed"),
        description="What its unpaid invoice owes, in cents: cancelling does not void it; none = nothing owed.",
        json_schema_extra={"money": True},
    )
    currency: str = Field(description="The currency of the unpaid invoice (EUR without one).")
