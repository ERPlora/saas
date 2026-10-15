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
know. Their addresses come proven, so they never owe the code a new account is mailed, only the sign-in code
every password sign-in mails. Development only: known passwords, so it refuses to run without ``DEBUG``.
Running it again changes nothing (an account seeded before the code existed gets its address proven).

They are the QA users of the root ``.env`` (README «Usuarios QA»): ``QA_OWNER_*``, ``QA_EMPLOYEE_*`` and
``QA_PLATFORM_*`` name them when exported, read on every run; the values above are their defaults, the same
the ``.env`` lists, so both agree by construction.
"""

import os

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


def qa_user(role: str, email: str, password: str) -> tuple[str, str]:
    """``QA_<ROLE>_EMAIL`` and ``QA_<ROLE>_PASSWORD`` of the environment, else ``email`` and ``password``."""
    return os.environ.get(f"QA_{role}_EMAIL", email), os.environ.get(f"QA_{role}_PASSWORD", password)


class Command(BaseCommand):
    help = (
        "Create owner@example.com (password owner), owner of the local hubs a and b, "
        "employee@example.com (password employee), employee of a and b, and "
        "platform@example.com (password platform), superuser of the admin."
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("demo_seed only runs with DEBUG=True")
        owner_email, owner_password = qa_user("OWNER", OWNER_EMAIL, OWNER_PASSWORD)
        employee_email, employee_password = qa_user("EMPLOYEE", EMPLOYEE_EMAIL, EMPLOYEE_PASSWORD)
        platform_email, platform_password = qa_user("PLATFORM", PLATFORM_EMAIL, PLATFORM_PASSWORD)
        owner = account_services.seed_demo_customer(owner_email, owner_password)
        employee = account_services.seed_demo_customer(employee_email, employee_password)
        for slug in HUB_SLUGS:
            services.seed_demo_business(
                slug, {owner: HubMember.Role.OWNER, employee: HubMember.Role.EMPLOYEE}
            )
        account_services.seed_demo_platform_admin(platform_email, platform_password)
        self.stdout.write(
            f"{owner_email} / {owner_password}: owner of {', '.join(HUB_SLUGS)} (customer, no admin)"
        )
        self.stdout.write(
            f"{employee_email} / {employee_password}: employee of {', '.join(HUB_SLUGS)} (customer, no admin)"
        )
        self.stdout.write(
            f"{platform_email} / {platform_password}: platform administrator (admin, no hub)"
        )
