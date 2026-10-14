"""Read operations of hubs, and the reads its commands and its push to the Hub share.

The public ones need no permission and no account: the taxonomy of the sign-up and the industry pages
(PLAN §21.4) and the plans on sale, which a visitor reads before signing up. Only active rows, in the
caller's language (``ctx.language``, which a live stream carries outside the request).

The rest are an account's (``hubs.view``, held by every signed-in account): its businesses, a
business's page and members, its invitations and a business's payer. Who may read what is decided
here by the account's ``HubMember`` role (round 17 §2.7): somebody without access to a business gets
404, never a hint that it exists; a role below the one needed gets 403.
"""

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
import re
from uuid import UUID

from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone, translation
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied, Unauthorized
from live.operations import operation
from live.slugs import is_reserved_hub_slug, validate_hub_slug

from accounts.models import HubMembership
from accounts.queries import hub_origin
from hubs.models import BusinessType, Hub, HubMember, HubOwnershipTransfer, Plan, Sector, Subscription
from hubs.retired_codes import current_business_type_code
from hubs.schemas import (
    AddressProposeIn,
    AddressProposeOut,
    BillingProfileGetIn,
    BillingProfileOut,
    BusinessDetailOut,
    BusinessListIn,
    BusinessListOut,
    BusinessTypeListIn,
    BusinessTypeListOut,
    ByIdIn,
    InvitationListIn,
    InvitationListOut,
    MemberListIn,
    MemberListOut,
    PlanListIn,
    PlanListOut,
    SectorListIn,
    SectorListOut,
)

Role = HubMember.Role
RANK = HubMember.RANK

def _entry(row: Sector | BusinessType, language: str) -> dict[str, Any]:
    return {
        "code": row.code,
        "name": row.name(language),
        "description": row.description(language),
        "icon": row.icon,
        "color": row.color,
        "updated_at": row.updated_at,
    }


@operation("hubs.sector.list", kind="query", permission=None, input=SectorListIn, output=SectorListOut)
def sector_list(ctx: OperationContext, data: SectorListIn) -> dict[str, Any]:
    """The active sectors, by their display order."""
    sectors = Sector.objects.filter(is_active=True).order_by("display_order", "code")
    return {"sectors": [_entry(sector, ctx.language) for sector in sectors]}


@operation(
    "hubs.business_type.list", kind="query", permission=None, input=BusinessTypeListIn, output=BusinessTypeListOut
)
def business_type_list(ctx: OperationContext, data: BusinessTypeListIn) -> dict[str, Any]:
    """The active business types by their display order, then code, across sectors (the origin ``catalog``'s
    ``ordering = ["order", "code"]``: ``/industries/`` interleaves them as the seed orders them)."""
    business_types = BusinessType.objects.filter(is_active=True).select_related("sector")
    if data.sector:
        business_types = business_types.filter(sector__code=data.sector)
    ordered = business_types.order_by("display_order", "code")
    return {
        "business_types": [
            {
                **_entry(business_type, ctx.language),
                "sector": _sector_ref(business_type.sector, ctx.language),
                "vertical": business_type.vertical,
            }
            for business_type in ordered
        ]
    }


def _sector_ref(sector: Sector | None, language: str) -> dict[str, str] | None:
    return None if sector is None else {"code": sector.code, "name": sector.name(language)}


@operation("hubs.plan.list", kind="query", permission=None, input=PlanListIn, output=PlanListOut)
def plan_list(ctx: OperationContext, data: PlanListIn) -> dict[str, Any]:
    """The plans on sale (``Plan.objects.public()``), by display order then price.

    Each plan's features end with its real trial (saas#2424), except an upgrade's: an upgrade grants
    none (#809). The rows of the old seed carried visual separators («───»): they are dropped.
    """
    plans = list(Plan.objects.public().order_by("display_order", "price_monthly"))
    signable = [plan for plan in plans if not plan.upgrade_only]
    cheapest = min(signable, key=lambda plan: (plan.price_monthly, plan.display_order), default=None)
    trial_days = Plan.objects.signup_trial_days()["trial_days_max"] or 0
    with translation.override(ctx.language):
        rows = [_plan(plan, ctx.language) for plan in plans]
    return {"signup_trial_days": trial_days, "cheapest_slug": cheapest.slug if cheapest else None, "plans": rows}


