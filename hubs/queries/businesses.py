"""The businesses of an account and the page of one business."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone, translation
from live.context import OperationContext
from live.operations import AI, operation

from hubs.models import Hub, HubMember, HubOwnershipTransfer, Subscription
from hubs.queries.access_control import (
    LISTED,
    OPEN_BLOCKED,
    ROW_CAN,
    Role,
    access,
    account_of,
    can,
    host_of,
    maintenance_of,
    open_blocked_reason,
    scheduled_move_of,
    status_label,
)
from hubs.queries.hub_usage import usage_of
from hubs.queries.invitations import invitations_of, ownership_offers_of
from hubs.queries.membership import seats_of
from hubs.queries.payers import is_payer, plans_charged_to, still_pays, unpaid_of
from hubs.queries.plan_catalog import plan_ref
from hubs.queries.signup import free_business_filling_quota
from hubs.schemas.businesses import BusinessDetailOut, BusinessListIn, BusinessListOut
from hubs.schemas.common import ByIdIn


@operation(
    "hubs.business.list",
    kind="query",
    permission="hubs.view",
    input=BusinessListIn,
    output=BusinessListOut,
    expose_api=True,
    ai=AI(
        description="Lists the businesses of this account: name, address, status and plan.",
        asks={
            "en": ("what businesses do I have?", "list my shops", "show all my businesses"),
            "es": ("¿qué negocios tengo?", "enséñame mis negocios", "¿cuántos locales tengo?"),
        },
    ),
)
def business_list(ctx: OperationContext, data: BusinessListIn) -> dict[str, Any]:
    """The account's businesses, the last opened first, then by name.

    With them, what waits for its answer: invitations and ownership offers.
    """
    user = account_of(ctx)
    members = (
        HubMember.objects.select_related(
            "hub", "hub__billing_profile", "hub__subscription__plan", "hub__subscription__trial_plan"
        )
        .filter(user=user, accepted_at__isnull=False, hub__status__in=LISTED)
        .annotate(
            opened=Case(
                When(last_opened_at__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
            charged=Exists(plans_charged_to(OuterRef("hub_id"), OuterRef(OuterRef("user_id")))),
        )
    )
    if data.search:
        members = members.filter(
            Q(hub__name__icontains=data.search) | Q(hub__slug__icontains=data.search)
        )
    ordered = members.order_by("opened", "-last_opened_at", "hub__name", "hub__id")
    total = ordered.count()
    page = ordered[data.offset : data.offset + data.limit]
    now = timezone.now()
    with translation.override(ctx.language):
        rows = [business_row(member, now) for member in page]
        invitations = invitations_of(user, now)
        offers = ownership_offers_of(user, now)
    free = free_business_filling_quota(user)
    return {
        "rows": rows,
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
        "invitations": invitations,
        "ownership_offers": offers,
        "free_business": {"id": free.id, "slug": free.slug, "name": free.name} if free else None,
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
        "is_platform": hub.is_platform,
        "plan": plan,
        "role": member.role,
        "role_label": str(member.get_role_display()),
        "last_opened_at": member.last_opened_at,
        "can_open": hub.status not in OPEN_BLOCKED,
        "open_blocked_reason": open_blocked_reason(hub),
        "hub_error": hub.last_hub_error or None,
        "maintenance": maintenance_of(hub),
        "move_scheduled_for": scheduled_move_of(hub, now),
        "timezone": hub.timezone,
        "deletion_requested_at": hub.deletion_requested_at,
        "purge_after": hub.purge_after,
        "created_at": hub.created_at,
        "can": {
            key: allowed for key, allowed in can(member, now).items() if key in ROW_CAN
        },
        **unpaid_of(member, getattr(hub, "subscription", None)),
        "is_payer": still_pays(member),
        "payer_id": hub.billing_profile_id if is_payer(member) else None,
    }


def _plan_of(hub: Hub, now: datetime) -> dict[str, Any] | None:
    subscription = getattr(hub, "subscription", None)
    if subscription is None:
        return None
    return plan_ref(subscription.plan)


@operation(
    "hubs.business.get",
    kind="query",
    permission="hubs.view",
    input=ByIdIn,
    output=BusinessDetailOut,
    expose_api=True,
    ai=AI(
        description="One business of this account with its people, plan and address.",
        asks={
            "en": (
                "show me Bar Manolo",
                "who has access to the salon and on what plan?",
                "what's the address of the café?",
            ),
            "es": ("enséñame Bar Manolo", "¿qué plan tiene el café?", "¿cuál es la dirección de la peluquería?"),
        },
    ),
)
def business_get(ctx: OperationContext, data: ByIdIn) -> dict[str, Any]:
    """A business's page (the Summary and Settings tabs): its owner and its administrators."""
    user = account_of(ctx)
    member = access(user, data.id, Role.ADMIN)
    with translation.override(ctx.language):
        return business_detail(member)


