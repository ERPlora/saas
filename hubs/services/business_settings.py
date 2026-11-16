"""Changing a business: its name and settings, and its address."""

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation
from live.outbox import record_event

from hubs import events
from hubs.models import Hub
from hubs.queries import access_control, businesses
from hubs.queries.access_control import Role
from hubs.schemas import BusinessAddressIn, BusinessDetailOut, BusinessUpdateIn
from hubs.services.creation import _chosen_slug, _slug_taken
from hubs.services.hub_push import Call, push_after_commit
from hubs.services.refusals import business_deleted


@operation(
    "hubs.business.update",
    kind="command",
    permission="hubs.manage",
    input=BusinessUpdateIn,
    output=BusinessDetailOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Changes the name, country, language or time zone of a business; its owner and administrators.",
        asks={
            "en": (
                "rename the bar to Bar Manolo 2",
                "change the salon's time zone to the Canaries",
                "the café's language should be English",
            ),
            "es": (
                "cámbiale el nombre al bar",
                "pon la peluquería en hora de Canarias",
                "el café tiene que ir en inglés",
            ),
        },
    ),
)
def business_update(ctx: OperationContext, data: BusinessUpdateIn) -> dict:
    """Name, country, language and time zone (the Settings tab): the owner and the administrators. The
    country is read-only once the business is ready (``businesses.country_locked``): a change is the 409
    ``hubs.country_locked``; sending the same one again is no change."""
    member = access_control.access(access_control.account_of(ctx), data.id, Role.ADMIN, lock=True)
    hub = member.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id"})
    changes = {
        field: value for field, value in sent.items() if getattr(hub, field) != value
    }
    if "country" in changes and businesses.country_locked(hub):
        raise Conflict(
            _("The country cannot change once the business is ready: its invoices belong to one country."),
            code="hubs.country_locked",
        )
    if changes:
        for field, value in changes.items():
            setattr(hub, field, value)
        hub.pending_hub_call = hub.pending_hub_call or Call.PUT
        hub.registry_version = F("registry_version") + 1
        hub.save(update_fields=[*changes, "pending_hub_call", "registry_version", "updated_at"])
        record_event(ctx, events.BUSINESS_UPDATED, {"id": str(hub.id)})
        push_after_commit(hub.id)
    return businesses.business_detail(member)


@operation(
    "hubs.business.change_address",
    kind="command",
    permission="hubs.manage",
    input=BusinessAddressIn,
    output=BusinessDetailOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Moves a business to another web address; people must use the new one. Only its owner.",
        risk="high",
        asks={
            "en": (
                "change the bar's web address to barmanolo",
                "I want a different link for my salon",
                "move my shop to a new URL",
            ),
            "es": (
                "cambia la dirección web del bar a barmanolo",
                "quiero otro enlace para la peluquería",
                "cámbiale la URL al negocio",
            ),
        },
    ),
)
def business_change_address(ctx: OperationContext, data: BusinessAddressIn) -> dict:
    """The owner moves the business to another web address (HUBS-F16), checked as the Hub checks it
    (``live.slugs``). The Hub registers it and the snapshot carries it, both pushed after the COMMIT; the jump
    follows it. The address it leaves stays the business's own (``previous_slug``), so no other business takes
    it and receives the old links and QR codes. The same address again changes nothing."""
    member = access_control.access(access_control.account_of(ctx), data.id, Role.OWNER, lock=True)
    hub = member.hub
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    if data.slug == hub.slug:
        return businesses.business_detail(member)
    slug = _chosen_slug(data.slug, excluding=hub.id)
    previous = hub.slug
    hub.slug = slug
    hub.previous_slug = previous
    hub.pending_hub_call = hub.pending_hub_call or Call.PUT
    hub.registry_version = F("registry_version") + 1
    hub.state_version = F("state_version") + 1
    try:
        with transaction.atomic():
            hub.save(
                update_fields=[
                    "slug",
                    "previous_slug",
                    "pending_hub_call",
                    "registry_version",
                    "state_version",
                    "updated_at",
                ]
            )
    except IntegrityError:
        raise _slug_taken() from None  # another business took it between the check and the write
    hub.refresh_from_db()
    record_event(ctx, events.BUSINESS_ADDRESS_CHANGED, {"id": str(hub.id), "slug": slug, "previous_slug": previous})
    push_after_commit(hub.id)
    return businesses.business_detail(member)