def _plan(plan: Plan, language: str) -> dict[str, Any]:
    features = [feature for feature in plan.translated("features", language) if str(feature).strip().strip("─").strip()]
    if not plan.upgrade_only and plan.trial_label:
        features.append(plan.trial_label)
    return {
        "slug": plan.slug,
        "name": plan.translated("name", language),
        "description": plan.translated("description", language),
        "price_monthly": plan.price_monthly,
        "price_annual": plan.price_annual,
        "features": features,
        "featured_label": plan.translated("featured_label", language),
        "max_users": plan.max_users,
        "max_devices": plan.max_devices,
        "trial_period_days": plan.trial_period_days,
        "has_trial": plan.has_trial(),
        "support_level_label": plan.support_level_label,
        "included_level_label": plan.included_level_label,
        "upgrade_only": plan.upgrade_only,
        "internal_only": plan.internal_only,
    }


# --- Access to a business -------------------------------------------------------------------------

#: Statuses a business is listed with; ``deleted`` (purged) is gone for good.
LISTED = [status for status in Hub.Status.values if status != Hub.Status.DELETED]
#: Why «Open» does not work, by status (round 17 §2.2): a business with a payment pending still opens.
OPEN_BLOCKED = {
    Hub.Status.PREPARING: "preparing",
    Hub.Status.SUSPENDED: "suspended",
    Hub.Status.DELETING: "deleting",
    Hub.Status.DELETED: "deleting",
}


def account_of(ctx: OperationContext):
    """The signed-in account running ``ctx``; a visitor without one is refused."""
    if ctx.actor is None or isinstance(ctx.actor, str):
        raise Unauthorized(_("Sign in to see your businesses."))
    return ctx.actor


def not_found() -> NotFound:
    return NotFound(_("This business does not exist or you have no access to it."))


def access(user, hub_id: UUID, minimum: str = Role.EMPLOYEE, *, lock: bool = False) -> HubMember:
    """``user``'s answered membership of the business ``hub_id``, with its hub.

    No business, no membership or an unanswered invitation: 404 (nobody learns a business exists).
    A role below ``minimum``: 403. ``lock`` takes the hub's row first (commands), so two writes on one
    business never interleave.
    """
    if lock:
        hub = Hub.objects.select_for_update().filter(pk=hub_id).first()
        if hub is None:
            raise not_found()
    member = (
        HubMember.objects.select_related("hub", "hub__business_type", "user")
        .filter(hub_id=hub_id, user=user, accepted_at__isnull=False)
        .exclude(hub__status=Hub.Status.DELETED)
        .first()
    )
    if member is None:
        raise not_found()
    if RANK[member.role] > RANK[minimum]:
        raise PermissionDenied(_("Your role in this business does not allow it."))
    return member


def open_blocked_reason(hub: Hub) -> str | None:
    """Why "Open" does not work: a business being prepared whose registry the Hub refused is an error."""
    reason = OPEN_BLOCKED.get(hub.status)
    if reason == "preparing" and hub.last_hub_error:
        return "error"
    return reason


def is_writable(hub: Hub) -> bool:
    """Whether the business takes changes: a deleted one answers every write with 409 until recovered."""
    return hub.status not in (Hub.Status.DELETING, Hub.Status.DELETED)


def is_restorable(hub: Hub, now: datetime) -> bool:
    """Deleted and still within its 90 days (``hubs.business.restore``)."""
    return hub.status == Hub.Status.DELETING and hub.purge_after is not None and hub.purge_after > now


def can(member: HubMember, now: datetime | None = None) -> dict[str, bool]:
    """What ``member`` may do on its business, by role (round 17 §2.7) and status, computed here so no page
    deduces it: the owner everything, an admin the team and the settings, a manager or an employee only
    «Open». «Open» while it serves; a deleted business takes no change, only «Recover» by its owner."""
    hub = member.hub
    now = now or timezone.now()
    is_owner = member.role == Role.OWNER
    manages_it = RANK[member.role] <= RANK[Role.ADMIN] and is_writable(hub)
    return {
        "open": hub.status not in OPEN_BLOCKED,
        "manage": manages_it,
        "manage_members": manages_it,
        "manage_settings": manages_it,
        "manage_billing": is_owner,
        "transfer": is_owner and is_writable(hub),
        "restore": is_owner and is_restorable(hub, now),
        "delete": is_owner and is_writable(hub),
    }


