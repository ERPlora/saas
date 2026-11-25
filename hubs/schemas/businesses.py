"""Schemas of the businesses of an account: the list, a business's page, and what changes, deletes or
opens one."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from hubs.schemas.common import Country, HubRefOut, LocalPath, Name, Page, PageIn, Role, TimeZone
from hubs.schemas.hub_callbacks import HubMaintenanceOut
from hubs.schemas.hub_usage import UsageOut
from hubs.schemas.invitations import InvitationOut
from hubs.schemas.membership import SeatsOut
from hubs.schemas.ownership import OwnershipOfferOut, TransferRefOut
from hubs.schemas.subscriptions import UnpaidReason


class PlanRefOut(Schema):
    """The plan a business has, with what it covers: it may be an internal one, which ``hubs.plan.list`` never
    lists, so a business's page reads its plan here."""

    slug: str
    name: str
    #: 0 is Free (``isFree`` of the Store).
    price_monthly: Decimal
    #: As in ``PlanOut``: 0 = unlimited.
    max_devices: int
    max_apps: int


class BusinessListIn(PageIn):
    search: str | None = Field(None, max_length=120)


class BusinessRowCanOut(Schema):
    """What the row's buttons do for this account, computed by the server (the page never deduces it from
    the role): ``open`` (it serves now), ``manage`` (owner and administrators, not deleted), ``restore``
    (the owner, deleted and within its 90 days) and ``delete`` (the owner, not deleted; never ERPlora's own)."""

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
    #: ERPlora's own business: it has no plan nor payments, and only its people are managed here.
    is_platform: bool
    plan: PlanRefOut | None
    role: Role
    role_label: str
    last_opened_at: datetime | None
    #: Whether "Open" works now; else why not (``preparing``, ``error``, ``suspended``, ``deleting``).
    can_open: bool
    open_blocked_reason: str | None
    #: The Hub's last refusal of this business (its error code), until a call succeeds; else None.
    hub_error: str | None
    maintenance: HubMaintenanceOut | None
    #: When the maintenance scheduled for its night starts, while it is still ahead; else None.
    move_scheduled_for: datetime | None
    #: The business's time zone: that moment is said on its clock.
    timezone: str
    deletion_requested_at: datetime | None
    purge_after: datetime | None
    created_at: datetime
    can: BusinessRowCanOut
    #: Why a renewal is not paid (``card_declined``: «Pay» waits for another card; ``card_changed``,
    #: ``authentication_required``, ``payment_failed``: «Pay» works); None while it is paid.
    unpaid_reason: UnpaidReason | None
    #: When the unpaid invoice was issued: the 7 days of grace count from it.
    unpaid_since: datetime | None
    #: Stripe's page to pay that invoice: only for the owner, whose billing it is.
    pay_url: str | None
    #: The account pays for the business, whatever its role: it owns its payer (``billing_profile``), or the plan
    #: is still charged to the card of one of its payers after a hand-over (``queries.payers.still_pays``).
    is_payer: bool
    #: That payer (its Stripe customer), only to whoever owns it: the Store warns about a declined card only for
    #: the businesses it pays too.
    payer_id: UUID | None


class BusinessListOut(Page[BusinessRowOut]):
    invitations: list[InvitationOut]
    ownership_offers: list[OwnershipOfferOut]
    #: The account's Free business when its Free ones fill the quota: a new business cannot be Free, so
    #: «Create business» says so before the form, naming it.
    free_business: HubRefOut | None


class BusinessTypeRefOut(Schema):
    code: str
    name: str


class BusinessCanOut(Schema):
    """What the account may do on the business, by its role and the business's status.
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
    #: Only the owner moves the business to another web address (HUBS-F16).
    change_address: bool
    #: Only the owner downloads the copies of the business's data (``hubs.data_copy.*``).
    download_data: bool


class BusinessDetailOut(Schema):
    id: UUID
    slug: str
    name: str
    host: str
    #: As in ``BusinessRowOut``.
    is_platform: bool
    country: str
    #: The country no longer changes: the business is ready, and may invoice (``hubs.country_locked``).
    country_locked: bool
    timezone: str
    language: str
    business_type: BusinessTypeRefOut | None
    status: str
    status_label: str
    hub_error: str | None
    maintenance: HubMaintenanceOut | None
    #: As in ``BusinessRowOut``.
    move_scheduled_for: datetime | None
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
    #: The last day the Hub measured (``hubs.usage.get``); ``None`` until the first night.
    usage: UsageOut | None


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


class BusinessAddressIn(Schema):
    """The new web address of the business, ``<slug>.erplora.com`` (only its owner changes it)."""

    id: UUID
    slug: str = Field(max_length=63, description="Lowercase letters, digits and hyphens; checked as the Hub checks it.")


class BusinessDeleteIn(Schema):
    id: UUID
    #: The business's name, typed again: deleting is not one click away.
    confirm_name: str = Field(max_length=120)


class BusinessOpenIn(Schema):
    id: UUID
    next: LocalPath = "/"
    #: «Open» inside the installed app: the jump carries ``shell=1``, the mark with which the app links the till
    #: to this business (``ERPlora/app`` ``hub_link.rs``).
    shell: bool = False


class BusinessOpenOut(Schema):
    """Where «Open» goes: the Hub's start (``/auth/login?next=``), which bounces to ``/hub-login/`` with a
    ``state`` bound to the browser; that door mints the code. The SPA navigates to ``url``."""

    url: str
