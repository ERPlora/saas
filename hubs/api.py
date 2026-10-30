"""Ninja routes of hubs: each route calls exactly one operation and holds no logic.

The panel's routes live under ``/api/hubs/`` with the API's session auth (an anonymous visitor gets
the 401 envelope). No path parameters: ids travel in the input (query string on GET, body on POST),
because a route takes one parameter, the operation's input. ``hubs.business.mark_ready`` has no route:
only the Hub calls it, signed, at ``/internal/hubs/{id}/ready`` (``hubs/internal.py``).

The taxonomy and the plans on sale are public (``auth=None``): the sign-up, the industry pages and
the pricing page read them before any account exists. A GET needs no CSRF token.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from hubs import queries, services
from hubs.schemas import (
    AddressProposeIn,
    BillingProfileGetIn,
    BillingProfileIn,
    BusinessCreateIn,
    BusinessAddressIn,
    BusinessDeleteIn,
    BusinessListIn,
    BusinessOpenIn,
    BusinessTypeListIn,
    BusinessUpdateIn,
    ByIdIn,
    DataCopyLinkIn,
    DataCopyListIn,
    InvitationListIn,
    MemberInviteIn,
    MemberListIn,
    MemberRoleIn,
    OwnershipTransferIn,
    UsageGetIn,
    UsageSeriesIn,
)

router = Router(tags=["hubs"])


@bind(router, "hubs.sector.list", "/catalog/sectors", auth=None)
async def sector_list(request):
    return await run_operation(request, queries.sector_list)


@bind(router, "hubs.business_type.list", "/catalog/business-types", auth=None)
async def business_type_list(request, params: Query[BusinessTypeListIn]):
    return await run_operation(request, queries.business_type_list, params)


@bind(router, "hubs.plan.list", "/plans", auth=None)
async def plan_list(request):
    return await run_operation(request, queries.plan_list)


# --- Businesses -----------------------------------------------------------------------------------


@bind(router, "hubs.business.list", "/hubs/businesses")
async def business_list(request, params: Query[BusinessListIn]):
    return await run_operation(request, queries.business_list, params)


@bind(router, "hubs.business.create", "/hubs/businesses", status=201)
async def business_create(request, data: BusinessCreateIn):
    return await run_operation(request, services.business_create, data)


@bind(router, "hubs.business.get", "/hubs/businesses/detail")
async def business_get(request, params: Query[ByIdIn]):
    return await run_operation(request, queries.business_get, params)


@bind(router, "hubs.business.update", "/hubs/businesses/update")
async def business_update(request, data: BusinessUpdateIn):
    return await run_operation(request, services.business_update, data)


@bind(router, "hubs.business.change_address", "/hubs/businesses/address")
async def business_change_address(request, data: BusinessAddressIn):
    return await run_operation(request, services.business_change_address, data)


@bind(router, "hubs.business.delete", "/hubs/businesses/delete")
async def business_delete(request, data: BusinessDeleteIn):
    return await run_operation(request, services.business_delete, data)


@bind(router, "hubs.business.restore", "/hubs/businesses/restore")
async def business_restore(request, data: ByIdIn):
    return await run_operation(request, services.business_restore, data)


@bind(router, "hubs.business.open", "/hubs/businesses/open")
async def business_open(request, data: BusinessOpenIn):
    return await run_operation(request, services.business_open, data)


@bind(router, "hubs.address.propose", "/hubs/address")
async def address_propose(request, params: Query[AddressProposeIn]):
    return await run_operation(request, queries.address_propose, params)


# --- Members and invitations ----------------------------------------------------------------------


@bind(router, "hubs.member.list", "/hubs/members")
async def member_list(request, params: Query[MemberListIn]):
    return await run_operation(request, queries.member_list, params)


@bind(router, "hubs.member.invite", "/hubs/members/invite")
async def member_invite(request, data: MemberInviteIn):
    return await run_operation(request, services.member_invite, data)


@bind(router, "hubs.member.change_role", "/hubs/members/change_role")
async def member_change_role(request, data: MemberRoleIn):
    return await run_operation(request, services.member_change_role, data)


@bind(router, "hubs.member.remove", "/hubs/members/remove")
async def member_remove(request, data: ByIdIn):
    return await run_operation(request, services.member_remove, data)


@bind(router, "hubs.member.resend", "/hubs/members/resend")
async def member_resend(request, data: ByIdIn):
    return await run_operation(request, services.member_resend, data)


@bind(router, "hubs.member.cancel", "/hubs/members/cancel")
async def member_cancel(request, data: ByIdIn):
    return await run_operation(request, services.member_cancel, data)


@bind(router, "hubs.invitation.list_mine", "/hubs/invitations")
async def invitation_list_mine(request):
    return await run_operation(request, queries.invitation_list_mine, InvitationListIn())


@bind(router, "hubs.invitation.accept", "/hubs/invitations/accept")
async def invitation_accept(request, data: ByIdIn):
    return await run_operation(request, services.invitation_accept, data)


@bind(router, "hubs.invitation.decline", "/hubs/invitations/decline")
async def invitation_decline(request, data: ByIdIn):
    return await run_operation(request, services.invitation_decline, data)


# --- Ownership and payer --------------------------------------------------------------------------


@bind(router, "hubs.ownership.transfer", "/hubs/ownership/transfer")
async def ownership_transfer(request, data: OwnershipTransferIn):
    return await run_operation(request, services.ownership_transfer, data)


@bind(router, "hubs.ownership.accept", "/hubs/ownership/accept")
async def ownership_accept(request, data: ByIdIn):
    return await run_operation(request, services.ownership_accept, data)


@bind(router, "hubs.ownership.decline", "/hubs/ownership/decline")
async def ownership_decline(request, data: ByIdIn):
    return await run_operation(request, services.ownership_decline, data)


@bind(router, "hubs.ownership.cancel", "/hubs/ownership/cancel")
async def ownership_cancel(request, data: ByIdIn):
    return await run_operation(request, services.ownership_cancel, data)


@bind(router, "hubs.billing_profile.get", "/hubs/billing-profile")
async def billing_profile_get(request, params: Query[BillingProfileGetIn]):
    return await run_operation(request, queries.billing_profile_get, params)


@bind(router, "hubs.billing_profile.update", "/hubs/billing-profile")
async def billing_profile_update(request, data: BillingProfileIn):
    return await run_operation(request, services.billing_profile_update, data)


# --- Usage (lot L4-A) -----------------------------------------------------------------------------


@bind(router, "hubs.usage.get", "/hubs/usage")
async def usage_get(request, params: Query[UsageGetIn]):
    return await run_operation(request, queries.usage_get, params)


@bind(router, "hubs.usage.series", "/hubs/usage/series")
async def usage_series(request, params: Query[UsageSeriesIn]):
    return await run_operation(request, queries.usage_series, params)


# --- The copies of a business's data (PLAN-DB, round 2026-10-30, proposal (k)) ----------------------------------


@bind(router, "hubs.data_copy.list", "/hubs/data-copies")
async def data_copy_list(request, params: Query[DataCopyListIn]):
    return await run_operation(request, queries.data_copy_list, params)


@bind(router, "hubs.data_copy.link", "/hubs/data-copies/link")
async def data_copy_link(request, params: Query[DataCopyLinkIn]):
    return await run_operation(request, queries.data_copy_link, params)
