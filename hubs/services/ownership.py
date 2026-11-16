"""Handing a business over to another account: the offer, its answer and its cancellation."""

from functools import partial
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import AI, operation
from live.outbox import record_event

from hubs import emails, events
from hubs.models import Hub, HubMember, HubOwnershipTransfer, Subscription
from hubs.queries import access_control, payers
from hubs.queries.access_control import Role
from hubs.schemas import ByIdIn, OwnershipTransferIn, OwnershipTransferOut
from hubs.services.creation import check_free_quota
from hubs.services.hub_push import bump_state, push_after_commit
from hubs.services.people_notices import notify_people
from hubs.services.refusals import business_deleted
from hubs.services.session_revocations import revoke_after_commit


Transfer = HubOwnershipTransfer.Status


def _transfer_out(transfer: HubOwnershipTransfer) -> dict:
    return {
        "id": transfer.id,
        "hub": {"id": transfer.hub.id, "slug": transfer.hub.slug, "name": transfer.hub.name},
        "from_email": transfer.from_email,
        "to_email": transfer.to_email,
        "status": transfer.status,
        "expires_at": transfer.expires_at,
        "resolved_at": transfer.resolved_at,
    }


def _expire_stale(hub: Hub, now) -> None:
    """Move an offer past its window off ``pending``: the one-pending constraint counts rows, not clocks."""
    HubOwnershipTransfer.objects.filter(hub=hub, status=Transfer.PENDING, expires_at__lte=now).update(
        status=Transfer.EXPIRED, resolved_at=now
    )


@operation(
    "hubs.ownership.transfer",
    kind="command",
    permission="hubs.manage",
    input=OwnershipTransferIn,
    output=OwnershipTransferOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Offers a business to one of its members, who has 7 days to accept; the payer does not change and the "
                    "owner stays as administrator.",
        risk="high",
        asks={
            "en": (
                "transfer the bar to Marta",
                "make Luis the owner of the salon",
                "hand over my business to my partner",
            ),
            "es": (
                "pásale el bar a Marta",
                "haz a Luis dueño de la peluquería",
                "quiero traspasar el negocio a mi socio",
            ),
        },
    ),
)
def ownership_transfer(ctx: OperationContext, data: OwnershipTransferIn) -> dict:
    """The owner offers the business to somebody already on it, who answers within 7 days.

    The payer does not move with it; the outgoing owner stays as admin.
    """
    actor = access_control.access(access_control.account_of(ctx), data.hub_id, Role.OWNER, lock=True)
    hub = actor.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    target = HubMember.objects.select_related("user").filter(pk=data.member_id, hub=hub, accepted_at__isnull=False).first()
    if target is None:
        raise Conflict(
            _("Invite this person to the business first: it can only go to somebody already on it."),
            code="hubs.transfer_target_not_member",
        )
    if target.user_id == actor.user_id:
        raise Conflict(_("You already own this business."), code="hubs.transfer_to_self")
    now = timezone.now()
    _expire_stale(hub, now)
    if HubOwnershipTransfer.objects.filter(hub=hub, status=Transfer.PENDING).exists():
        raise Conflict(
            _("There is already a transfer of this business waiting for an answer."), code="hubs.transfer_pending"
        )
    transfer = HubOwnershipTransfer.objects.create(
        hub=hub,
        from_user=actor.user,
        to_user=target.user,
        from_email=actor.user.email,
        to_email=target.user.email,
        expires_at=now + HubOwnershipTransfer.WINDOW,
    )
    record_event(ctx, events.OWNERSHIP_REQUESTED, {"id": str(transfer.id), "hub_id": str(hub.id)})
    notify_people(ctx, events.OWNERSHIP_CHANGED, hub.id, target.user_id)
    transaction.on_commit(
        partial(
            emails.send_ownership_offer,
            transfer,
            base_url=emails.base_url(ctx.request),
            paid_until=payers.paid_until(hub.id),
        ),
        robust=True,
    )
    return _transfer_out(transfer)


def _answer(ctx: OperationContext, transfer_id: UUID, party: str) -> HubOwnershipTransfer:
    """The offer ``transfer_id`` of which the account is the ``party`` (``to_user`` or ``from_user``),
    locked after its hub, still open for an answer. Anybody else gets 404.

    An offer past its window is refused as expired; the refusal writes nothing (one operation, one
    transaction), so the row moves off ``pending`` when the next offer of the business is made, and
    every read already hides it by its clock.
    """
    user = access_control.account_of(ctx)
    hub_id = HubOwnershipTransfer.objects.filter(pk=transfer_id, **{party: user}).values_list("hub_id", flat=True).first()
    if hub_id is None:
        raise NotFound(_("This transfer does not exist or is not yours to answer."))
    Hub.objects.select_for_update().filter(pk=hub_id).first()
    transfer = (
        HubOwnershipTransfer.objects.select_for_update(of=("self",))
        .select_related("hub", "from_user", "to_user")
        .get(pk=transfer_id)
    )
    if transfer.status != Transfer.PENDING:
        raise Conflict(_("This transfer was already answered."), code="hubs.transfer_answered")
    if transfer.is_expired:
        raise Conflict(_("This transfer expired. Ask the owner to send it again."), code="hubs.transfer_expired")
    return transfer


