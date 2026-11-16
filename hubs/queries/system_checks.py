"""What the system checks of hubs read (``hubs.checks``)."""

from datetime import datetime

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Q

from hubs.models import HubMember
from hubs.queries.access_control import LISTED
from hubs.queries.invitations import _waiting_invitations


def tables_migrated() -> bool:
    """Whether accounts and hubs have no migration left to apply, so their tables can be read (the database checks of
    ``hubs.checks`` run in ``migrate`` too, before the tables are there)."""
    executor = MigrationExecutor(connection)
    targets = [
        node
        for node in executor.loader.graph.leaf_nodes()
        if node[0] in ("accounts", "hubs")
    ]
    return not executor.migration_plan(targets)


#: An account of ERPlora's staff on a business: ``(email, slug, "member" | "invited")``.
StaffOnABusiness = tuple[str, str, str]


def staff_on_businesses(now: datetime) -> list[StaffOnABusiness]:
    """Every account of ERPlora's staff (``is_staff`` or ``is_superuser``) that is also on a business, as
    ``accounts.services.account_businesses.on_a_business`` sees it: a member of one not deleted (one in its days of
    recovery too, which a restore gives back) or invited to one (``_waiting_invitations``). By email, then slug. The
    doors refuse it; the system check ``hubs.W002`` names the ones already on a business before (``hubs.checks``)."""
    staff = Q(user__is_staff=True) | Q(user__is_superuser=True)
    members = HubMember.objects.filter(staff, accepted_at__isnull=False, hub__status__in=LISTED)
    invited = _waiting_invitations(now).filter(staff)
    found = {(email, slug, "member") for email, slug in members.values_list("user__email", "hub__slug")}
    found |= {(email, slug, "invited") for email, slug in invited.values_list("user__email", "hub__slug")}
    return sorted(found)
