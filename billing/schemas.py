"""Input and output schemas of billing's operations (OpenAPI, the 422's ``fields``)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import AfterValidator, model_validator

#: The verdict a VAT number gets (``billing.services.clear_tax_id_for_stripe``):
#: ``verified`` (VIES confirmed it, with proof: reverse charge), ``invalid`` (not in VIES),
#: ``unavailable`` (VIES could not answer, or answered without proof), ``national`` (ERPlora's own
#: country: nothing to prove, never reverse charge), ``outside_vies`` (a UK number, HMRC's register).
VatStatus = Literal["verified", "invalid", "unavailable", "national", "outside_vies"]
#: What the preview knows of a VAT number without asking VIES: the statuses above from the log, ``absent``
#: (none typed: a consumer) or ``unchecked`` (nobody asked VIES about it yet: ``billing.vat_check.run``).
PreviewVatStatus = Literal[
    "verified",
    "invalid",
    "unavailable",
    "national",
    "outside_vies",
    "absent",
    "unchecked",
]

CountryCode = Annotated[str, Field(pattern=r"^[A-Za-z]{2}$"), AfterValidator(str.upper)]


class VatCheckIn(Schema):
    """A VAT number to check in VIES; without its country prefix, it is read in ``country``."""

    vat_number: str = Field(
        max_length=40, description="The VAT number, e.g. DE812871812."
    )
    country: CountryCode | Literal[""] = Field(
        "",
        description="ISO 3166-1 alpha-2 of the payer, for a number typed without its prefix.",
    )


class VatCheckOut(Schema):
    """The verdict that will price a sale to this number."""

    vat_number: str
    status: VatStatus
    #: True: in VIES. False: not in VIES. None: nobody could say (VIES down) or nothing to ask.
    valid: bool | None
    #: As VIES has them (empty when the member state does not share them).
    name: str
    address: str
    consultation_number: str
    checked_at: datetime | None
    is_current: bool
    #: The sale goes without VAT (intra-EU B2B): only a current VIES proof or a manual override.
    reverse_charge: bool
    manual_override: bool


class TaxPreviewIn(Schema):
    """Who pays and what: the payer's place, its VAT number (none = a consumer) and the net price."""

    country: CountryCode
    postal_code: str = Field(
        "", max_length=20, description="Decides the Canary Islands, Ceuta and Melilla."
    )
    vat_number: str = Field("", max_length=40)
    net: Decimal = Field(
        Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Net price in euros.",
    )
    category: Literal["plan", "module"] = "plan"


class TaxPreviewOut(Schema):
    """The tax a sale to that payer carries. ``resolvable`` false: no rule for that territory, the sale is
    refused (``treatment``, ``rate``, ``tax`` and ``total`` null)."""

    country: str
    resolvable: bool
    treatment: Literal["domestic", "oss", "reverse_charge", "not_subject"] | None
    tax_country: str
    rate: Decimal | None
    net: Decimal
    tax: Decimal | None
    total: Decimal | None
    #: A VAT number was given: the payer says it is a business.
    b2b: bool
    vat_status: PreviewVatStatus
    reverse_charge: bool


# --- Stripe (lot L2-B) -------------------------------------------------------------------------------


class PromoCheckIn(Schema):
    """A promo code typed in the store, before paying."""

    code: str = Field(max_length=64)


class PromoCheckOut(Schema):
    """Whether the code grants a trial now, and how many days (``0`` when it does not)."""

    code: str
    valid: bool
    trial_days: int


