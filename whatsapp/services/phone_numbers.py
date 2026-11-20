"""The business's number at Meta.

- ``whatsapp.number.reconnect_needed``: Meta refused the token;
- ``whatsapp.number.renewal`` / ``whatsapp.number.alerted``: the daily renewal of Meta's permission,
  the mark «needs reconnecting» and the owner told once per incident;
- ``whatsapp.number.connect`` / ``whatsapp.number.disconnect``: the number a business connected through Meta's
  window (door 11) and its disconnection (door 12).
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from hubs.models import HubMember
from whatsapp import events, queries
from whatsapp.models import PhoneNumber
from whatsapp.schemas import (
    AlertedIn,
    AlertedOut,
    DisconnectIn,
    NumberConnectIn,
    NumberConnectOut,
    NumberDisconnectOut,
    ReconnectAlert,
    ReconnectIn,
    ReconnectOut,
    RenewalIn,
    RenewalOut,
)
from whatsapp.services.channel_snapshot import announce_channel
from whatsapp.services.platform_actor import PERMISSION

logger = logging.getLogger("whatsapp.services")


@operation(
    "whatsapp.number.reconnect_needed",
    kind="command",
    permission=PERMISSION,
    input=ReconnectIn,
    output=ReconnectOut,
    ai=INTERNAL,  # meta
)
def number_reconnect_needed(ctx: OperationContext, data: ReconnectIn) -> ReconnectOut:
    """Meta refused the business's permission (an expired or withdrawn token): only connecting again fixes it, and
    the Hub shows it from its snapshot."""
    changed = PhoneNumber.objects.filter(hub_id=data.hub_id, is_active=True, needs_reconnect=False).update(
        needs_reconnect=True
    )
    if changed:
        announce_channel(data.hub_id)
        record_event(ctx, events.NUMBER_RECONNECT_NEEDED, {"hub_id": str(data.hub_id)})
    return ReconnectOut(changed=bool(changed))


#: Inside this many days (or past the deadline) the owner is told even without Meta's verdict.
LAST_CALL = timedelta(days=3)


@operation(
    "whatsapp.number.renewal",
    kind="command",
    permission=PERMISSION,
    input=RenewalIn,
    output=RenewalOut,
    ai=INTERNAL,  # scheduled
)
def number_renewal(ctx: OperationContext, data: RenewalIn) -> RenewalOut:
    """Write how a renewal ended: the fresh token and its deadline, or the mark «needs reconnecting» when Meta said
    no (or gave no verdict and the deadline is too close to wait). The owner is to be told the first time in an
    incident: the alert says to whom; ``whatsapp.number.alerted`` notes it once the mail left."""
    number = PhoneNumber.objects.select_for_update().select_related("hub").filter(pk=data.number_id).first()
    if number is None or not number.is_active:
        return RenewalOut(needs_reconnect=False)
    was_marked = number.needs_reconnect
    if data.outcome == "renewed":
        number.access_token = data.token.get_secret_value()
        number.token_expires_at = data.expires_at
        number.needs_reconnect = False
        number.reconnect_alerted_at = None
        number.save(
            update_fields=["access_token", "token_expires_at", "needs_reconnect", "reconnect_alerted_at", "updated_at"]
        )
        if was_marked:
            announce_channel(number.hub_id)
        return RenewalOut(needs_reconnect=False)
    out_of_runway = number.token_expires_at is not None and number.token_expires_at <= timezone.now() + LAST_CALL
    if data.outcome == "unverified" and not out_of_runway:
        return RenewalOut(needs_reconnect=was_marked)
    if not was_marked:
        number.needs_reconnect = True
        number.save(update_fields=["needs_reconnect", "updated_at"])
        announce_channel(number.hub_id)
        record_event(ctx, events.NUMBER_RECONNECT_NEEDED, {"hub_id": str(number.hub_id)})
    if number.reconnect_alerted_at is not None:
        return RenewalOut(needs_reconnect=True)
    owners = HubMember.objects.select_related("user").filter(hub_id=number.hub_id, role=HubMember.Role.OWNER)
    owner = owners.first()
    if owner is None or not owner.user.email:
        logger.error("whatsapp.token.no_owner_to_tell hub_id=%s", number.hub_id)
        return RenewalOut(needs_reconnect=True)
    alert = ReconnectAlert(
        to=owner.user.email,
        language=owner.user.language or settings.LANGUAGE_CODE,
        business=number.hub.name,
        number=number.display_phone,
        slug=number.hub.slug,
    )
    return RenewalOut(needs_reconnect=True, alert=alert)


@operation(
    "whatsapp.number.alerted",
    kind="command",
    permission=PERMISSION,
    input=AlertedIn,
    output=AlertedOut,
    ai=INTERNAL,  # scheduled
)
def number_alerted(ctx: OperationContext, data: AlertedIn) -> AlertedOut:
    """The owner was told: no other mail in this incident."""
    alerted = PhoneNumber.objects.filter(pk=data.number_id, reconnect_alerted_at__isnull=True).update(
        reconnect_alerted_at=timezone.now()
    )
    return AlertedOut(alerted=bool(alerted))


@operation(
    "whatsapp.number.connect",
    kind="command",
    permission=PERMISSION,
    input=NumberConnectIn,
    output=NumberConnectOut,
    ai=INTERNAL,  # meta
)
def number_connect(ctx: OperationContext, data: NumberConnectIn) -> NumberConnectOut:
    """Keep the number Meta just let the business use: its permission and PIN encrypted, active, without the mark
    «needs reconnecting». A number has one owner in the whole platform: one another business had moves here, and
    that business learns it lost it. The business's previous number stops and forgets its permission."""
    now = timezone.now()
    number = PhoneNumber.objects.select_for_update().filter(phone_number_id=data.phone_number_id).first()
    moved_from = number.hub_id if number is not None and number.hub_id != data.hub_id else None
    previous = PhoneNumber.objects.select_for_update().filter(hub_id=data.hub_id, is_active=True)
    for old in previous.exclude(phone_number_id=data.phone_number_id):
        _stop(old, now)
    if number is None:
        number = PhoneNumber(phone_number_id=data.phone_number_id)
    number.hub_id = data.hub_id
    number.display_phone = data.display_phone[:32]
    number.display_name = data.display_name[:200]
    number.waba_id = data.waba_id
    number.business_id = data.business_id
    number.access_token = data.token.get_secret_value()
    number.registration_pin = data.pin.get_secret_value()
    number.is_on_biz_app = data.is_on_biz_app
    number.token_expires_at = data.expires_at
    number.is_active = True
    number.needs_reconnect = False
    number.reconnect_alerted_at = None
    number.connected_at = now
    number.disconnected_at = None
    number.save()
    announce_channel(data.hub_id)
    if moved_from is not None:
        logger.warning("whatsapp.number.moved from_hub_id=%s to_hub_id=%s", moved_from, data.hub_id)
        announce_channel(moved_from)
    record_event(
        ctx,
        events.NUMBER_CONNECTED,
        {
            "hub_id": str(data.hub_id),
            "moved_from": str(moved_from) if moved_from else None,
            "is_on_biz_app": data.is_on_biz_app,
        },
    )
    return NumberConnectOut(moved_from=moved_from)


