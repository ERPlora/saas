"""Deleting a business, and restoring it while its deletion can still be undone."""

from functools import partial

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import AI, operation
from live.outbox import record_event

from hubs import emails, events
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub, HubOwnershipTransfer, Subscription, SubscriptionItem
from hubs.queries import access_control, businesses, data_copies, plan_catalog
from hubs.queries.access_control import Role
from hubs.schemas.businesses import BusinessDeleteIn, BusinessDetailOut
from hubs.schemas.common import ByIdIn
from hubs.services.creation import check_free_quota
from hubs.services.hub_push import Call, push_after_commit
from hubs.services.refusals import business_deleted, refuse_platform_business
from hubs.services.subscription_sync import sync_plan_modules


@operation(
    "hubs.business.delete",
    kind="command",
    permission="hubs.manage",
    input=BusinessDeleteIn,
    output=BusinessDetailOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Deletes a business: it stops opening at once, is kept 90 days and its plan goes back to Free. "
                    "confirm_name is the business's exact name. Only its owner.",
        risk="high",
        asks={
            "en": (
                "delete the test business",
                "remove Bar Manolo, I don't need it anymore",
                "close down my old shop",
                "get rid of Bar Manolo",
            ),
            "es": (
                "borra el negocio de pruebas",
                "elimina Bar Manolo",
                "elimina el local viejo, ya no lo uso",
                "quiero cerrar para siempre la tienda vieja",
            ),
        },
    ),
)
def business_delete(ctx: OperationContext, data: BusinessDeleteIn) -> dict:
    """The owner deletes the business: it stops opening at once, the Hub keeps it 90 days, and the plan goes
    back to Free on the spot (it comes back on Free)."""
    member = access_control.access(access_control.account_of(ctx), data.id, Role.OWNER, lock=True)
    hub = member.hub
    refuse_platform_business(hub)
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    if data.confirm_name.strip().casefold() != hub.name.strip().casefold():
        reason = _("Type the name of the business to delete it.")
        raise InvalidPayload(reason, fields={"confirm_name": reason})
    _delete_business(ctx, hub, member.user, base_url=emails.base_url(ctx.request))
    return businesses.business_detail(member)


def _delete_business(ctx: OperationContext, hub: Hub, owner, *, base_url: str, unpaid: bool = False) -> None:
    """Delete ``hub``: it stops opening at once, the Hub keeps it 90 days, its plan goes back to
    Free (Stripe's subscription ends in billing's next sweep) and its owner hears until when it can be recovered.
    The owner's own deletion and the end of a long suspension (HUBS-F20, ``unpaid``) take this one path."""
    hub.status = Hub.Status.DELETING
    hub.deletion_requested_at = timezone.now()
    hub.pending_hub_call = Call.DELETE
    # Out of the clock of HUBS-F20: recovered, it comes back on Free, with nothing unpaid.
    hub.suspended_at = hub.suspension_warned_at = hub.suspension_final_notice_at = None
    # The mail «the copy of its data is ready» of this deletion is tried afresh.
    hub.data_copy_mail_attempts = 0
    hub.save(
        update_fields=[
            "status",
            "deletion_requested_at",
            "pending_hub_call",
            "data_copy_mail_attempts",
            "suspended_at",
            "suspension_warned_at",
            "suspension_final_notice_at",
            "updated_at",
        ]
    )
    # A subscription Stripe still bills ends: billing's sweep cancels it (hubs never calls Stripe).
    Subscription.objects.filter(hub=hub, cancel_requested_at__isnull=True).exclude(stripe_subscription_id="").update(
        cancel_requested_at=timezone.now()
    )
    _back_to_free(hub)
    SubscriptionItem.objects.filter(subscription__hub=hub, source=SubscriptionItem.Source.PLAN).delete()
    HubOwnershipTransfer.objects.filter(
        hub=hub, status=HubOwnershipTransfer.Status.PENDING
    ).update(status=HubOwnershipTransfer.Status.CANCELLED, resolved_at=timezone.now())
    record_event(ctx, events.BUSINESS_DELETED, {"id": str(hub.id)})
    push_after_commit(hub.id)
    transaction.on_commit(
        partial(_send_deletion, hub, owner, base_url=base_url, unpaid=unpaid),
        robust=True,
    )


def _send_deletion(hub: Hub, owner, *, base_url: str, unpaid: bool) -> None:
    """The deletion mail, after the COMMIT: it leads to the copy of the business's data unless the Hub says the business
    never gets one (``available`` false: no database of its own). The Hub away or refusing keeps the way to it: the page
    itself promises nothing it cannot keep."""
    try:
        data_copy = data_copies.hub_data_copies(hub.id)["available"]
    except (HubUnavailable, HubRefused):
        data_copy = True
    emails.send_deletion(hub, owner, base_url=base_url, unpaid=unpaid, data_copy=data_copy)


def _back_to_free(hub: Hub) -> None:
    plan = plan_catalog.free_plan()
    if plan is None:
        return
    Subscription.objects.filter(hub=hub).update(
        plan=plan,
        trial_plan=None,
        trial_end=None,
        status=Subscription.Status.ACTIVE,
        cancel_at_period_end=False,
        updated_at=timezone.now(),
    )
    for subscription in Subscription.objects.filter(hub=hub):
        sync_plan_modules(subscription)


@operation(
    "hubs.business.restore",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=BusinessDetailOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Recovers a business deleted less than 90 days ago, on the Free plan; only its owner.",
        asks={
            "en": ("bring back the business I deleted", "undo deleting Bar Manolo", "recover my old salon"),
            "es": (
                "recupera el negocio que borré",
                "me he equivocado, devuélveme Bar Manolo",
                "restaura la peluquería borrada",
            ),
        },
    ),
)
def business_restore(ctx: OperationContext, data: ByIdIn) -> dict:
    """The owner recovers a deleted business within its 90 days, on Free."""
    member = access_control.access(access_control.account_of(ctx), data.id, Role.OWNER, lock=True)
    hub = member.hub
    refuse_platform_business(hub)
    if hub.status != Hub.Status.DELETING:
        raise Conflict(
            _("This business is not deleted."), code="hubs.business_not_deleted"
        )
    if hub.purge_after <= timezone.now():
        raise Conflict(
            _("This business was erased for good and cannot be recovered."),
            code="hubs.business_purged",
        )
    check_free_quota(member.user, excluding=hub.id)  # it comes back on Free
    hub.status = Hub.Status.ACTIVE if hub.ready_at else Hub.Status.PREPARING
    hub.deletion_requested_at = None
    # A deletion the Hub never got leaves nothing to restore there: only the (idempotent) registry.
    hub.pending_hub_call = Call.PUT if hub.pending_hub_call == Call.DELETE else Call.RESTORE
    hub.state_version = F("state_version") + 1
    hub.save(
        update_fields=[
            "status",
            "deletion_requested_at",
            "pending_hub_call",
            "state_version",
            "updated_at",
        ]
    )
    hub.refresh_from_db()
    record_event(ctx, events.BUSINESS_RESTORED, {"id": str(hub.id)})
    push_after_commit(hub.id)
    return businesses.business_detail(member)