Interval = Literal["month", "year"]
#: The label of an app of the Hub (``apps.Module.slug``).
ModuleSlug = Annotated[str, Field(max_length=63, pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")]


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


class PlanChangeIn(Schema):
    """Move a paying business to another plan or billing, at the previewed proration."""

    hub_id: UUID
    plan: str = Field(max_length=50)
    interval: Interval = "month"
    proration_date: int = Field(ge=0)
    #: Honoured when the business pays modules alone (Free): trial days instead of paying the plan now.
    promo_code: str = Field("", max_length=64)


class HubIn(Schema):
    hub_id: UUID


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
    """A plan change that starts with the next period (a downgrade, review of L3-C)."""

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


class PortalOpenIn(Schema):
    hub_id: UUID


class PortalOpenOut(Schema):
    """Stripe's Customer Portal for the payer of the business (cards, invoices): one use, a few minutes."""

    url: str


# --- The Store (lot L2-D) ----------------------------------------------------------------------------


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
    #: Sold to new buyers. A module off sale is only listed to the business that still has it (saas#2589),
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


class StoreCatalogOut(Schema):
    hub_id: UUID
    #: ``None`` for a business without a plan yet.
    subscription: StoreSubscriptionOut | None
    modules: list[StoreModuleOut]
    #: The paid plans the business may move to (slugs, in display order): the ones sold at sign-up while Stripe
    #: does not bill it; the ``upgrade_only`` ones too once it pays (audit 2 S-03, ``billing.queries.offered_plans``).
    offered_plans: list[str]


# --- ERPlora's invoices, subscriptions and payment details: the Billing section (lot L3-C) ------------

InvoicePaymentStatus = Literal["open", "paid", "void"]
InvoiceFiscalStatus = Literal["", "issuing", "issued", "accepted", "accepted_with_errors", "rejected"]
PlatformStatus = Literal["issuing", "issued", "accepted", "accepted_with_errors", "rejected"]
#: VeriFactu's ``TipoFactura`` of a rectifying invoice (``Invoice.RectificationType`` without its empty value).
InvoiceRectificationType = Literal["R1", "R2", "R3", "R4"]


class InvoiceRecordIn(Schema):
    """Internal (the webhook): a Stripe invoice of a business, to list (``open``), invoice (``paid``) or drop
    (``void``). The VIES clearance of the payer is asked before the business is locked."""

    hub_id: UUID
    invoice: dict[str, Any]
    status: InvoicePaymentStatus
    tax_id_verified: bool = False
    vat_consultation_number: str = ""


class InvoiceRecordOut(Schema):
    id: UUID | None
    number: str
    payment_status: str
    #: ``listed``, ``numbered``, ``duplicate``, ``voided``, ``ignored`` or ``unknown``.
    outcome: str


class CreditNoteRecordIn(Schema):
    """Internal (the webhook): a Stripe credit note of an invoice ERPlora issued."""

    credit_note: dict[str, Any]


class RefundRecordIn(Schema):
    """Internal (the webhook): a Stripe refund made without a credit note, of the invoice ``invoice_id``."""

    invoice_id: UUID
    refund: dict[str, Any]


class FiscalAnswerIn(Schema):
    """Internal: what ERPlora's platform hub answered about an invoice."""

    id: UUID
    status: PlatformStatus
    qr: str = ""
    error_code: str = ""
    error: str = ""


class FiscalAnswerOut(Schema):
    id: UUID
    fiscal_status: str
    changed: bool


class InvoiceFilterIn(Schema):
    """The filters of the invoices of the account: a business, the payment, a year and a number."""

    hub_id: UUID | None = None
    #: ``paid`` or ``open`` (not collected); empty, every one.
    status: InvoicePaymentStatus | None = None
    year: int | None = Field(None, ge=2000, le=2999)
    search: str | None = Field(None, max_length=64, description="Part of the number.")


class InvoiceListIn(InvoiceFilterIn):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class InvoiceBusinessOut(Schema):
    #: ``None`` once the business is gone; its name stays as it was on the invoice.
    id: UUID | None
    name: str


class InvoiceCanOut(Schema):
    """What the row's buttons do for this account, computed by the server: ``pay`` (not collected, and the
    account pays it) and ``pdf`` (issued by the platform hub)."""

    pay: bool
    pdf: bool


class InvoiceRectificationOut(Schema):
    """Why a credit note rectifies: its VeriFactu type and the reason printed on it (empty when Stripe gave
    none)."""

    type: InvoiceRectificationType
    reason: str


class InvoiceRowOut(Schema):
    id: UUID
    kind: Literal["invoice", "credit_note"]
    kind_label: str
    #: ``None`` until it is paid (an unpaid Stripe invoice has no number of ours yet).
    number: str | None
    #: Stripe's number of it: the reference of one not numbered yet.
    reference: str
    date: date
    business: InvoiceBusinessOut
    currency: str
    net_cents: int
    tax_cents: int
    total_cents: int
    payment_status: InvoicePaymentStatus
    payment_status_label: str
    fiscal_status: InvoiceFiscalStatus
    fiscal_status_label: str
    #: Why «Pay» is disabled: the bank declined the card (change it first) or another account pays it.
    pay_blocked_reason: Literal["card_change_required", "payer_required"] | None
    #: The row's actions in order, the fixed one first.
    actions: list[Literal["pay", "pdf"]]
    can: InvoiceCanOut
    #: ``None`` for an invoice; a credit note's type (R1–R4) and reason.
    rectification: InvoiceRectificationOut | None
    #: The Stripe object that made a credit note (``cn_…`` credit note, ``re_…`` refund); empty for an invoice.
    stripe_source_id: str


class InvoiceListOut(Schema):
    rows: list[InvoiceRowOut]
    total: int
    limit: int
    offset: int


class InvoiceByIdIn(Schema):
    id: UUID


class InvoiceLineOut(Schema):
    position: int
    description: str
    item_kind: Literal["plan", "module", "other"]
    item_slug: str
    quantity: int
    proration: bool
    period_start: datetime | None
    period_end: datetime | None
    tax_rate: Decimal
    net_cents: int
    tax_cents: int
    total_cents: int


class InvoiceRecipientOut(Schema):
    name: str
    tax_id: str
    address: str
    city: str
    postal_code: str
    country: str
    email: str


class InvoiceRefOut(Schema):
    id: UUID
    number: str


class InvoiceDetailOut(InvoiceRowOut):
    issued_on: date | None
    paid_at: datetime | None
    tax_treatment: str
    tax_country: str
    tax_rate: Decimal
    recipient: InvoiceRecipientOut
    lines: list[InvoiceLineOut]
    rectifies: InvoiceRefOut | None
    #: The content of the VeriFactu QR, once the platform hub issued it.
    qr: str


class InvoiceFileOut(Schema):
    """A document to download: the route answers it as the file itself."""

    filename: str
    content_type: str
    content: bytes


class InvoicePayIn(Schema):
    id: UUID


class InvoicePayOut(Schema):
    """Stripe's page to pay the invoice (the payer's card, 3-D Secure included)."""

    url: str


class SubscriptionListIn(Schema):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)
    #: One business's subscription (BILLING-G02: the old API's «detail of one»); only among the account's.
    hub_id: UUID | None = None
    #: Stripe's status of the subscription (an ended one is never a row).
    status: Literal["active", "trialing", "past_due", "unpaid", "incomplete", "paused"] | None = None


class SubscriptionPlanOut(Schema):
    slug: str
    name: str
    interval: Interval
    #: Net, as the plan is sold («29,99 €/mes + IVA»).
    price_cents: int


class SubscriptionModuleRowOut(Schema):
    slug: str
    interval: Interval
    #: Net; ``None`` for a module no longer on sale.
    price_cents: int | None
    source: Literal["plan", "purchase"]
    #: Cancelled: it works until then.
    valid_until: datetime | None


class NextInvoiceOut(Schema):
    date: datetime | None
    #: With VAT, as the payer's place prices it; ``None`` while that place is unknown.
    total_cents: int | None
    currency: str


class SubscriptionCanOut(Schema):
    change_plan: bool
    cancel_plan: bool
    keep_plan: bool
    #: «Keep it with my card»: the business was handed over and its plan is still on the previous payer's card.
    take_over: bool
    view_invoice: bool
    view_invoices: bool


class SubscriptionRowOut(Schema):
    business: InvoiceBusinessOut
    plan: SubscriptionPlanOut
    modules: list[SubscriptionModuleRowOut]
    #: ``None`` when the plan ends at the end of the period (``cancelling``): no invoice follows.
    next_invoice: NextInvoiceOut | None
    status: str
    status_label: str
    cancelling: bool
    ends_at: datetime | None
    #: The business was deleted and its Stripe subscription is being ended.
    cancel_requested: bool
    #: The open invoice the business owes («View the invoice»), if any.
    unpaid_invoice_id: UUID | None
    #: A downgrade waiting for the end of the period («Starter from 1 Nov»).
    scheduled_change: ScheduledChangeOut | None = None
    #: The plan is charged to the card of another account (the payer before a hand-over, HUBS-F28).
    paid_by_another_account: bool
    actions: list[Literal["take_over", "change_plan", "keep_plan", "view_invoice", "cancel_plan", "view_invoices"]]
    can: SubscriptionCanOut


class SubscriptionListOut(Schema):
    rows: list[SubscriptionRowOut]
    total: int
    limit: int
    offset: int


class PaymentMethodIn(Schema):
    hub_id: UUID | None = None


class CardOut(Schema):
    brand: str
    last4: str
    exp_month: int
    exp_year: int


class LastFailureOut(Schema):
    at: datetime
    business: str


class PaymentMethodRowOut(Schema):
    """The card of one payer (a Stripe customer) and the businesses it pays."""

    businesses: list[InvoiceBusinessOut]
    #: ``None`` when Stripe has no card for it, or did not answer (``unavailable``).
    card: CardOut | None
    unavailable: bool
    last_failure: LastFailureOut | None


class PaymentMethodOut(Schema):
    methods: list[PaymentMethodRowOut]