def _stop(number: PhoneNumber, now) -> None:
    """The number takes and sends nothing more and forgets Meta's permission; its PIN stays, to register it again."""
    number.is_active = False
    number.access_token = ""
    number.needs_reconnect = False
    number.reconnect_alerted_at = None
    number.disconnected_at = now
    number.save(
        update_fields=[
            "is_active", "access_token", "needs_reconnect", "reconnect_alerted_at", "disconnected_at", "updated_at"
        ]
    )


@operation(
    "whatsapp.number.disconnect",
    kind="command",
    permission=PERMISSION,
    input=DisconnectIn,
    output=NumberDisconnectOut,
    ai=INTERNAL,  # hub
)
def number_disconnect(ctx: OperationContext, data: DisconnectIn) -> NumberDisconnectOut:
    """Stop the business's number: what Meta reports of it is discarded from now on and nothing is sent with it.
    Says the account and the permission just forgotten, so the app is unsubscribed at Meta after the COMMIT unless
    another connected number still uses that account."""
    hub = queries.known_hub(data.hub, live=False)
    if hub is None:
        raise queries.unknown_hub()
    number = PhoneNumber.objects.select_for_update().filter(hub=hub, is_active=True).first()
    if number is None:
        return NumberDisconnectOut(disconnected=False)
    token = number.access_token
    _stop(number, timezone.now())
    in_use = PhoneNumber.objects.filter(waba_id=number.waba_id, is_active=True).exists()
    announce_channel(hub.id)
    record_event(ctx, events.NUMBER_DISCONNECTED, {"hub_id": str(hub.id)})
    return NumberDisconnectOut(
        disconnected=True, waba_id=number.waba_id, token=token or None, account_in_use=in_use
    )
