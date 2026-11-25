"""What the Hub is told about a business (``hubs.services.hub_push.sync_hub``): its registry and its snapshot."""

from typing import Any
from uuid import UUID

from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from fiscal.queries import snapshot_block as verifactu_representation
from hubs.models import CustomDomain, Hub, HubMember, Plan, Subscription
from hubs.models.subscriptions import grace_end
from hubs.queries.access_control import RANK
from hubs.queries.hub_usage import storage_limit_bytes
from hubs.queries.plan_catalog import _effective_plan


#: The snapshot's ``status`` is the commercial one: a business being prepared is active for the Hub's
#: rights.
SNAPSHOT_STATUS = {
    Hub.Status.PREPARING: "active",
    Hub.Status.ACTIVE: "active",
    Hub.Status.PAST_DUE: "past_due",
    Hub.Status.SUSPENDED: "suspended",
}


def hub_registry(hub_id: UUID) -> dict[str, Any]:
    """The body of ``PUT /internal/hubs/{id}``: what the Hub provisions the business with."""
    hub = Hub.objects.select_related("business_type").get(pk=hub_id)
    vertical = hub.business_type.vertical if hub.business_type else ""
    return {
        "id": str(hub.id),
        "slug": hub.slug,
        "name": hub.name,
        "country": hub.country,
        "timezone": hub.timezone,
        "language": hub.language,
        "vertical": vertical or None,
    }


def hub_snapshot(hub_id: UUID) -> dict[str, Any]:
    """The body of ``PUT /internal/hubs/{id}/state``, at the business's state version.

    ``hub_id`` names the hub of the path, which the signature (body only) does not cover; ``slug`` names it
    too. ``verifactu``: the authorisation for ERPlora to file its records as the staff left it
    (``fiscal.queries.snapshot_block``), and nothing of the plan: VeriFactu goes in every plan, Free
    included, so the validated authorisation alone opens the Hub's «live» through ERPlora. ``whatsapp``:
    the business's WhatsApp channel (its number, the month's usage against the plan's allowance and its
    templates at Meta), door 4 of the Hub's ``whatsapp_inbox`` contract (``whatsapp.queries.channel_block``).
    Of ERPlora's own business, its people alone: the rest is not erplora.com's to say.
    """
    from whatsapp.queries import channel_block  # whatsapp reads hubs; hubs reads it only here

    hub = Hub.objects.get(pk=hub_id)
    people = {
        "hub_id": str(hub.id),
        "slug": hub.slug,
        "version": hub.state_version,
        "members": _snapshot_members(hub),
    }
    if hub.is_platform:
        return people
    now = timezone.now()
    subscription = (
        Subscription.objects.select_related("plan", "trial_plan")
        .filter(hub=hub)
        .first()
    )
    plan = _effective_plan(subscription, now)
    items = (
        [item for item in subscription.items.order_by("module_slug") if item.is_live(now)]
        if subscription
        else []
    )
    return {
        **people,
        "status": SNAPSHOT_STATUS.get(hub.status, "suspended"),
        "plan": _snapshot_plan(plan),
        "modules": [
            {
                "id": item.module_slug,
                "source": item.source,
                "valid_until": item.valid_until.isoformat()
                if item.valid_until
                else None,
            }
            for item in items
        ],
        "verifactu": verifactu_representation(hub.id),
        # The business's WhatsApp channel, door 4 of the Hub's whatsapp_inbox contract: the body of its door 3 at the
        # snapshot's version (whatsapp.queries.channel_block).
        "whatsapp": channel_block(hub.id, version=hub.state_version),
        **_snapshot_custom_domain(hub, plan),
        **_snapshot_deadline(hub, subscription),
    }


def _snapshot_members(hub: Hub) -> list[dict[str, str]]:
    """The people of the business who answered, the owner first."""
    members = (
        HubMember.objects.select_related("user")
        .filter(hub=hub, accepted_at__isnull=False)
        .annotate(
            rank=Case(
                *[When(role=role, then=Value(rank)) for role, rank in RANK.items()],
                output_field=IntegerField(),
            )
        )
        .order_by("rank", "joined_at", "id")
    )
    return [
        {
            "user_id": str(member.user_id),
            "email": member.user.email,
            "name": member.user.get_full_name() or member.user.email,
            "role": member.role,
        }
        for member in members
    ]


def _snapshot_custom_domain(hub: Hub, plan: Plan | None) -> dict[str, str]:
    """``custom_domain``: the host the Hub serves the business's website on, once it is proved and if the plan
    includes it. Absent otherwise, which to the Hub means none: the snapshot is whole."""
    if plan is None or not plan.includes_custom_domain:
        return {}
    domain = CustomDomain.objects.filter(hub=hub).first()
    return {"custom_domain": domain.hostname} if domain is not None and domain.in_snapshot else {}


def _snapshot_deadline(hub: Hub, subscription: Subscription | None) -> dict[str, str]:
    """``suspends_on``: while a payment is pending, when the business is suspended unless it is paid (ISO 8601,
    ``grace_end`` of its oldest unpaid invoice). Absent otherwise, which to the Hub means no deadline."""
    since = getattr(subscription, "unpaid_since", None)
    if hub.status != Hub.Status.PAST_DUE or since is None:
        return {}
    return {"suspends_on": grace_end(since).isoformat()}


#: The plan's fields its businesses' snapshots carry (``plan`` of the snapshot): changing one in the admin owes the
#: Hub a newer snapshot of every business on the plan (``services.subscription_sync.owe_plan_rights``). The monthly messages are counted
#: and blocked at by the Hub: 0 = none. ``max_apps`` is how many modules the business may choose to turn on, which
#: the Hub checks when it turns one on: 0 = no limit.
SNAPSHOT_PLAN_FIELDS = (
    "slug",
    "included_level",
    "max_devices",
    "max_users",
    "max_db_connections",
    "statement_timeout_seconds",
    "assistant_messages_per_month",
    "whatsapp_messages_per_month",
    "max_apps",
)


def _snapshot_plan(plan: Plan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    # The space for files its tier includes (the Hub's «Space»): from ``included_level``, already
    # a field above, so a change of tier owes the newer snapshot.
    return {field: getattr(plan, field) for field in SNAPSHOT_PLAN_FIELDS} | {
        "max_storage_bytes": storage_limit_bytes(plan)
    }
