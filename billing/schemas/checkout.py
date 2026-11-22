"""The schemas of buying a plan or a module: the Embedded Checkout or the prorated charge of a business that pays
already (``billing.checkout.start``, ``billing.checkout.confirm``)."""

from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator

from billing.schemas.common import Interval, ModuleSlug


class CheckoutStartIn(Schema):
    """What the owner buys for a business: a plan (with its billing) OR a module, one at a time."""

    hub_id: UUID
    plan: str | None = Field(None, max_length=50, description="The plan's slug (starter, standard…).")
    interval: Interval = Field("month", description="The billing of a plan; a module follows the business's.")
    module: ModuleSlug | None = None
    promo_code: str = Field("", max_length=64, description="Trial days instead of the plan's (a plan only).")

    @model_validator(mode="after")
    def _one_thing(self):
        if (self.plan is None) == (self.module is None):
            raise ValueError("Buy a plan or a module, one at a time.")
        return self


class ChargePreviewOut(Schema):
    """What confirming charges NOW (the prorated invoice Stripe would issue), in cents."""

    amount_due_cents: int
    tax_cents: int
    currency: str
    #: The instant the proration was computed for: the confirmation sends it back, so the charge is the
    #: preview's to the cent.
    proration_date: int
    #: While a trial lasts nothing is charged: when it starts charging (unix seconds), else ``None``.
    charge_starts_at: int | None = None


class CheckoutStartOut(Schema):
    """``checkout``: open the Embedded Checkout with ``client_secret`` (a business without a Stripe
    subscription). ``confirm``: show ``preview`` and confirm with ``billing.checkout.confirm`` (a module)
    or ``billing.plan.change`` (a plan)."""

    flow: Literal["checkout", "confirm"]
    session_id: str | None
    client_secret: str | None
    publishable_key: str | None
    preview: ChargePreviewOut | None


class CheckoutConfirmIn(Schema):
    """Add a module to the subscription of a business that pays already, at the previewed proration."""

    hub_id: UUID
    module: ModuleSlug
    proration_date: int = Field(ge=0)
