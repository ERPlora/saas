"""Schemas of the hubs operations: the public taxonomy (PLAN §21.4) and plans, and the businesses of
an account with their members, invitations, ownership and payer (plan 2026-10-13, lot L1-A)."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils.translation import gettext as _
from ninja import Field, Schema
from pydantic import AfterValidator, StringConstraints, model_validator

from accounts.queries import local_path


class SectorListIn(Schema):
    pass


class SectorOut(Schema):
    """A sector in the caller's language."""

    code: str
    name: str
    description: str
    icon: str
    color: str
    #: When the row last changed (the public sitemap's ``lastmod``).
    updated_at: datetime


class SectorListOut(Schema):
    sectors: list[SectorOut]


class BusinessTypeListIn(Schema):
    #: Only the business types of the sector with this code.
    sector: str | None = None


class SectorRefOut(Schema):
    code: str
    name: str


class BusinessTypeOut(Schema):
    """A business type in the caller's language, with its sector and its vertical ("" for none)."""

    code: str
    name: str
    description: str
    icon: str
    color: str
    sector: SectorRefOut | None
    vertical: str
    #: When the row last changed (the public sitemap's ``lastmod``).
    updated_at: datetime


class BusinessTypeListOut(Schema):
    business_types: list[BusinessTypeOut]


# --- Plans on sale --------------------------------------------------------------------------------


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
    upgrade_only: bool
    internal_only: bool


class PlanListOut(Schema):
    #: The longest trial a sign-up gets on a plan on sale (0 = none).
    signup_trial_days: int
    #: The cheapest plan a visitor can sign up for (never an upgrade-only one).
    cheapest_slug: str | None
    plans: list[PlanOut]


# --- Businesses of an account ---------------------------------------------------------------------

T = TypeVar("T")