@operation(
    "hubs.ownership.accept",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=OwnershipTransferOut,
    ai=AI(
        description="Accepts the offer to become the owner of a business; the previous owner stays as administrator.",
        asks={
            "en": ("accept ownership of the bar", "yes, I'll take over the salon", "accept the transfer of Café Luna"),
            "es": (
                "acepto quedarme con el bar",
                "acepta el traspaso de la peluquería",
                "sí, quiero ser el dueño del café",
            ),
        },
    ),
)
def ownership_accept(ctx: OperationContext, data: ByIdIn) -> dict:
    """The named recipient takes the business: the two roles swap in one transaction (exactly one owner
    before and after) and nobody leaves it."""
    transfer = _answer(ctx, data.id, "to_user")
    if Subscription.objects.filter(hub=transfer.hub, plan__price_monthly=0).exists():
        check_free_quota(transfer.to_user, excluding=transfer.hub_id)  # it becomes theirs, Free
    incoming = HubMember.objects.select_for_update().filter(hub=transfer.hub, user=transfer.to_user, accepted_at__isnull=False).first()
    outgoing = (
        HubMember.objects.select_for_update()
        .filter(hub=transfer.hub, user_id=transfer.from_user_id, role=Role.OWNER)
        .first()
    )
    if incoming is None:
        raise Conflict(_("You are no longer on this business."), code="hubs.transfer_answered")
    if outgoing is None:
        raise Conflict(
            _("This business already changed hands: ask its current owner to transfer it."), code="hubs.transfer_stale"
        )
    now = timezone.now()
    outgoing.role = Role.ADMIN
    outgoing.save(update_fields=["role"])
    incoming.role = Role.OWNER
    incoming.save(update_fields=["role"])
    transfer.status = Transfer.ACCEPTED
    transfer.resolved_at = now
    transfer.save(update_fields=["status", "resolved_at"])
    # A paid plan stops renewing on the previous payer's card; the new owner keeps it with theirs (HUBS-F28).
    from billing.services import end_renewal_after_hand_over, expire_open_checkouts

    paid_until = end_renewal_after_hand_over(transfer.hub, transfer.to_user)
    # What the previous owner left open in Stripe Checkout can no longer be paid.
    transaction.on_commit(partial(expire_open_checkouts, transfer.hub_id), robust=True)
    bump_state(transfer.hub_id)
    # Both roles changed, and each travels in its Hub session: both sign in again.
    revoke_after_commit(outgoing.user_id, transfer.hub_id)
    revoke_after_commit(incoming.user_id, transfer.hub_id)
    record_event(ctx, events.OWNERSHIP_ACCEPTED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    notify_people(ctx, events.OWNERSHIP_CHANGED, transfer.hub_id, transfer.from_user_id)
    push_after_commit(transfer.hub_id)
    transaction.on_commit(
        partial(
            emails.send_ownership_accepted, transfer, base_url=emails.base_url(ctx.request), paid_until=paid_until
        ),
        robust=True,
    )
    return _transfer_out(transfer)


def _resolve(transfer: HubOwnershipTransfer, status: str) -> None:
    transfer.status = status
    transfer.resolved_at = timezone.now()
    transfer.save(update_fields=["status", "resolved_at"])


@operation(
    "hubs.ownership.decline",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=OwnershipTransferOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Declines the offer to become the owner of a business; nothing changes.",
        asks={
            "en": (
                "decline the ownership of the bar",
                "I don't want to own the salon",
                "reject the transfer from Marta",
            ),
            "es": (
                "rechaza el traspaso del bar",
                "no quiero ser el dueño de la peluquería",
                "dile a Marta que no me quedo con el café",
            ),
        },
    ),
)
def ownership_decline(ctx: OperationContext, data: ByIdIn) -> dict:
    """The named recipient says no: nothing about the business changes."""
    transfer = _answer(ctx, data.id, "to_user")
    _resolve(transfer, Transfer.DECLINED)
    record_event(ctx, events.OWNERSHIP_DECLINED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    notify_people(ctx, events.OWNERSHIP_CHANGED, transfer.hub_id, transfer.from_user_id)
    return _transfer_out(transfer)


@operation(
    "hubs.ownership.cancel",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=OwnershipTransferOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="The owner withdraws an offer of the business nobody answered yet.",
        asks={
            "en": (
                "cancel the transfer of the bar",
                "I changed my mind, don't hand the salon over",
                "withdraw the ownership offer to Marta",
            ),
            "es": (
                "cancela el traspaso del bar",
                "ya no quiero ceder la peluquería",
                "retira la oferta de propiedad a Marta",
            ),
        },
    ),
)
def ownership_cancel(ctx: OperationContext, data: ByIdIn) -> dict:
    """The owner withdraws the offer before it is answered."""
    transfer = _answer(ctx, data.id, "from_user")
    _resolve(transfer, Transfer.CANCELLED)
    record_event(ctx, events.OWNERSHIP_CANCELLED, {"id": str(transfer.id), "hub_id": str(transfer.hub_id)})
    notify_people(ctx, events.OWNERSHIP_CHANGED, transfer.hub_id, transfer.to_user_id)
    return _transfer_out(transfer)
