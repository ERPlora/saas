"""Who may do what on a business, by role (round 17 §2.7): the owner everything (plan, billing, transfer,
delete), an administrator the team and the settings, a manager or an employee only «Open»; somebody
without access (a stranger, or an invitation not answered yet) does not learn the business exists.

One table for every operation on a business, so a new operation cannot slip in without its row.
Ported in spirit from ERPlora/saas ``hubs/main/tests/test_permissions.py`` (``IsHubMember``,
``IsHubAdmin``: the part of the account plane) and ``test_member_cannot_act_as_admin.py`` (a member
reaches neither the payer nor the plan).
"""

import pytest
from live.errors import NotFound, OperationError, PermissionDenied

from hubs import queries, services
from hubs.schemas import (
    BillingProfileGetIn,
    BusinessAddressIn,
    BillingProfileIn,
    BusinessDeleteIn,
    BusinessOpenIn,
    BusinessUpdateIn,
    ByIdIn,
    MemberInviteIn,
    MemberListIn,
    MemberRoleIn,
    OwnershipTransferIn,
    UsageGetIn,
    UsageSeriesIn,
)
from hubs.tests.conftest import ctx_for, member_of

pytestmark = pytest.mark.django_db

OK, DENIED, HIDDEN = "ok", 403, 404
ROLES = ["owner", "admin", "manager", "employee", "invitee", "stranger"]


def call(name, hub, team):
    """Run the operation ``name`` on ``hub``; a refusal of the domain (409, 422) means it got past the role."""
    employee = member_of(hub, team["employee"]).id
    admin = member_of(hub, team["admin"]).id
    invitation = member_of(hub, team["invitee"]).id
    return {
        "business.get": (queries.business_get, ByIdIn(id=hub.id)),
        "business.update": (
            services.business_update,
            BusinessUpdateIn(id=hub.id, name="Renamed"),
        ),
        "business.change_address": (
            services.business_change_address,
            BusinessAddressIn(id=hub.id, slug="casa-manolo"),
        ),
        "business.delete": (
            services.business_delete,
            BusinessDeleteIn(id=hub.id, confirm_name="not the name"),
        ),
        "business.restore": (services.business_restore, ByIdIn(id=hub.id)),
        "business.open": (services.business_open, BusinessOpenIn(id=hub.id)),
        "member.list": (queries.member_list, MemberListIn(hub_id=hub.id)),
        "member.invite": (
            services.member_invite,
            MemberInviteIn(hub_id=hub.id, email="new@example.com"),
        ),
        "member.change_role": (
            services.member_change_role,
            MemberRoleIn(id=employee, role="hub_manager"),
        ),
        "member.remove": (services.member_remove, ByIdIn(id=employee)),
        "member.resend": (services.member_resend, ByIdIn(id=invitation)),
        "member.cancel": (services.member_cancel, ByIdIn(id=invitation)),
        "ownership.transfer": (
            services.ownership_transfer,
            OwnershipTransferIn(hub_id=hub.id, member_id=admin),
        ),
        "billing_profile.get": (
            queries.billing_profile_get,
            BillingProfileGetIn(hub_id=hub.id),
        ),
        "billing_profile.update": (
            services.billing_profile_update,
            BillingProfileIn(hub_id=hub.id, billing_name="Me"),
        ),
        # A night measured, so «nothing yet» (also a 404) never hides what the role decides.
        "usage.get": (queries.usage_get, UsageGetIn(business_id=measured(hub).id)),
        "usage.series": (queries.usage_series, UsageSeriesIn(business_id=hub.id)),
    }[name]


def measured(hub):
    from datetime import UTC, datetime, timedelta

    from hubs.models import HubUsageDaily

    HubUsageDaily.objects.get_or_create(
        hub=hub,
        day=datetime.now(UTC).date() - timedelta(days=1),
        defaults={"s3_bytes": 0, "db_bytes": 0, "active_users_1d": 0, "active_users_30d": 0},
    )
    return hub


MATRIX = {
    #                          owner admin   manager employee invitee stranger
    "business.get": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "business.update": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "business.change_address": (OK, DENIED, DENIED, DENIED, HIDDEN, HIDDEN),
    "business.delete": (OK, DENIED, DENIED, DENIED, HIDDEN, HIDDEN),
    "business.restore": (OK, DENIED, DENIED, DENIED, HIDDEN, HIDDEN),
    "business.open": (OK, OK, OK, OK, HIDDEN, HIDDEN),
    "member.list": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "member.invite": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "member.change_role": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "member.remove": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "member.resend": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "member.cancel": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "ownership.transfer": (OK, DENIED, DENIED, DENIED, HIDDEN, HIDDEN),
    "billing_profile.get": (OK, DENIED, DENIED, DENIED, HIDDEN, HIDDEN),
    "billing_profile.update": (OK, DENIED, DENIED, DENIED, HIDDEN, HIDDEN),
    # The usage of the business (L4-A): who sees its page.
    "usage.get": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    "usage.series": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
}


def outcome(operation, ctx, data):
    try:
        operation(ctx, data)
    except PermissionDenied:
        return DENIED
    except NotFound:
        return HIDDEN
    except OperationError:
        return OK  # past the role: refused by the domain (409, 422)
    return OK


@pytest.mark.parametrize("name", MATRIX)
@pytest.mark.parametrize("role", ROLES)
def test_the_role_decides(business, team, name, role):
    operation, data = call(name, business, team)

    assert (
        outcome(operation, ctx_for(team[role]), data) == MATRIX[name][ROLES.index(role)]
    )


def test_every_operation_on_a_business_has_its_row():
    """The account's own operations (list, invitations, answers, sign-up) are not about a business it may
    not see; every other ``hubs.*`` operation with ``hubs.view``/``hubs.manage`` is in the matrix."""
    from live.operations import registry

    own = {
        "hubs.business.list",
        "hubs.business.create",
        "hubs.business.mark_ready",
        "hubs.business.record_hub_error",
        "hubs.business.notify_people",
        # The platform's (billing writes what Stripe says): ``test_subscription_apply.py``.
        "hubs.subscription.apply",
        # The platform's (the nightly collection): ``test_collect_hub_usage.py``.
        "hubs.usage.record",
        # The platform's (the clock of a suspended business): ``test_suspended_lifecycle.py``.
        "hubs.business.age_suspension",
        "hubs.address.propose",
        "hubs.invitation.list_mine",
        "hubs.invitation.accept",
        "hubs.invitation.decline",
        "hubs.ownership.accept",
        "hubs.ownership.decline",
        "hubs.ownership.cancel",
    }
    on_a_business = {
        name
        for name, op in registry.items()
        if name.startswith("hubs.") and op.permission
    } - own

    assert on_a_business == {f"hubs.{name}" for name in MATRIX}