#: What a row of the Businesses page says its buttons do (``BusinessRowCanOut``).
ROW_CAN = ("open", "manage", "restore", "delete")


def host_of(slug: str) -> str:
    """``<slug>.erplora.com`` (locally ``<slug>.localhost:8000``)."""
    return urlsplit(hub_origin(slug)).netloc


def status_label(status: str) -> str:
    return str(Hub.Status(status).label)


# --- What the sign-up reads --------------------------------------------------------------------------

#: The address of a business whose name slugifies to nothing (emoji, other scripts).
FALLBACK_SLUG = "my-business"
#: Room for the counter within a DNS label.
SLUG_BASE_MAX_LENGTH = 30


def free_plan() -> Plan | None:
    """The permanent Free plan (0 €) a business is born on, or ``None`` if it is not seeded."""
    return Plan.objects.public().filter(price_monthly=0).order_by("display_order").first()


def trial_plan() -> Plan | None:
    """The plan a Free business is born trying (ADR-0474: Starter), if it is on sale with a trial."""
    return Plan.objects.public().filter(slug="starter", trial_period_days__gt=0).first()


def free_hubs_owned(user, excluding: UUID | None = None) -> int:
    """The Free businesses ``user`` owns (a deleted one no longer counts): ADR-0154's quota."""
    owned = Hub.objects.filter(members__user=user, members__role=Role.OWNER, subscription__plan__price_monthly=0).exclude(
        status__in=[Hub.Status.DELETING, Hub.Status.DELETED]
    )
    if excluding is not None:
        owned = owned.exclude(pk=excluding)
    return owned.count()


def business_type_for(code: str | None) -> BusinessType | None:
    """The active business type of ``code`` (a retired code resolves to its survivor); else «not said»."""
    if not code:
        return None
    return BusinessType.objects.filter(code=current_business_type_code(code), is_active=True).first()


def slug_taken(slug: str) -> bool:
    """A business has it, or a hub of the phase-1 seed (only an ``accounts.HubMembership`` row)."""
    return Hub.objects.filter(slug=slug).exists() or HubMembership.objects.filter(hub_slug=slug).exists()


def base_slug(name: str) -> str:
    """The address a name proposes, always one the Hub accepts (``live.slugs``).

    ``slugify`` keeps ``_``, which no DNS label admits: it becomes ``-``, runs of hyphens collapse and
    none is left at an end (also after the cut). A reserved or too short name gets ``-store``.
    """
    base = re.sub(r"-+", "-", slugify(name).replace("_", "-"))[:SLUG_BASE_MAX_LENGTH].strip("-")
    if not base:
        return FALLBACK_SLUG
    if is_reserved_hub_slug(base) or len(base) < 3:
        base = f"{base}-store"
    return base if is_valid_slug(base) else FALLBACK_SLUG


def is_valid_slug(slug: str) -> bool:
    try:
        validate_hub_slug(slug)
    except ValueError:
        return False
    return True


def free_slug(name: str) -> str:
    """The first free address of ``name``: ``bar-manolo``, ``bar-manolo-2``…"""
    base = base_slug(name)
    taken = set(Hub.objects.filter(slug__startswith=base).values_list("slug", flat=True))
    taken |= set(HubMembership.objects.filter(hub_slug__startswith=base).values_list("hub_slug", flat=True))
    candidate, counter = base, 1
    while candidate in taken or not is_valid_slug(candidate):
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate


@operation("hubs.address.propose", kind="query", permission="hubs.view", input=AddressProposeIn, output=AddressProposeOut)
def address_propose(ctx: OperationContext, data: AddressProposeIn) -> dict[str, Any]:
    """The address «Create a business» proposes while the name is typed."""
    account_of(ctx)
    slug = free_slug(data.name)
    return {"slug": slug, "host": host_of(slug)}


# --- The businesses of an account -----------------------------------------------------------------


