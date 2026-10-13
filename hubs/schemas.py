"""Schemas of the hubs operations: the public taxonomy (PLAN §21.4) and plans, and the businesses of
an account with their members, invitations, ownership and payer (plan 2026-10-13, lot L1-A)."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils.translation import gettext as _
from ninja import Field, Schema
from pydantic import AfterValidator, StringConstraints


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
    """A path on the hub (``/…``), never another host (``//host``, ``/\\host``, a scheme)."""
    parts = urlsplit(value)
    if not value.startswith("/") or value.startswith(("//", "/\\")) or parts.scheme or parts.netloc:
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


class BusinessListIn(PageIn):
    search: str | None = Field(None, max_length=120)


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


class BusinessTypeRefOut(Schema):
    code: str
    name: str


class SeatsOut(Schema):
    """People on the business (members and live invitations) and the plan's cap (0 = unlimited)."""

    used: int
    cap: int


class TransferRefOut(Schema):
    id: UUID
    to_email: str
    expires_at: datetime


class BusinessCanOut(Schema):
    """What the account may do on the business, by its role (round 17 §2.7)."""

    open: bool
    manage_members: bool
    manage_settings: bool
    manage_billing: bool
    transfer: bool
    delete: bool


class BusinessDetailOut(Schema):
    id: UUID
    slug: str
    name: str
    host: str
    country: str
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
    country: Country | None = None
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
    """The jump into the business: POST ``code`` and ``next`` to ``action`` (OIDC form_post)."""

    action: str
    code: str
    next: str


class MarkReadyIn(Schema):
    id: UUID


class HubStatusOut(Schema):
    id: UUID
    status: str
    ready_at: datetime | None


# --- Members and invitations ----------------------------------------------------------------------


class MemberListIn(PageIn):
    hub_id: UUID


class MemberActionsOut(Schema):
    """The row actions the account may take on this member (none on its own row)."""

    change_role: bool
    remove: bool
    resend: bool
    cancel: bool
    transfer: bool


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
    joined_at: datetime
    accepted_at: datetime | None
    last_opened_at: datetime | None
    is_self: bool
    actions: MemberActionsOut
    #: The roles the account may give this member.
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


class BillingProfileIn(Schema):
    """Who ERPlora invoices for this business. With ``same_as_business``, its name and country are
    copied from the business (PLAN-SAAS §3.1: a copy, not a sync)."""

    hub_id: UUID
    billing_name: str = Field("", max_length=255)
    tax_id: str = Field("", max_length=50)
    billing_address: str = Field("", max_length=500)
    billing_city: str = Field("", max_length=100)
    billing_postal_code: str = Field("", max_length=20)
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
