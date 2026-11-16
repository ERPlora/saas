"""What the sign-up checks before a business is created: the Free plan, staff accounts and the Free quota."""

from uuid import UUID

from django.conf import settings
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.operations import INTERNAL, operation

from hubs.models import Hub, Plan
from hubs.queries.access_control import Role, account_of
from hubs.queries.plan_catalog import free_plan
from hubs.schemas import BusinessCreateCheckIn, BusinessCreateCheckOut


def _free_hubs(user):
    """The Free businesses ``user`` owns (a deleted one no longer counts)."""
    return Hub.objects.filter(
        members__user=user,
        members__role=Role.OWNER,
        subscription__plan__price_monthly=0,
    ).exclude(status__in=[Hub.Status.DELETING, Hub.Status.DELETED])


def free_hubs_owned(user, excluding: UUID | None = None) -> int:
    """The Free businesses ``user`` owns (a deleted one no longer counts), for ``FREE_HUBS_PER_ACCOUNT``."""
    owned = _free_hubs(user)
    if excluding is not None:
        owned = owned.exclude(pk=excluding)
    return owned.count()


def free_business_filling_quota(user) -> Hub | None:
    """The first Free business of ``user`` when its Free ones fill the quota (``FREE_HUBS_PER_ACCOUNT``),
    else ``None``: «Create business» says so before the form."""
    owned = _free_hubs(user).order_by("created_at", "id")
    if owned.count() < getattr(settings, "FREE_HUBS_PER_ACCOUNT", 1):
        return None
    return owned.first()


def plan_of_a_new_business() -> Plan:
    """The Free plan a new business is born on; without it none can be created right now (503)."""
    plan = free_plan()
    if plan is None:
        raise OperationError(
            _("Businesses cannot be created right now. Try again in a few minutes."),
            code="hubs.free_plan_missing",
            status=503,
        )
    return plan


def refuse_staff(user) -> None:
    """The platform's staff and the customers never share an account: a staff or superuser account neither creates a
    business, nor is invited to one (nor invited again), nor enters one with an invitation that waited while it was
    made staff (409 ``hubs.platform_account``)."""
    if user.is_staff or user.is_superuser:
        raise Conflict(
            _("This address belongs to ERPlora's staff and cannot join a business."), code="hubs.platform_account"
        )


def refuse_full_free_quota(user, excluding: UUID | None = None) -> None:
    """One more Free business does not fit ``user``'s quota (``FREE_HUBS_PER_ACCOUNT``): 409
    ``hubs.free_hub_limit``. Counts without a lock: a write first takes it (``services.check_free_quota``)."""
    if free_hubs_owned(user, excluding=excluding) >= getattr(settings, "FREE_HUBS_PER_ACCOUNT", 1):
        raise Conflict(
            _("You already have a free business. Change its plan to create another one."),
            code="hubs.free_hub_limit",
        )


@operation(
    "hubs.business.create_check",
    kind="query",
    permission="hubs.manage",
    input=BusinessCreateCheckIn,
    output=BusinessCreateCheckOut,
    ai=INTERNAL,  # the preview of ``hubs.business.create``
)
def business_create_check(ctx: OperationContext, params: BusinessCreateCheckIn) -> dict:
    """Refuses as ``hubs.business.create`` refuses, before its card asks anybody to confirm it (ASSISTANT-F25):
    the assistant hears why and nobody confirms a business that was never going to be created. It locks nothing and
    the write checks again under its lock."""
    user = account_of(ctx)
    plan_of_a_new_business()
    refuse_staff(user)
    refuse_full_free_quota(user)
    return {}
