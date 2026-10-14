"""``manage.py demo_seed``: the local accounts of the PoC, one per kind of role, and their businesses.

- ``owner@example.com`` / ``owner``: a customer, owner (``hub_owner``) of the local hubs ``a`` and ``b``;
  no staff, so no admin.
- ``employee@example.com`` / ``employee``: a customer, employee (``hub_employee``) of ``a`` and ``b``: sees
  the demo's list and detail but manages nothing (DEMO-F06); no staff.
- ``platform@example.com`` / ``platform``: the platform administrator (superuser of the admin); member of
  no hub.

``a`` and ``b`` already run in the local Hub: they become businesses of the SaaS adopted as they are
(``hubs.services.seed_demo_business``: active, ready, nothing owed to the Hub), and the jump's access is
their mirror (``sync_access``). In ``hubs`` since L1-A2: it seeds businesses, which ``accounts`` does not
know. Development only: known passwords, so it refuses to run without ``DEBUG``. Running it again changes
nothing.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts import services as account_services
from hubs import services
from hubs.models import HubMember

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
        owner = account_services.seed_demo_customer(OWNER_EMAIL, OWNER_PASSWORD)
        employee = account_services.seed_demo_customer(
            EMPLOYEE_EMAIL, EMPLOYEE_PASSWORD
        )
        for slug in HUB_SLUGS:
            services.seed_demo_business(
                slug, {owner: HubMember.Role.OWNER, employee: HubMember.Role.EMPLOYEE}
            )
        account_services.seed_demo_platform_admin(PLATFORM_EMAIL, PLATFORM_PASSWORD)
        self.stdout.write(
            f"{OWNER_EMAIL} / {OWNER_PASSWORD}: owner of {', '.join(HUB_SLUGS)} (customer, no admin)"
        )
        self.stdout.write(
            f"{EMPLOYEE_EMAIL} / {EMPLOYEE_PASSWORD}: employee of {', '.join(HUB_SLUGS)} (customer, no admin)"
        )
        self.stdout.write(
            f"{PLATFORM_EMAIL} / {PLATFORM_PASSWORD}: platform administrator (admin, no hub)"
        )
