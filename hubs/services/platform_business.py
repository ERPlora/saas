"""ERPlora's own business, which erplora.com keeps only for its people (HUBS-F38, ``manage.py create_platform_business``)."""

import logging
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, OperationError, PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from accounts.queries import ways_in
from hubs import events, hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.models import Hub, HubMember
from hubs.queries import signup
from hubs.queries.access_control import Role
from hubs.schemas.platform_business import PlatformBusinessIn, PlatformBusinessOut
from hubs.services.creation import TIME_ZONES
from hubs.services.hub_callbacks import system_ctx_for
from hubs.services.hub_push import push_after_commit

logger = logging.getLogger(__name__)

NAME = "ERPlora"
COUNTRY = "ES"


@operation(
    "hubs.platform_business.create",
    kind="command",
    permission="hubs.manage",
    input=PlatformBusinessIn,
    output=PlatformBusinessOut,
    ai=INTERNAL,  # only its command runs it
)
def platform_business_create(ctx: OperationContext, data: PlatformBusinessIn) -> dict:
    """The row of ERPlora's own business, with the id it already has in the Hub and ``data.owner_email`` as its owner.
    Only the platform runs it, once: again with the same id, it changes nothing.

    The Hub is asked about that id first, and only its own hub is taken. The row is born active, with nothing to
    register nor to pay: after the COMMIT the Hub gets its people and nothing else (``hub_sync.hub_snapshot``).
    """
    if ctx.actor != "system":
        raise PermissionDenied(_("Only the platform creates ERPlora's own business."), code="internal_command")
    found = Hub.objects.select_for_update().filter(
        Q(pk=data.id) | Q(is_platform=True) | Q(slug=settings.PLATFORM_HUB_SLUG)
    )
    for hub in found:
        if hub.is_platform and hub.pk == data.id:
            return {"id": hub.id, "slug": hub.slug, "created": False}
        raise Conflict(
            _("Another business has this id or this address, or ERPlora's own is here with another id."),
            code="hubs.platform_business_taken",
        )
    _require_platform_hub(data.id)
    owner = _owner_of(data.owner_email)
    now = timezone.now()
    hub = Hub.objects.create(
        id=data.id,
        slug=settings.PLATFORM_HUB_SLUG,
        name=NAME,
        country=COUNTRY,
        timezone=TIME_ZONES[COUNTRY],
        language=owner.language,
        is_platform=True,
        status=Hub.Status.ACTIVE,
        ready_at=now,
    )
    HubMember.objects.create(hub=hub, user=owner, role=Role.OWNER, joined_at=now, accepted_at=now)
    record_event(system_ctx_for(hub.id), events.BUSINESS_CREATED, {"id": str(hub.id)})
    push_after_commit(hub.id)
    logger.info("hubs.platform_business.created hub=%s owner=%s", hub.id, owner.pk)
    return {"id": hub.id, "slug": hub.slug, "created": True}


def _require_platform_hub(hub_id: UUID) -> None:
    """The Hub has ``hub_id`` as its own hub, ready under its reserved name and no demo; else ``OperationError``."""
    try:
        answer = hub_client.get_hub(str(hub_id))
    except (HubUnavailable, HubRefused) as failed:
        raise OperationError(
            _("The Hub could not say what this id is: %(reason)s") % {"reason": failed},
            code="hubs.platform_hub_unchecked",
            status=503,
        ) from None
    said = answer.body if isinstance(answer.body, dict) else {}
    expected = {"id": str(hub_id), "slug": settings.PLATFORM_HUB_SLUG, "status": "ready", "is_demo": False}
    if answer.status != 200 or any(said.get(key) != value for key, value in expected.items()):
        raise Conflict(
            _("The Hub does not have this id as ERPlora's own business, ready under its name."),
            code="hubs.platform_hub_mismatch",
        )


def _owner_of(email: str):
    """The active account that proved ``email``; none of the staff's, as in any business."""
    owner = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    if owner is None or not ways_in.email_is_proven(owner, owner.email):
        raise Conflict(
            _("No active account with a proven address has this email."), code="hubs.platform_owner_unknown"
        )
    signup.refuse_staff(owner)
    return owner