@operation("hubs.business.list", kind="query", permission="hubs.view", input=BusinessListIn, output=BusinessListOut)
def business_list(ctx: OperationContext, data: BusinessListIn) -> dict[str, Any]:
    """The account's businesses, the last opened first (round 17 §2.2), then by name.

    With them, what waits for its answer: invitations and ownership offers.
    """
    user = account_of(ctx)
    members = (
        HubMember.objects.select_related("hub", "hub__subscription__plan", "hub__subscription__trial_plan")
        .filter(user=user, accepted_at__isnull=False, hub__status__in=LISTED)
        .annotate(opened=Case(When(last_opened_at__isnull=True, then=Value(1)), default=Value(0), output_field=IntegerField()))
    )
    if data.search:
        members = members.filter(Q(hub__name__icontains=data.search) | Q(hub__slug__icontains=data.search))
    ordered = members.order_by("opened", "-last_opened_at", "hub__name", "hub__id")
    total = ordered.count()
    page = ordered[data.offset : data.offset + data.limit]
    now = timezone.now()
    with translation.override(ctx.language):
        rows = [business_row(member, now) for member in page]
        invitations = invitations_of(user, now)
        offers = ownership_offers_of(user, now)
    return {
        "rows": rows,
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
        "invitations": invitations,
        "ownership_offers": offers,
    }


def business_row(member: HubMember, now: datetime) -> dict[str, Any]:
    hub = member.hub
    plan = _plan_of(hub, now)
    return {
        "id": hub.id,
        "slug": hub.slug,
        "name": hub.name,
        "host": host_of(hub.slug),
        "status": hub.status,
        "status_label": status_label(hub.status),
        "plan": plan,
        "role": member.role,
        "role_label": str(member.get_role_display()),
        "last_opened_at": member.last_opened_at,
        "can_open": hub.status not in OPEN_BLOCKED,
        "open_blocked_reason": open_blocked_reason(hub),
        "hub_error": hub.last_hub_error or None,
        "deletion_requested_at": hub.deletion_requested_at,
        "purge_after": hub.purge_after,
        "created_at": hub.created_at,
        "can": {key: allowed for key, allowed in can(member, now).items() if key in ROW_CAN},
    }


def _plan_of(hub: Hub, now: datetime) -> dict[str, str] | None:
    subscription = getattr(hub, "subscription", None)
    if subscription is None:
        return None
    plan = subscription.plan
    return {"slug": plan.slug, "name": plan.translated("name")}


def invitations_of(user, now: datetime) -> list[dict[str, Any]]:
    """The invitations waiting for ``user``'s answer: not answered, not expired, business not deleted."""
    pending = (
        HubMember.objects.select_related("hub", "invited_by")
        .filter(user=user, accepted_at__isnull=True, hub__status__in=[s for s in LISTED if s != Hub.Status.DELETING])
        .filter(Q(invitation_expires_at__isnull=True) | Q(invitation_expires_at__gt=now))
        .order_by("invited_at", "id")
    )
    return [
        {
            "id": member.id,
            "hub": {"id": member.hub.id, "slug": member.hub.slug, "name": member.hub.name},
            "role": member.role,
            "role_label": str(member.get_role_display()),
            "invited_by": _name_of(member.invited_by),
            "invited_at": member.invited_at,
            "expires_at": member.invitation_expires_at,
            "message": member.invitation_message,
        }
        for member in pending
    ]


def ownership_offers_of(user, now: datetime) -> list[dict[str, Any]]:
    """The businesses offered to ``user``, waiting for its answer (an expired offer is not live)."""
    offers = (
        HubOwnershipTransfer.objects.select_related("hub")
        .filter(to_user=user, status=HubOwnershipTransfer.Status.PENDING, expires_at__gt=now)
        .order_by("-created_at")
    )
    return [
        {
            "id": offer.id,
            "hub": {"id": offer.hub.id, "slug": offer.hub.slug, "name": offer.hub.name},
            "from_email": offer.from_email,
            "expires_at": offer.expires_at,
        }
        for offer in offers
    ]


