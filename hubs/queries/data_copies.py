"""The copies of a business's data the Hub keeps for its owner to download."""

import logging
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import AI, INTERNAL, operation

from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.queries.access_control import Role, access, account_of
from hubs.schemas.data_copies import DataCopyLinkIn, DataCopyLinkOut, DataCopyListIn, DataCopyListOut

logger = logging.getLogger(__name__)


#: What the Hub copies a business's data for (``GET /internal/hubs/{id}/dumps``): its deletion, and before a reset.
DATA_COPY_KINDS = frozenset({"offboarding", "reset"})
#: The longest key of a copy the SaaS takes (its S3 key: ``<hex>/<AAAAMMDDTHHMMSSZ>-<kind>.dump``).
DATA_COPY_ID_MAX = 512


def hub_data_copies(hub_id: UUID) -> dict[str, Any] | None:
    """What the Hub keeps of a business's data: ``{available, copies}``, ``copies`` newest first, each ``{id, kind,
    created_at, bytes, url}`` (``url`` a link of 15 minutes, as the Hub gave it). ``available`` false: the business has
    no database of its own, so it never gets a copy; a Hub that does not say it is taken as able
    to make them. No copies, or a Hub that does not know the business (404): ``copies`` empty. A cancelled business
    answers 200 at ``/internal`` (the 410 is the door of its host), so any other refusal is a fault: ``HubRefused``,
    as ``HubUnavailable`` with the Hub away (both logged). A row out of the contract is left out, and an answer out of
    it is no copy yet; both are logged, never with a link."""
    nothing_yet: dict[str, Any] = {"available": True, "copies": []}
    try:
        answer = hub_client.get_dumps(str(hub_id))
    except HubUnavailable as away:
        logger.warning("hubs.data_copy.hub_unavailable hub=%s %s", hub_id, away)
        raise
    except HubRefused as refused:
        if refused.status == 404:
            logger.warning("hubs.data_copy.hub_refused hub=%s status=404 code=%s", hub_id, refused.code)
            return nothing_yet
        logger.error("hubs.data_copy.hub_refused hub=%s status=%s code=%s", hub_id, refused.status, refused.code)
        raise
    body = answer.body if isinstance(answer.body, dict) else {}
    rows, available = body.get("dumps"), body.get("available", True)
    if not isinstance(rows, list) or not isinstance(available, bool):
        logger.error("hubs.data_copy.bad_answer hub=%s status=%s", hub_id, answer.status)
        return nothing_yet
    if not available:
        return {"available": False, "copies": []}
    copies = []
    for row in rows:
        copy = _data_copy(row)
        if copy is None:
            known = row if isinstance(row, dict) else {}
            logger.error("hubs.data_copy.bad_row hub=%s id=%r kind=%r", hub_id, known.get("id"), known.get("kind"))
            continue
        copies.append(copy)
    return {"available": True, "copies": sorted(copies, key=lambda copy: copy["created_at"], reverse=True)}


def _data_copy(row: Any) -> dict[str, Any] | None:
    """A row of the Hub's list as the contract says it, or ``None``."""
    if not isinstance(row, dict):
        return None
    copy_id, kind, size, created = row.get("id"), row.get("kind"), row.get("bytes"), row.get("created_at")
    try:
        created_at = parse_datetime(created) if isinstance(created, str) else None
    except ValueError:
        created_at = None
    if (
        not isinstance(copy_id, str)
        or not 0 < len(copy_id) <= DATA_COPY_ID_MAX
        or kind not in DATA_COPY_KINDS
        or created_at is None
        or not timezone.is_aware(created_at)
        or type(size) is not int
        or size < 0
    ):
        return None
    url = row.get("url")
    return {"id": copy_id, "kind": kind, "created_at": created_at, "bytes": size, "url": url if isinstance(url, str) else ""}


def _data_copy_unavailable() -> OperationError:
    return OperationError(
        _("The copy cannot be downloaded right now. Try again in a moment."),
        code="hubs.data_copy_unavailable",
        status=503,
    )


@operation(
    "hubs.data_copy.list",
    kind="query",
    permission="hubs.view",
    input=DataCopyListIn,
    output=DataCopyListOut,
    expose_api=True,
    ai=AI(
        description="The copies of a business's data its Hub keeps for its owner to download: when and how big, newest "
        "first; the download itself is on the business's page.",
        asks={
            "en": (
                "do I have a backup of the bar?",
                "when was the last copy of my data?",
                "how big is the last copy of the salon's data?",
            ),
            "es": (
                "¿tengo copia de seguridad del bar?",
                "¿cuándo se hizo la última copia de mis datos?",
                "¿hay copias de los datos de la peluquería?",
                "quiero descargarme los datos de la peluquería",
            ),
        },
    ),
)
def data_copy_list(ctx: OperationContext, data: DataCopyListIn) -> dict[str, Any]:
    """The copies the Hub keeps of the business's data (the panel's «Download the data»): when, which and how big,
    newest first and without their links (``hubs.data_copy.link`` asks for one on each click). Only the owner. With
    the Hub away or no copy yet, an empty list: the page says the copy is not ready yet; ``available`` false, the
    business has no database of its own and never gets one, so the page promises nothing. The Hub refusing (anything
    but a 404): 503 ``hubs.data_copy_unchecked``, and the page says it could not check."""
    user = account_of(ctx)
    hub = access(user, data.business_id, Role.OWNER).hub
    try:
        kept = hub_data_copies(hub.id)
    except HubUnavailable:
        kept = {"available": True, "copies": []}
    except HubRefused:
        raise OperationError(
            _("The copy of the data could not be checked right now. Try again in a moment."),
            code="hubs.data_copy_unchecked",
            status=503,
        ) from None
    return {
        "business_id": hub.id,
        "available": kept["available"],
        "copies": [{key: copy[key] for key in ("id", "kind", "created_at", "bytes")} for copy in kept["copies"]],
    }


@operation(
    "hubs.data_copy.link",
    kind="query",
    permission="hubs.view",
    input=DataCopyLinkIn,
    output=DataCopyLinkOut,
    ai=INTERNAL,  # its answer is a download link for the panel's button
)
def data_copy_link(ctx: OperationContext, data: DataCopyLinkIn) -> dict[str, Any]:
    """A link to download one copy of the business's data, asked to the Hub now (it lasts 15 minutes, so a page left
    open still downloads, and the link in a mail never expires: it leads here). Only the owner, in the owner's
    session: no API key downloads a full copy of every person's data of the business (as none deletes it). A copy the
    Hub no longer keeps: 404 ``hubs.data_copy_gone``; the Hub away, or a link that is no web address: 503
    ``hubs.data_copy_unavailable``."""
    user = account_of(ctx)
    hub = access(user, data.business_id, Role.OWNER).hub
    try:
        kept = hub_data_copies(hub.id)
    except (HubUnavailable, HubRefused):
        raise _data_copy_unavailable() from None
    wanted = next((copy for copy in kept["copies"] if copy["id"] == data.copy_id), None)
    if wanted is None:
        raise NotFound(_("This copy of the data is no longer kept."), code="hubs.data_copy_gone")
    address = urlsplit(wanted["url"])
    if address.scheme not in ("https", "http") or not address.netloc:
        logger.error("hubs.data_copy.bad_link hub=%s copy=%s", hub.id, wanted["id"])
        raise _data_copy_unavailable()
    return {"url": wanted["url"]}
