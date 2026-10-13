"""``manage.py demo_seed``: the local accounts of the PoC, one per kind of role.

- ``owner@example.com`` / ``owner``: a customer, owner (``hub_owner``) of the local hubs ``a`` and
  ``b``; no staff, so no admin.
- ``employee@example.com`` / ``employee``: a customer, employee (``hub_employee``) of ``a`` and ``b``:
  sees the demo's list and detail but manages nothing (DEMO-F06); no staff.
- ``platform@example.com`` / ``platform``: the platform administrator (superuser of the admin);
  member of no hub.

Development only: known passwords, so it refuses to run without ``DEBUG``. Running it again changes
nothing.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts import services
from accounts.models import HubMembership

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "owner"
EMPLOYEE_EMAIL = "employee@example.com"
EMPLOYEE_PASSWORD = "employee"
HUB_SLUGS = ["a", "b"]
PLATFORM_EMAIL = "platform@example.com"
PLATFORM_PASSWORD = "platform"


class Command(BaseCommand):
    help = (
        "Create owner@example.com (password owner), owner of the local hubs a and b, "
        "employee@example.com (password employee), employee of a and b, and "
        "platform@example.com (password platform), superuser of the admin."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("demo_seed only runs with DEBUG=True")
        services.seed_demo_owner(OWNER_EMAIL, OWNER_PASSWORD, HUB_SLUGS)
        services.seed_demo_member(EMPLOYEE_EMAIL, EMPLOYEE_PASSWORD, HUB_SLUGS, HubMembership.Role.EMPLOYEE)
        services.seed_demo_platform_admin(PLATFORM_EMAIL, PLATFORM_PASSWORD)
        self.stdout.write(f"{OWNER_EMAIL} / {OWNER_PASSWORD}: owner of {', '.join(HUB_SLUGS)} (customer, no admin)")
        self.stdout.write(
            f"{EMPLOYEE_EMAIL} / {EMPLOYEE_PASSWORD}: employee of {', '.join(HUB_SLUGS)} (customer, no admin)"
        )
        self.stdout.write(f"{PLATFORM_EMAIL} / {PLATFORM_PASSWORD}: platform administrator (admin, no hub)")