def _name_of(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name() or user.email


@operation("hubs.business.get", kind="query", permission="hubs.view", input=ByIdIn, output=BusinessDetailOut)
def business_get(ctx: OperationContext, data: ByIdIn) -> dict[str, Any]:
    """A business's page (the Summary and Settings tabs): its owner and its administrators."""
    user = account_of(ctx)
    member = access(user, data.id, Role.ADMIN)
    with translation.override(ctx.language):
        return business_detail(member)


def business_detail(member: HubMember) -> dict[str, Any]:
    """The page of ``member``'s business as ``member`` sees it."""
    hub = Hub.objects.select_related("business_type").get(pk=member.hub_id)
    member.hub = hub
    now = timezone.now()
    subscription = Subscription.objects.select_related("plan", "trial_plan").filter(hub=hub).first()
    trial_live = subscription is not None and subscription.trial_plan_id is not None and subscription.trial_end and subscription.trial_end > now
    pending = (
        HubOwnershipTransfer.objects.filter(hub=hub, status=HubOwnershipTransfer.Status.PENDING, expires_at__gt=now).first()
        if member.role == Role.OWNER
        else None
    )
    return {
        "id": hub.id,
        "slug": hub.slug,
        "name": hub.name,
        "host": host_of(hub.slug),
        "country": hub.country,
        "country_locked": country_locked(hub),
        "timezone": hub.timezone,
        "language": hub.language,
        "business_type": (
            {"code": hub.business_type.code, "name": hub.business_type.name()} if hub.business_type else None
        ),
        "status": hub.status,
        "status_label": status_label(hub.status),
        "hub_error": hub.last_hub_error or None,
        "ready_at": hub.ready_at,
        "created_at": hub.created_at,
        "deletion_requested_at": hub.deletion_requested_at,
        "purge_after": hub.purge_after,
        "role": member.role,
        "role_label": str(member.get_role_display()),
        "plan": {"slug": subscription.plan.slug, "name": subscription.plan.translated("name")} if subscription else None,
        "trial_plan": (
            {"slug": subscription.trial_plan.slug, "name": subscription.trial_plan.translated("name")} if trial_live else None
        ),
        "trial_end": subscription.trial_end if trial_live else None,
        "seats": seats_of(hub, now),
        "pending_transfer": (
            {"id": pending.id, "to_email": pending.to_email, "expires_at": pending.expires_at} if pending else None
        ),
        "can": can(member, now),
    }


def country_locked(hub: Hub) -> bool:
    """The country no longer changes once the business is ready (mockups README §6.21, W-B7): its fiscal
    series and records belong to one country. The SaaS does not see the invoices (the Hub keeps them), so
    the lock starts at ``ready_at``, the first moment the business can invoice."""
    return hub.ready_at is not None


def seats_of(hub: Hub, now: datetime) -> dict[str, int | None]:
    """The seats of the business (saas#2022): ``used`` = its people, answered or invited (a live
    invitation holds its seat: it is spent when somebody is added, never when they walk in), and
    ``limit`` = what its plan covers at ``now``, ``None`` when nothing caps it (``max_users = 0`` on
    every paid plan and the Starter trial, or no subscription at all)."""
    used = (
        HubMember.objects.filter(hub=hub)
        .filter(Q(accepted_at__isnull=False) | Q(invitation_expires_at__isnull=True) | Q(invitation_expires_at__gt=now))
        .count()
    )
    return {"used": used, "limit": seat_limit_of(hub, now)}


def seat_limit_of(hub: Hub, now: datetime) -> int | None:
    """The people the plan of ``hub`` covers at ``now``; ``None`` = unlimited."""
    subscription = Subscription.objects.select_related("plan", "trial_plan").filter(hub=hub).first()
    limit = subscription.effective_plan(now).max_users if subscription else 0
    return limit or None


def people_inside(hub: Hub) -> int:
    """The people who answered: those an acceptance must find a seat beside."""
    return HubMember.objects.filter(hub=hub, accepted_at__isnull=False).count()


def expired_deletions(cutoff: datetime) -> list[UUID]:
    """The deleted businesses whose recovery window closed before ``cutoff``."""
    return list(
        Hub.objects.filter(status=Hub.Status.DELETING, deletion_requested_at__lte=cutoff).values_list("id", flat=True)
    )


def owner_id(hub_id: UUID) -> UUID | None:
    return HubMember.objects.filter(hub_id=hub_id, role=Role.OWNER).values_list("user_id", flat=True).first()


# --- What the Hub is told (hubs.services.sync_hub) ------------------------------------------------

#: The snapshot's ``status`` is the commercial one (PLAN-SAAS §2.3): a business being prepared is
#: active for the Hub's rights.
SNAPSHOT_STATUS = {
    Hub.Status.PREPARING: "active",
    Hub.Status.ACTIVE: "active",
    Hub.Status.PAST_DUE: "past_due",
    Hub.Status.SUSPENDED: "suspended",
}


def hub_registry(hub_id: UUID) -> dict[str, Any]:
    """The body of ``PUT /internal/hubs/{id}``: what the Hub provisions the business with (§3.1)."""
    hub = Hub.objects.select_related("business_type").get(pk=hub_id)
    vertical = hub.business_type.vertical if hub.business_type else ""
    return {
        "id": str(hub.id),
        "slug": hub.slug,
        "name": hub.name,
        "country": hub.country,
        "timezone": hub.timezone,
        "language": hub.language,
        "vertical": vertical or None,
    }


def hub_snapshot(hub_id: UUID) -> dict[str, Any]:
    """The body of ``PUT /internal/hubs/{id}/state`` (PLAN-SAAS §2.2), at the business's state version.

    ``hub_id`` names the hub of the path, which the signature (body only) does not cover.
    """
    hub = Hub.objects.get(pk=hub_id)
    now = timezone.now()
    subscription = Subscription.objects.select_related("plan", "trial_plan").filter(hub=hub).first()
    plan = subscription.effective_plan(now) if subscription else free_plan()
    items = subscription.items.order_by("module_slug") if subscription else []
    members = (
        HubMember.objects.select_related("user")
        .filter(hub=hub, accepted_at__isnull=False)
        .annotate(rank=Case(*[When(role=role, then=Value(rank)) for role, rank in RANK.items()], output_field=IntegerField()))
        .order_by("rank", "joined_at", "id")
    )
    return {
        "hub_id": str(hub.id),
        "version": hub.state_version,
        "status": SNAPSHOT_STATUS.get(hub.status, "suspended"),
        "plan": _snapshot_plan(plan),
        "modules": [
            {
                "id": item.module_slug,
                "source": item.source,
                "valid_until": item.valid_until.isoformat() if item.valid_until else None,
            }
            for item in items
            if item.is_live(now)
        ],
        "members": [
            {
                "user_id": str(member.user_id),
                "email": member.user.email,
                "name": member.user.get_full_name() or member.user.email,
                "role": member.role,
            }
            for member in members
        ],
    }


def _snapshot_plan(plan: Plan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "slug": plan.slug,
        "included_level": plan.included_level,
        "max_devices": plan.max_devices,
        "max_users": plan.max_users,
        "max_db_connections": plan.max_db_connections,
        "statement_timeout_seconds": plan.statement_timeout_seconds,
    }


# --- Members and invitations ----------------------------------------------------------------------

#: The roles an invitation or a role change may hand out, from the most authority to the least.
INVITABLE = [Role.ADMIN, Role.MANAGER, Role.EMPLOYEE]
MEMBER_STATUS_LABELS = {
    "active": gettext_lazy("Active"),
    "pending": gettext_lazy("Pending"),
    "expired": gettext_lazy("Expired"),
}


def assignable_roles(role: str) -> list[str]:
    """The roles ``role`` may hand out: strictly below its own, and only from admin up."""
    if RANK[role] > RANK[Role.ADMIN]:
        return []
    return [str(candidate) for candidate in INVITABLE if RANK[candidate] > RANK[role]]


def manages(actor: HubMember, target: HubMember) -> bool:
    """Whether ``actor`` may act on ``target``: an admin or the owner, never on itself nor on a peer
    or a superior (test_member_service: the hierarchy is per business)."""
    return (
        target.user_id != actor.user_id
        and RANK[actor.role] <= RANK[Role.ADMIN]
        and RANK[target.role] > RANK[actor.role]
    )


def ranked(members):
    """``members`` with their ``rank``, the owner first."""
    return members.annotate(
        rank=Case(*[When(role=role, then=Value(rank)) for role, rank in RANK.items()], output_field=IntegerField())
    )


@operation("hubs.member.list", kind="query", permission="hubs.view", input=MemberListIn, output=MemberListOut)
def member_list(ctx: OperationContext, data: MemberListIn) -> dict[str, Any]:
    """The members page of a business (the Members tab), for its owner and its administrators: every member
    and invitation, the owner first, with the actions the account may take on each row."""
    actor = access(account_of(ctx), data.hub_id, Role.ADMIN)
    now = timezone.now()
    everyone = ranked(HubMember.objects.select_related("user", "invited_by").filter(hub_id=data.hub_id)).order_by(
        "rank", "joined_at", "id"
    )
    total = everyone.count()
    page = everyone[data.offset : data.offset + data.limit]
    offered = HubOwnershipTransfer.objects.filter(
        hub_id=data.hub_id, status=HubOwnershipTransfer.Status.PENDING, expires_at__gt=now
    ).exists()
    with translation.override(ctx.language):
        rows = [member_row(actor, member, now, transfer_pending=offered) for member in page]
    return {
        "rows": rows,
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
        "seats": seats_of(actor.hub, now),
        "invitable_roles": assignable_roles(actor.role) if is_writable(actor.hub) else [],
    }


#: The row actions in the order the members page shows them.
MEMBER_ACTIONS = ("change_role", "remove", "resend", "cancel", "transfer")


def member_actions(actor: HubMember, member: HubMember, *, transfer_pending: bool = False) -> list[str]:
    """What ``actor`` may do on ``member``'s row, in ``MEMBER_ACTIONS`` order (saas#1626, saas#1670): the
    same rules the writes apply (``services._managed``, ``services.ownership_transfer``), so the page never
    offers a button its door refuses. Nothing on one's own row, a peer, a superior or a deleted business."""
    if not is_writable(actor.hub):
        return []
    pending = member.accepted_at is None
    manageable = manages(actor, member)
    allowed = {
        "change_role": manageable,
        "remove": manageable and not pending,
        "resend": manageable and pending,
        "cancel": manageable and pending,
        "transfer": actor.role == Role.OWNER
        and member.user_id != actor.user_id
        and not pending
        and not transfer_pending,
    }
    return [action for action in MEMBER_ACTIONS if allowed[action]]


def member_row(actor: HubMember, member: HubMember, now: datetime, *, transfer_pending: bool = False) -> dict[str, Any]:
    """One row of the members page as ``actor`` sees it: ``is_me`` marks the account's own row, and
    ``actions`` lists what it may do on this one (``member_actions``)."""
    pending = member.accepted_at is None
    status = "expired" if member.is_expired(now) else "pending" if pending else "active"
    actions = member_actions(actor, member, transfer_pending=transfer_pending)
    return {
        "id": member.id,
        "user_id": member.user_id,
        "email": member.user.email,
        "name": member.user.get_full_name() or member.user.email,
        "role": member.role,
        "role_label": str(member.get_role_display()),
        "status": status,
        "status_label": str(MEMBER_STATUS_LABELS[status]),
        "invited_by": _name_of(member.invited_by),
        "invited_at": member.invited_at,
        "invitation_expires_at": member.invitation_expires_at,
        # An invitation has not joined anything yet (saas#2251): no date until it is answered.
        "joined_at": None if pending else member.joined_at,
        "accepted_at": member.accepted_at,
        "last_opened_at": member.last_opened_at,
        "is_me": member.user_id == actor.user_id,
        "actions": actions,
        "assignable_roles": assignable_roles(actor.role) if "change_role" in actions else [],
    }


@operation(
    "hubs.invitation.list_mine", kind="query", permission="hubs.view", input=InvitationListIn, output=InvitationListOut
)
def invitation_list_mine(ctx: OperationContext, data: InvitationListIn) -> dict[str, Any]:
    """The invitations waiting for the account's answer (the invitation page)."""
    user = account_of(ctx)
    with translation.override(ctx.language):
        return {"invitations": invitations_of(user, timezone.now())}


# --- The payer ------------------------------------------------------------------------------------

PAYER_FIELDS = (
    "billing_name",
    "tax_id",
    "billing_address",
    "billing_city",
    "billing_postal_code",
    "billing_country",
    "billing_email",
    "same_as_business",
)


@operation(
    "hubs.billing_profile.get", kind="query", permission="hubs.view", input=BillingProfileGetIn, output=BillingProfileOut
)
def billing_profile_get(ctx: OperationContext, data: BillingProfileGetIn) -> dict[str, Any]:
    """Who ERPlora invoices for the business (Account → Billing, and the Settings tab): only its owner."""
    member = access(account_of(ctx), data.hub_id, Role.OWNER)
    return payer_of(member.hub, member.user)


def payer_of(hub: Hub, owner) -> dict[str, Any]:
    """The payer of ``hub`` as its ``owner`` edits it: empty when there is none yet, and when it is
    another account's (it keeps paying; its data is not the new owner's to read)."""
    profile = hub.billing_profile
    if profile is None or profile.owner_id != owner.pk:
        return {
            "hub_id": hub.id,
            **{field: "" for field in PAYER_FIELDS},
            "same_as_business": False,
            "paid_by_another_account": profile is not None,
        }
    return {"hub_id": hub.id, **{field: getattr(profile, field) for field in PAYER_FIELDS}, "paid_by_another_account": False}