#: The markets ERPlora serves (the EU-27, as the old ``CountryCompliance`` catalog).
COUNTRIES = frozenset(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()
)
#: The roles an invitation or a role change may hand out: never the owner (it only moves by a transfer).
InvitableRole = Literal["hub_admin", "hub_manager", "hub_employee"]
Role = Literal["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _country(value: str) -> str:
    code = value.strip().upper()
    if code not in COUNTRIES:
        raise ValueError(_("Choose one of the countries ERPlora serves."))
    return code


def _email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError(_("Enter a valid email address."))
    return email


def _local_path(value: str) -> str:
    """A path on the hub (``/…``), never another host: the rule of ``accounts.queries.local_path``, which
    turns anything else into ``/``; an input refuses it instead (422)."""
    if local_path(value) != value:
        raise ValueError(_("Enter a path of the business, starting with /."))
    return value


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(_("Choose a valid time zone.")) from None
    return value


Country = Annotated[str, AfterValidator(_country)]
Email = Annotated[str, AfterValidator(_email)]
LocalPath = Annotated[str, Field(max_length=500), AfterValidator(_local_path)]
TimeZone = Annotated[str, Field(max_length=64), AfterValidator(_timezone)]


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int
    limit: int
    offset: int


class ByIdIn(Schema):
    id: UUID


class HubRefOut(Schema):
    id: UUID
    slug: str
    name: str


class PlanRefOut(Schema):
    slug: str
    name: str


#: Why a renewal is not paid (``hubs.Subscription.UnpaidReason``).
UnpaidReason = Literal["card_declined", "card_changed", "authentication_required", "payment_failed"]


class BusinessListIn(PageIn):
    search: str | None = Field(None, max_length=120)


class BusinessRowCanOut(Schema):
    """What the row's buttons do for this account, computed by the server (the page never deduces it from
    the role): ``open`` (it serves now), ``manage`` (owner and administrators, not deleted), ``restore``
    (the owner, deleted and within its 90 days) and ``delete`` (the owner, not deleted)."""

    open: bool
    manage: bool
    restore: bool
    delete: bool


class BusinessRowOut(Schema):
    """A business the account belongs to, as the Businesses page and the launcher list it."""

    id: UUID
    slug: str
    name: str
    host: str
    status: str
    status_label: str
    plan: PlanRefOut | None
    role: Role
    role_label: str
    last_opened_at: datetime | None
    #: Whether "Open" works now; else why not (``preparing``, ``error``, ``suspended``, ``deleting``).
    can_open: bool
    open_blocked_reason: str | None
    #: The Hub's last refusal of this business (its error code), until a call succeeds; else None.
    hub_error: str | None
    deletion_requested_at: datetime | None
    purge_after: datetime | None
    created_at: datetime
    can: BusinessRowCanOut
    #: Why a renewal is not paid (``card_declined``: «Pay» waits for another card; ``card_changed``,
    #: ``authentication_required``, ``payment_failed``: «Pay» works); None while it is paid.
    unpaid_reason: UnpaidReason | None
    #: When the unpaid invoice was issued: the 7 days of grace count from it.
    unpaid_since: datetime | None
    #: Stripe's page to pay that invoice: only for the owner (billing is the owner's, round 17 §2.7).
    pay_url: str | None
    #: The account owns the business's payer (``billing_profile``): it pays for it, whatever its role.
    is_payer: bool
    #: That payer (its Stripe customer), only to whoever owns it: the Store warns about a declined card only for
    #: the businesses it pays too (audit 2 R-21).
    payer_id: UUID | None


class InvitationOut(Schema):
    """An invitation waiting for this account's answer."""

    id: UUID
    hub: HubRefOut
    role: Role
    role_label: str
    invited_by: str | None
    invited_at: datetime | None
    expires_at: datetime | None
    message: str


class OwnershipOfferOut(Schema):
    """A business offered to this account (an ownership transfer waiting for its answer)."""

    id: UUID
    hub: HubRefOut
    from_email: str
    expires_at: datetime


class BusinessListOut(Page[BusinessRowOut]):
    invitations: list[InvitationOut]
    ownership_offers: list[OwnershipOfferOut]
    #: The account's Free business when its Free ones fill the quota (ADR-0154): a new business cannot be Free, so
    #: «Create business» says so before the form, naming it (audit 2 S-02).
    free_business: HubRefOut | None


class BusinessTypeRefOut(Schema):
    code: str
    name: str


class SeatsOut(Schema):
    """People on the business (members and live invitations) and what its plan covers (saas#2022)."""

    used: int
    #: ``None`` = unlimited (every paid plan, the Starter trial, no subscription).
    limit: int | None


class TransferRefOut(Schema):
    id: UUID
    to_email: str
    expires_at: datetime


class BusinessCanOut(Schema):
    """What the account may do on the business, by its role and the business's status (round 17 §2.7).
    ``open``, ``manage``, ``restore`` and ``delete`` mean what they mean on its row (``BusinessRowCanOut``);
    a deleted business takes no change (every write answers 409) until it is recovered."""

    open: bool
    manage: bool
    manage_members: bool
    manage_settings: bool
    manage_billing: bool
    transfer: bool
    restore: bool
    delete: bool


# The usage of a business (lot L4-A, PLAN-SAAS §5): the page carries the last day; ``hubs.usage.*`` below.


class StorageUsageOut(Schema):
    """What the business's files take (``used_bytes``, S3) against the space its plan includes
    (``limit_bytes``; ``None`` without a plan), and how full it is, rounded (``percent``, over 100 past it)."""

    used_bytes: int
    limit_bytes: int | None
    percent: int | None


class ActiveUsersOut(Schema):
    """The people active on the day measured (``on_day``) and in the 30 days up to it."""

    on_day: int
    last_30_days: int


class UsageOut(Schema):
    """The last day the Hub measured of a business; ``stale`` when it is not yesterday's (UTC)."""

    day: date
    storage: StorageUsageOut
    active_users: ActiveUsersOut
    stale: bool


class BusinessDetailOut(Schema):
    id: UUID
    slug: str
    name: str
    host: str
    country: str
    #: The country no longer changes: the business is ready, and may invoice (``hubs.country_locked``).
    country_locked: bool
    timezone: str
    language: str
    business_type: BusinessTypeRefOut | None
    status: str
    status_label: str
    hub_error: str | None
    ready_at: datetime | None
    created_at: datetime
    deletion_requested_at: datetime | None
    purge_after: datetime | None
    role: Role
    role_label: str
    plan: PlanRefOut | None
    trial_plan: PlanRefOut | None
    trial_end: datetime | None
    seats: SeatsOut
    pending_transfer: TransferRefOut | None
    can: BusinessCanOut
    #: As in ``BusinessRowOut``.
    unpaid_reason: UnpaidReason | None
    unpaid_since: datetime | None
    pay_url: str | None
    is_payer: bool
    #: The last day the Hub measured (``hubs.usage.get``); ``None`` until the first night (lot L4-A).
    usage: UsageOut | None


class AddressProposeIn(Schema):
    name: Name


class AddressProposeOut(Schema):
    """A free address for a business called ``name`` (it may still be taken before the sign-up)."""

    slug: str
    host: str


class BusinessCreateIn(Schema):
    """The minimal sign-up (round 17 §2.3): a name, a country, and a business type if the person knows."""

    name: Name
    country: Country
    business_type: str | None = Field(None, max_length=80)
    #: The address; proposed from the name when not given.
    slug: str | None = Field(None, max_length=63)


class BusinessUpdateIn(Schema):
    """Only the fields sent change; ``null`` leaves a field as it is."""

    id: UUID
    name: Name | None = None
    #: Read-only once the business is ready (``country_locked``): a change is the 409 ``hubs.country_locked``.
    country: Country | None = Field(
        None, description="ISO 3166-1 alpha-2. Read-only once the business is ready: 409 hubs.country_locked."
    )
    language: Literal["en", "es"] | None = None
    timezone: TimeZone | None = None


class BusinessDeleteIn(Schema):
    id: UUID
    #: The business's name, typed again: deleting is not one click away.
    confirm_name: str = Field(max_length=120)


class BusinessOpenIn(Schema):
    id: UUID
    next: LocalPath = "/"


class BusinessOpenOut(Schema):
    """Where «Open» goes: the Hub's start (``/auth/login?next=``), which bounces to ``/hub-login/`` with a
    ``state`` bound to the browser; that door mints the code. The SPA navigates to ``url``."""

    url: str


class MarkReadyIn(Schema):
    id: UUID


class HubErrorIn(Schema):
    """The Hub's refusal of a call about the business (its error code), or ``None`` once a call succeeds."""

    id: UUID
    hub_error: str | None = Field(None, max_length=64)


class HubStatusOut(Schema):
    id: UUID
    status: str
    ready_at: datetime | None


#: The label of a paid app (``modules[].id`` of the snapshot, PLAN §20.2).
ModuleSlug = Annotated[str, Field(max_length=63, pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")]
SubscriptionStatus = Literal[
    "active", "trialing", "past_due", "unpaid", "canceled", "incomplete", "incomplete_expired", "paused"
]


class ModuleRightIn(Schema):
    """A module Stripe bills the business for (``source = purchase``): open-ended, or until ``valid_until``
    (cancelled at the end of its period, PLAN-SAAS §3.3)."""

    module_slug: ModuleSlug
    stripe_item_id: str = Field("", max_length=255)
    valid_until: datetime | None = None


class SubscriptionApplyIn(Schema):
    """What the LIVE Stripe subscription says of a business (billing, lot L2-B), applied as it comes. A field
    left out is left as it is; one sent as ``None`` is cleared.

    ``modules`` replaces the bought modules (the ones the plan includes are not Stripe's). ``standing``
    moves the business: ``good`` (paid), ``grace`` (a renewal failed, inside the 7 days: «payment
    pending») or ``suspended``.
    """

    hub_id: UUID
    plan: str | None = Field(None, max_length=50)
    billing_interval: Literal["month", "year"] | None = None
    status: SubscriptionStatus | None = None
    stripe_customer_id: str | None = Field(None, max_length=255)
    stripe_subscription_id: str | None = Field(None, max_length=255)
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool | None = None
    trial_start: datetime | None = None
    trial_end: datetime | None = None
    modules: list[ModuleRightIn] | None = None
    standing: Literal["good", "grace", "suspended"] | None = None
    unpaid_reason: UnpaidReason | None = None
    unpaid_since: datetime | None = None
    unpaid_invoice_url: str | None = Field(None, max_length=2048)
    #: Cleared once the subscription a deleted business still had ended in Stripe.
    cancel_requested_at: datetime | None = None


class SubscriptionApplyOut(Schema):
    hub_id: UUID
    #: The version of the snapshot after the change (it grows only when what the Hub sees changed).
    state_version: int
    #: Something was written.
    changed: bool


class NotifyPeopleIn(Schema):
    """A change of the people of the business ``id``, told on the context's channel (a system command)."""

    id: UUID
    event: Literal["hubs.member.changed", "hubs.ownership.changed", "hubs.business.usage_collected"]


class NotifyPeopleOut(Schema):
    id: UUID


# --- Members and invitations ----------------------------------------------------------------------


class MemberListIn(PageIn):
    hub_id: UUID


#: What the account may do on a row of the members page.
MemberAction = Literal["change_role", "remove", "resend", "cancel", "transfer"]


class MemberRowOut(Schema):
    id: UUID
    user_id: UUID
    email: str
    name: str
    role: Role
    role_label: str
    #: ``active`` (answered), ``pending`` (invited) or ``expired`` (invited, past its window).
    status: Literal["active", "pending", "expired"]
    status_label: str
    invited_by: str | None
    invited_at: datetime | None
    invitation_expires_at: datetime | None
    #: None while the invitation waits for its answer.
    joined_at: datetime | None
    accepted_at: datetime | None
    last_opened_at: datetime | None
    #: The account's own row.
    is_me: bool
    #: What the account may do on this row, computed by the server, in this order: ``change_role``,
    #: ``remove`` (answered), ``resend`` and ``cancel`` (invitation), ``transfer`` (owner only, while no
    #: offer waits). Empty on one's own row, a peer, a superior and a deleted business.
    actions: list[MemberAction]
    #: The roles the account may give this member (empty without ``change_role``).
    assignable_roles: list[InvitableRole]


class MemberListOut(Page[MemberRowOut]):
    seats: SeatsOut
    #: The roles the account may invite with.
    invitable_roles: list[InvitableRole]


class MemberInviteIn(Schema):
    hub_id: UUID
    email: Email
    role: InvitableRole = "hub_employee"
    message: str = Field("", max_length=500)


class MemberRoleIn(Schema):
    id: UUID
    role: InvitableRole


class RemovedOut(Schema):
    id: UUID


class InvitationListIn(Schema):
    pass


class InvitationListOut(Schema):
    invitations: list[InvitationOut]


# --- Ownership ------------------------------------------------------------------------------------


class OwnershipTransferIn(Schema):
    hub_id: UUID
    #: The member the business is offered to (already on it).
    member_id: UUID


class OwnershipTransferOut(Schema):
    id: UUID
    hub: HubRefOut
    from_email: str
    to_email: str
    status: Literal["pending", "accepted", "declined", "cancelled", "expired"]
    expires_at: datetime
    resolved_at: datetime | None


# --- Payer ----------------------------------------------------------------------------------------


class BillingProfileGetIn(Schema):
    hub_id: UUID


#: A Spanish postal code: five digits, the first two its province, which decides the tax (the Canary
#: Islands, Ceuta and Melilla are outside VAT; «3500» is not Las Palmas, saas#1972).
SPANISH_POSTAL_CODE = re.compile(r"^\d{5}$")


def postal_code_problem(country: str, postal_code: str) -> str | None:
    """Why ``postal_code`` is not one of ``country`` (only Spain's has a shape the tax depends on), or
    ``None``. Empty is fine: the payer may wait for the first checkout, which asks for it."""
    if country == "ES" and postal_code and not SPANISH_POSTAL_CODE.match(postal_code):
        return _("A Spanish postal code has five digits, e.g. 28001.")
    return None


class BillingProfileIn(Schema):
    """Who ERPlora invoices for this business. With ``same_as_business``, its name and country are
    copied from the business (PLAN-SAAS §3.1: a copy, not a sync). The postal code must be one of the
    payer's country (``postal_code_problem``)."""

    hub_id: UUID
    billing_name: str = Field("", max_length=255)
    tax_id: str = Field("", max_length=50)
    billing_address: str = Field("", max_length=500)
    billing_city: str = Field("", max_length=100)
    billing_postal_code: Annotated[str, StringConstraints(strip_whitespace=True)] = Field("", max_length=20)
    billing_country: Country | Literal[""] = ""
    billing_email: Email | Literal[""] = ""
    same_as_business: bool = False


class BillingProfileOut(Schema):
    """The business's payer as its owner edits it. A payer is somebody's: one set up by another account
    (the owner before a transfer) keeps paying, but its data is not shown (``paid_by_another_account``)
    and saving gives the business a payer of the current owner."""

    hub_id: UUID
    paid_by_another_account: bool
    billing_name: str
    tax_id: str
    billing_address: str
    billing_city: str
    billing_postal_code: str
    billing_country: str
    billing_email: str
    same_as_business: bool


# --- Usage (lot L4-A, PLAN-SAAS §5) ----------------------------------------------------------------

#: The largest figures the columns of ``HubUsageDaily`` hold.
MAX_BYTES = 2**63 - 1
MAX_PEOPLE = 2**31 - 1


class UsageGetIn(Schema):
    business_id: UUID


class UsageSeriesIn(Schema):
    business_id: UUID
    #: The window: the days up to yesterday (UTC), from one to a year.
    days: int = Field(30, ge=1, le=365)


class UsagePointOut(Schema):
    """One day of the window (only the days measured: a chart draws the gaps)."""

    day: date
    storage: StorageUsageOut
    active_users: ActiveUsersOut


class UsageSeriesOut(Schema):
    """The days of the window, oldest first, against the space the plan includes today."""

    business_id: UUID
    limit_bytes: int | None
    points: list[UsagePointOut]


class HubUsageIn(Schema):
    """One business's usage on a day, as the Hub sends it (``GET /internal/usage``, ``hubs/README.md``)."""

    id: UUID
    s3_bytes: int = Field(ge=0, le=MAX_BYTES)
    db_bytes: int = Field(ge=0, le=MAX_BYTES)
    active_users_1d: int = Field(ge=0, le=MAX_PEOPLE)
    active_users_30d: int = Field(ge=0, le=MAX_PEOPLE)

    @model_validator(mode="after")
    def _one_day_within_its_thirty(self):
        if self.active_users_1d > self.active_users_30d:
            raise ValueError("active_users_1d is more than active_users_30d, which holds that day")
        return self


class HubUsagePageIn(Schema):
    """One page of ``GET /internal/usage``: each row is read on its own, so a broken one never drops the page."""

    day: date
    hubs: list[dict[str, Any]]
    #: Sent back as it came for the next page; ``None`` on the last.
    next_cursor: str | None = Field(None, min_length=1, max_length=512)


class UsageRecordIn(HubUsageIn):
    """The usage of the business ``id`` on ``day`` (the system command ``hubs.usage.record``)."""

    day: date


class UsageRecordOut(Schema):
    id: UUID
    day: date
    #: The figures were new or different (the owner and the admins were told).
    changed: bool

