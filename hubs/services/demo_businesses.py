"""The local hubs of ``demo_seed`` adopted as businesses of the SaaS."""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from hubs.models import Hub, HubMember, Subscription
from hubs.queries import plan_catalog
from hubs.queries.access_control import Role
from hubs.services.subscription_sync import sync_plan_modules


def seed_demo_business(slug: str, people: dict) -> Hub:
    """The business of a hub that already runs in the local Hub (``demo_seed``: ``a`` and ``b``), with
    ``people`` (account → ``hub_*`` role) answered on it; creates what is missing, changes nothing else.

    Adopted, not provisioned: active, ready and owing the Hub nothing (as the data migration ``0006`` adopts
    the hubs of the Hub's seed), on the Free plan if it is seeded; named after its address, in Spain.
    """
    roles = set(people.values())
    if not roles <= set(Role.values):
        raise ValueError(f"not customer roles: {sorted(roles - set(Role.values))}")
    with transaction.atomic():
        hub = Hub.objects.filter(slug=slug).first()
        if hub is None:
            now = timezone.now()
            owner = next((user for user, role in people.items() if role == Role.OWNER), None)
            hub = Hub.objects.create(
                slug=slug,
                name=slug,
                country="ES",
                language=owner.language if owner is not None else settings.LANGUAGE_CODE,
                status=Hub.Status.ACTIVE,
                ready_at=now,
                pushed_state_version=1,
                state_version=1,
            )
            plan = plan_catalog.free_plan()
            if plan is not None:
                sync_plan_modules(
                    Subscription.objects.create(
                        hub=hub, plan=plan, status=Subscription.Status.ACTIVE, current_period_start=now
                    ),
                    now,
                )
        for user, role in people.items():
            joined = timezone.now()
            HubMember.objects.get_or_create(
                hub=hub, user=user, defaults={"role": role, "joined_at": joined, "accepted_at": joined}
            )
    return hub