def business_detail(member: HubMember) -> dict[str, Any]:
    """The page of ``member``'s business as ``member`` sees it."""
    hub = Hub.objects.select_related("business_type", "billing_profile").get(pk=member.hub_id)
    member.hub = hub
    now = timezone.now()
    subscription = (
        Subscription.objects.select_related("plan", "trial_plan")
        .filter(hub=hub)
        .first()
    )
    trial_live = (
        subscription is not None
        and subscription.trial_plan_id is not None
        and subscription.trial_end
        and subscription.trial_end > now
    )
    pending = (
        HubOwnershipTransfer.objects.filter(
            hub=hub, status=HubOwnershipTransfer.Status.PENDING, expires_at__gt=now
        ).first()
        if member.role == Role.OWNER
        else None
    )
    return {
        "id": hub.id,
        "slug": hub.slug,
        "name": hub.name,
        "host": host_of(hub.slug),
        "is_platform": hub.is_platform,
        "country": hub.country,
        "country_locked": country_locked(hub),
        "timezone": hub.timezone,
        "language": hub.language,
        "business_type": (
            {"code": hub.business_type.code, "name": hub.business_type.name()}
            if hub.business_type
            else None
        ),
        "status": hub.status,
        "status_label": status_label(hub.status),
        "hub_error": hub.last_hub_error or None,
        "maintenance": maintenance_of(hub),
        "move_scheduled_for": scheduled_move_of(hub, now),
        "ready_at": hub.ready_at,
        "created_at": hub.created_at,
        "deletion_requested_at": hub.deletion_requested_at,
        "purge_after": hub.purge_after,
        "role": member.role,
        "role_label": str(member.get_role_display()),
        "plan": plan_ref(subscription.plan) if subscription else None,
        "trial_plan": plan_ref(subscription.trial_plan) if trial_live else None,
        "trial_end": subscription.trial_end if trial_live else None,
        "seats": seats_of(hub, now),
        "pending_transfer": (
            {
                "id": pending.id,
                "to_email": pending.to_email,
                "expires_at": pending.expires_at,
            }
            if pending
            else None
        ),
        "can": can(member, now),
        **unpaid_of(member, subscription),
        "is_payer": still_pays(member),
        "usage": usage_of(hub, subscription.effective_plan(now) if subscription else None, now),
    }


def country_locked(hub: Hub) -> bool:
    """The country no longer changes once the business is ready: its fiscal
    series and records belong to one country. The SaaS does not see the invoices (the Hub keeps them), so
    the lock starts at ``ready_at``, the first moment the business can invoice."""
    return hub.ready_at is not None


def expired_deletions(cutoff: datetime) -> list[UUID]:
    """The deleted businesses whose recovery window closed before ``cutoff``."""
    return list(
        Hub.objects.filter(
            status=Hub.Status.DELETING, deletion_requested_at__lte=cutoff
        ).values_list("id", flat=True)
    )
