"""A business's own domain as its owner connects or removes it (HUBS-F17)."""

import logging
from functools import partial
from time import sleep
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import AI, operation
from live.outbox import record_event

from base.refusals import fields_refused
from hubs import domain_checks, domain_names, edge_client, events
from hubs.models import CustomDomain, Hub, new_certificate_token
from hubs.queries import access_control, custom_domains, plan_catalog
from hubs.queries.access_control import Role
from hubs.schemas.common import ByIdIn
from hubs.schemas.custom_domains import CustomDomainOut, CustomDomainRequestIn, CustomDomainStatusOut
from hubs.services.custom_domain_checks import _check_custom_domain
from hubs.services.hub_push import bump_state
from hubs.services.refusals import business_deleted, refuse_platform_business

logger = logging.getLogger(__name__)


#: How often the request looks for ACM's validation record, a second apart. It takes some seconds to exist, and asking
#: holds the business's row: past them, the answer has none yet and ``hubs.custom_domain.get`` gives it.
VALIDATION_RECORD_TRIES = 3


def _custom_domains_on() -> None:
    if not settings.CUSTOM_DOMAINS_ENABLED:
        raise Conflict(_("Own domains are not available yet."), code="hubs.custom_domains_off")


#: What ``hubs.domain_names`` and the DNS refuse, with the message of each.
_DOMAIN_REFUSALS = {
    domain_names.Refusal.NOT_A_DOMAIN: ("hubs.custom_domain_invalid", gettext_lazy("Write only the domain, like www.yourbusiness.com.")),
    domain_names.Refusal.OURS: ("hubs.custom_domain_ours", gettext_lazy("That domain belongs to ERPlora. Write your own.")),
    domain_checks.Zone.APEX: (
        "hubs.custom_domain_apex",
        gettext_lazy("A root domain cannot point at ERPlora. Connect www and redirect the root to it at your provider."),
    ),
    domain_checks.Zone.UNREGISTERED: ("hubs.custom_domain_unregistered", gettext_lazy("Nobody has registered that domain yet.")),
}


def _domain_refused(why) -> InvalidPayload:
    code, message = _DOMAIN_REFUSALS[why]
    return fields_refused({"domain": str(message)}, code=code)


def _hostname_of(typed: str) -> str:
    """The domain in the form everybody is given, or the 422 of what the Hub, ACM or the DNS would not take."""
    try:
        hostname = domain_names.normalized(typed)
    except domain_names.DomainRefused as refused:
        raise _domain_refused(refused.reason) from None
    try:
        zone = domain_checks.zone_of(hostname)
    except domain_checks.DnsUnavailable as error:
        # It cannot be told apart now: a root domain has no CNAME to prove itself with, so nothing is promised.
        logger.warning("hubs.custom_domain.zone_unread domain=%s: %s", hostname, error)
        return hostname
    if zone != domain_checks.Zone.SUBDOMAIN:
        raise _domain_refused(zone)
    return hostname


@operation(
    "hubs.custom_domain.request",
    kind="command",
    permission="hubs.manage",
    input=CustomDomainRequestIn,
    output=CustomDomainOut,
    ai=AI(
        description=(
            "Connects a domain of the owner's (www.theirbusiness.com, never a root domain) to the public website of a "
            "business whose plan includes it, and gives the two DNS records to create. Only its owner."
        ),
        asks={
            "en": ("connect www.barmanolo.com to my website", "I want my own domain on the salon's website"),
            "es": ("conecta www.barmanolo.com a mi web", "quiero mi propio dominio en la web de la peluquería"),
        },
    ),
)
def custom_domain_request(ctx: OperationContext, data: CustomDomainRequestIn) -> dict:
    """Keep the domain and ask ACM for its certificate; the hourly check (``check_custom_domains``) does the rest.

    AWS is called inside the transaction, so a domain and its certificate come together: if it rolls back, the
    certificate left in ACM is free, tagged and on nothing. Before the business's row is locked, what the Hub would refuse
    and the DNS: a slow answer holds no other write of the business.
    """
    user = access_control.account_of(ctx)
    hub = access_control.access(user, data.id, Role.OWNER).hub
    refuse_platform_business(hub)
    _custom_domains_on()
    if hub.status in (Hub.Status.DELETING, Hub.Status.DELETED):
        raise business_deleted()
    plan = plan_catalog.effective_plan(hub.id, timezone.now())
    if plan is None or not plan.includes_custom_domain:
        raise Conflict(_("The plan of this business does not include an own domain."), code="hubs.custom_domain_not_in_plan")
    hostname = _hostname_of(data.domain)
    access_control.access(user, data.id, Role.OWNER, lock=True)
    row = CustomDomain.objects.select_for_update().filter(hub=hub).first()
    if row is not None and row.hostname == hostname and row.state in (CustomDomain.State.PENDING, CustomDomain.State.ACTIVE):
        return custom_domains.custom_domain_of(row, ctx.language)
    if row is not None and (row.state != CustomDomain.State.LAPSED or row.certificate_arn):
        raise Conflict(_("This business already has a domain. Remove it first."), code="hubs.custom_domain_exists")
    if CustomDomain.objects.filter(hostname=hostname, proven_at__isnull=False).exclude(hub=hub).exists():
        raise Conflict(_("Another business is connected to this domain."), code="hubs.custom_domain_taken")
    if row is None:
        row = CustomDomain(hub=hub)
    row.hostname = hostname
    row.state = CustomDomain.State.PENDING
    row.reason = CustomDomain.Reason.NONE
    row.certificate_token = new_certificate_token()
    row.validation_name = row.validation_value = ""
    row.save()
    _ask_for_a_certificate(row)
    record_event(ctx, events.CUSTOM_DOMAIN_CHANGED, {"business_id": str(hub.id)})
    return custom_domains.custom_domain_of(row, ctx.language)


