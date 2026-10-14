"""The accounts and businesses the panel's specs open (launch, businesses, business, invitation).

``uv run python tests/e2e/panel/panel_seed.py seed|clear`` from saas-next/, against the local database
of ``.env`` (development only: known passwords, refused without ``DEBUG``). ``seed`` starts from
``clear``, so a run always finds the same rows; ``clear`` removes every account ``e2e-*@example.com``
and every business one of them owns (also the ones a spec created through the panel).

Rows are written with the ORM, not through the operations: nothing is pushed to the Hub (the specs
play the Hub's part, e.g. its signed ``ready`` callback). Every account's password is ``e2e-panel``.

- ``e2e-first``: no business, no invitation (the launcher's sign-up).
- ``e2e-one``: one active business, Panadería López (Free plan, trying Starter).
- ``e2e-several``: Panadería López (owner, last opened; Carlos admin, Marta manager, Ana employee and
  an invitation to Jorge), Peluquería Ana (manager, Carlos owns it), Bar La Plaza (owner, payment
  pending), Café Central (owner, being prepared) and an invitation to Bar Norte from Carlos.
- ``e2e-invited``: no business and an invitation to Peluquería Ana from Carlos.
- ``e2e-carlos``: owner of Peluquería Ana and Bar Norte, admin of Panadería López.
- ``e2e-creator``: nothing, for the spec that creates a business through the panel.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
PASSWORD = "e2e-panel"
DOMAIN = "@example.com"
PREFIX = "e2e-"

ACCOUNTS = {
    "e2e-first": ("Laura", "Martín"),
    "e2e-one": ("Laura", "Martín"),
    "e2e-several": ("Laura", "Martín"),
    "e2e-invited": ("Laura", "Martín"),
    "e2e-carlos": ("Carlos", "Ruiz"),
    "e2e-marta": ("Marta", "Gil"),
    "e2e-ana": ("Ana", "Torres"),
    "e2e-jorge": ("", ""),
    "e2e-creator": ("Laura", "Martín"),
}


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from accounts.models import HubMembership
    from hubs.models import BillingProfile, Hub, HubMember

    users = get_user_model().objects.filter(
        email__startswith=PREFIX, email__endswith=DOMAIN
    )
    owned = HubMember.objects.filter(
        user__in=users, role=HubMember.Role.OWNER
    ).values_list("hub_id", flat=True)
    hubs = Hub.objects.filter(Q(slug__startswith=PREFIX) | Q(pk__in=list(owned)))
    slugs = list(hubs.values_list("slug", flat=True))
    profiles = list(hubs.values_list("billing_profile_id", flat=True))
    hubs.delete()
    BillingProfile.objects.filter(Q(pk__in=profiles) | Q(owner__in=users)).delete()
    HubMembership.objects.filter(Q(hub_slug__in=slugs) | Q(user__in=users)).delete()
    users.delete()



def main(action: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("panel_seed.py only runs with DEBUG=True")
    with transaction.atomic():
        clear()
        if action == "seed":
            _seed()
    print(f"{action}: panel e2e accounts")


def _seed() -> None:
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from accounts.models import HubMembership
    from hubs.models import BillingProfile, Hub, HubMember, Plan, Subscription

    now = timezone.now()
    users = {}
    for local, (first, last) in ACCOUNTS.items():
        user = get_user_model().objects.create_user(
            email=f"{local}{DOMAIN}", password=PASSWORD
        )
        user.first_name, user.last_name, user.language = first, last, "en"
        user.save(update_fields=["first_name", "last_name", "language"])
        users[local] = user
    free = Plan.objects.get(slug="free")
    starter = Plan.objects.get(slug="starter")

    def business(
        slug, name, owner, *, status=Hub.Status.ACTIVE, plan=free, trial=None, error=""
    ):
        profile = BillingProfile.objects.create(
            owner=users[owner], billing_email=users[owner].email, billing_country="ES"
        )
        hub = Hub.objects.create(
            slug=f"{PREFIX}{slug}",
            name=name,
            country="ES",
            timezone="Europe/Madrid",
            language="es",
            billing_profile=profile,
            status=status,
            ready_at=None
            if status == Hub.Status.PREPARING
            else now - timedelta(days=200),
            last_hub_error=error,
        )
        Subscription.objects.create(
            hub=hub,
            plan=plan,
            trial_plan=trial,
            status=Subscription.Status.TRIALING
            if trial
            else Subscription.Status.ACTIVE,
            current_period_start=now - timedelta(days=10),
            trial_start=now - timedelta(days=1) if trial else None,
            trial_end=now + timedelta(days=14) if trial else None,
        )
        join(hub, owner, HubMember.Role.OWNER)
        return hub

    def join(hub, local, role, *, opened=None, invited_by=None):
        HubMember.objects.create(
            hub=hub,
            user=users[local],
            role=role,
            joined_at=now - timedelta(days=30),
            accepted_at=now - timedelta(days=30),
            last_opened_at=opened,
            invited_by=users[invited_by] if invited_by else None,
        )
        if hub.status != Hub.Status.DELETING:
            HubMembership.objects.create(
                user=users[local], hub_slug=hub.slug, role=role
            )

    def invite(hub, local, role, by):
        HubMember.objects.create(
            hub=hub,
            user=users[local],
            role=role,
            invited_by=users[by],
            invited_at=now - timedelta(days=2),
            invitation_expires_at=now + timedelta(days=5),
            joined_at=now - timedelta(days=2),
            accepted_at=None,
        )

    # e2e-one: a single active business, on Free trying Starter.
    business("one-panaderia", "Panadería López", "e2e-one", trial=starter)

    # Carlos's businesses.
    ana = business("peluqueria-ana", "Peluquería Ana", "e2e-carlos")
    norte = business("bar-norte", "Bar Norte", "e2e-carlos")

    # e2e-several: four businesses in four states, the bakery opened last.
    bakery = business("panaderia-lopez", "Panadería López", "e2e-several", plan=starter)
    bakery_owner = HubMember.objects.get(hub=bakery, role=HubMember.Role.OWNER)
    bakery_owner.last_opened_at = now - timedelta(hours=2)
    bakery_owner.save(update_fields=["last_opened_at"])
    join(
        bakery,
        "e2e-carlos",
        HubMember.Role.ADMIN,
        opened=now - timedelta(hours=3),
        invited_by="e2e-several",
    )
    join(
        bakery,
        "e2e-marta",
        HubMember.Role.MANAGER,
        opened=now - timedelta(days=1),
        invited_by="e2e-several",
    )
    join(
        bakery,
        "e2e-ana",
        HubMember.Role.EMPLOYEE,
        opened=now - timedelta(days=5),
        invited_by="e2e-several",
    )
    invite(bakery, "e2e-jorge", HubMember.Role.EMPLOYEE, "e2e-several")
    join(ana, "e2e-several", HubMember.Role.MANAGER, invited_by="e2e-carlos")
    business(
        "bar-la-plaza",
        "Bar La Plaza",
        "e2e-several",
        status=Hub.Status.PAST_DUE,
        plan=starter,
    )
    business("cafe-central", "Café Central", "e2e-several", status=Hub.Status.PREPARING)
    invite(norte, "e2e-several", HubMember.Role.EMPLOYEE, "e2e-carlos")

    # e2e-invited: nothing of its own, one invitation.
    invite(ana, "e2e-invited", HubMember.Role.MANAGER, "e2e-carlos")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "clear"}:
        sys.exit("usage: panel_seed.py seed|clear")
    main(sys.argv[1])
