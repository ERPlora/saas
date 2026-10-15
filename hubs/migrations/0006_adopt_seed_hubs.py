"""Data: the hubs of the phase-1 seed become businesses, and the jump's access becomes their mirror
(plan 2026-10-13, L1-A2).

Before ``hubs`` existed, a hub was only a slug in ``accounts.HubMembership`` (``demo_seed``, the admin).
From here every one of those slugs is a ``Hub`` with its ``HubMember`` rows, and ``HubMembership`` holds
exactly the answered members of the businesses that still open: ``hubs.services.sync_access`` is its
only writer until the jump reads ``HubMember`` and the table is retired (``hubs/README.md``).

Each slug with memberships and no business becomes one, adopted as it runs in the Hub, never provisioned
again:

- named after its slug, in Spain (``ES``), in its owner's language; ``status`` active and ``ready_at`` now;
  nothing owed to the Hub (``pending_hub_call`` empty, ``pushed_state_version`` = ``state_version`` = 1),
  so ``reconcile_hub_states`` neither registers nor polls it; ``provision_requested_at`` stays empty,
  since the SaaS never asked the Hub to provision it. The Hub learns its id with the next snapshot (the
  nightly ``push_hub_snapshots``), which it adopts with its own ``/internal`` (Hub lane);
- its owner is its ``hub_owner`` membership (the oldest, if several: the others become ``hub_admin``), or
  else the oldest membership, which becomes ``hub_owner`` (a business has one owner);
- one answered ``HubMember`` per membership, joined and accepted when the membership was created;
- a ``Subscription`` on the Free plan if it exists (seeded then by ``sync_hub_plans``, by ``0013`` since
  2026-10-15), as ``hubs.business.create``.

A slug that is no hub's (``live.slugs``: reserved, malformed, the platform host ``hubs``) opened nothing
at the jump (``is_hub_slug``): its rows are deleted. Then every business's mirror is set as
``sync_access`` sets it (a deleted business has none). Idempotent.

Reverse: nothing to undo. The businesses are valid rows of the schema before this migration, so they
stay, and applying it again finds them (and only puts their mirror right).
"""

from django.db import migrations
from django.utils import timezone
from live.slugs import validate_hub_slug

OWNER, ADMIN = "hub_owner", "hub_admin"
#: Statuses whose members no longer enter (``Hub.Status.DELETING``, ``DELETED``).
CLOSED = ("deleting", "deleted")
COUNTRY = "ES"


def _is_hub_slug(slug: str) -> bool:
    try:
        validate_hub_slug(slug)
    except ValueError:
        return False
    return True


def adopt_seed_hubs(apps, schema_editor):
    alias = schema_editor.connection.alias
    HubMembership = apps.get_model("accounts", "HubMembership")
    Hub = apps.get_model("hubs", "Hub")
    HubMember = apps.get_model("hubs", "HubMember")
    Plan = apps.get_model("hubs", "Plan")
    Subscription = apps.get_model("hubs", "Subscription")
    memberships = HubMembership.objects.using(alias)
    known = set(Hub.objects.using(alias).values_list("slug", flat=True))
    free = (
        Plan.objects.using(alias)
        .filter(is_active=True, internal_only=False, price_monthly=0)
        .order_by("display_order")
        .first()
    )
    now = timezone.now()
    for slug in sorted(set(memberships.values_list("hub_slug", flat=True)) - known):
        rows = list(
            memberships.filter(hub_slug=slug)
            .select_related("user")
            .order_by("created_at", "id")
        )
        if not _is_hub_slug(slug):
            memberships.filter(hub_slug=slug).delete()
            continue
        owners = [row for row in rows if row.role == OWNER]
        owner = owners[0] if owners else rows[0]
        hub = Hub.objects.using(alias).create(
            slug=slug,
            name=slug,
            country=COUNTRY,
            language=owner.user.language,
            status="active",
            ready_at=now,
            state_version=1,
            pushed_state_version=1,
        )
        for row in rows:
            role = OWNER if row is owner else (ADMIN if row.role == OWNER else row.role)
            HubMember.objects.using(alias).create(
                hub=hub,
                user_id=row.user_id,
                role=role,
                joined_at=row.created_at,
                accepted_at=row.created_at,
            )
        if free is not None:
            Subscription.objects.using(alias).create(
                hub=hub, plan=free, status="active", current_period_start=now
            )
    for hub in Hub.objects.using(alias).all():
        _mirror(hub, memberships, HubMember.objects.using(alias))


def _mirror(hub, memberships, members) -> None:
    """``hubs.services.sync_access`` on the historical models: the mirror = the answered members."""
    wanted = (
        {}
        if hub.status in CLOSED
        else dict(
            members.filter(hub=hub, accepted_at__isnull=False).values_list(
                "user_id", "role"
            )
        )
    )
    rows = memberships.filter(hub_slug=hub.slug)
    rows.exclude(user_id__in=wanted).delete()
    have = dict(rows.values_list("user_id", "role"))
    for user_id, role in wanted.items():
        if user_id not in have:
            memberships.create(user_id=user_id, hub_slug=hub.slug, role=role)
        elif have[user_id] != role:
            memberships.filter(user_id=user_id, hub_slug=hub.slug).update(role=role)


def keep_the_businesses(apps, schema_editor):
    """The reverse: the businesses and their members stay (see the module's docstring)."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_shared_hub_slug_validator"),
        ("hubs", "0005_session_revocation"),
    ]

    operations = [
        migrations.RunPython(adopt_seed_hubs, keep_the_businesses),
    ]