def _ask_for_a_certificate(row: CustomDomain) -> None:
    """The certificate of a domain that just came, and its validation record if ACM has it in time. Whatever fails, the
    hourly check tries again with the same token."""
    if not custom_domains.listener_has_room():
        row.reason = CustomDomain.Reason.QUOTA_FULL
        row.save()
        return
    try:
        row.certificate_arn = edge_client.request_certificate(row.hostname, row.certificate_token)
        row.reason = CustomDomain.Reason.CERTIFICATE_PENDING
        row.save()
        for attempt in range(VALIDATION_RECORD_TRIES):
            facts = edge_client.describe_certificate(row.certificate_arn)
            if facts.validation_name:
                row.validation_name, row.validation_value = facts.validation_name, facts.validation_value
                row.save()
                return
            if attempt + 1 < VALIDATION_RECORD_TRIES:
                sleep(1)
    except edge_client.EdgeUnavailable as error:
        logger.error("hubs.custom_domain.aws domain=%s: %s", row.hostname, error)
        if not row.certificate_arn:
            row.reason = CustomDomain.Reason.CERTIFICATE_UNAVAILABLE
            row.save()


@operation(
    "hubs.custom_domain.remove",
    kind="command",
    permission="hubs.manage",
    input=ByIdIn,
    output=CustomDomainStatusOut,
    ai=AI(
        description=(
            "Disconnects the own domain of a business: its website stops being served on it and stays at its address on "
            "erplora.com. Only its owner."
        ),
        asks={
            "en": ("disconnect my domain from the website", "remove www.barmanolo.com from the bar"),
            "es": ("desconecta mi dominio de la web", "quita www.barmanolo.com del bar"),
        },
    ),
)
def custom_domain_remove(ctx: OperationContext, data: ByIdIn) -> dict:
    """The snapshot first: the Hub stops serving it, then the certificate goes, and the row last, which frees the name
    (after the COMMIT, and the hourly check finishes whatever is left)."""
    hub = access_control.access(access_control.account_of(ctx), data.id, Role.OWNER, lock=True).hub
    _custom_domains_on()
    row = CustomDomain.objects.select_for_update().filter(hub=hub).first()
    if row is None:
        raise access_control.not_found()
    if row.state != CustomDomain.State.REMOVING:
        was_in_snapshot = row.in_snapshot
        row.state = CustomDomain.State.REMOVING
        row.save()
        if was_in_snapshot:
            bump_state(hub.id)
        record_event(ctx, events.CUSTOM_DOMAIN_CHANGED, {"business_id": str(hub.id)})
    transaction.on_commit(partial(_finish_removal_quietly, row.id), robust=True)
    return custom_domains.custom_domain_status(hub, ctx.language)


def _finish_removal_quietly(domain_id: UUID) -> None:
    try:
        _check_custom_domain(domain_id)
    except Exception:  # noqa: BLE001 - it already answered; the hourly check finishes it
        logger.exception("hubs.custom_domain.removal_crashed domain=%s", domain_id)
