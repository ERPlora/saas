"""A business's own domain (HUBS-F17): what the panel and the hourly check read."""

import logging
from typing import Any
from uuid import UUID

from django.conf import settings
from django.utils import timezone, translation
from live.context import OperationContext
from live.operations import AI, operation

from hubs import domain_checks, edge_client
from hubs.models import CustomDomain, Hub
from hubs.queries.access_control import Role, access, account_of
from hubs.queries.plan_catalog import effective_plan
from hubs.schemas import CustomDomainStatusOut, ByIdIn

logger = logging.getLogger(__name__)


def custom_domain_of(row: CustomDomain, language: str, *, validation: tuple[str, str] | None = None) -> dict[str, Any]:
    """What the panel and the assistant are told of a domain, in ``language``; ``validation`` when ACM just said it."""
    name, value = validation or (row.validation_name, row.validation_value)
    with translation.override(language):
        return {
            "id": row.id,
            "domain": row.hostname,
            "state": row.state,
            "state_label": row.get_state_display(),
            "reason": row.reason,
            "reason_label": row.get_reason_display(),
            "validation": {"name": name, "value": value} if name else None,
            "traffic": {"name": row.hostname, "value": domain_checks.target_of(row.hub_id)},
            "failures": row.failures,
            "checked_at": row.checked_at,
            "activated_at": row.activated_at,
        }


def custom_domain_status(hub: Hub, language: str) -> dict[str, Any]:
    """The answer of the panel's page about ``hub``: whether a domain is offered, and the one it has."""
    row = CustomDomain.objects.filter(hub=hub).first()
    plan = effective_plan(hub.id, timezone.now())
    return {
        "available": settings.CUSTOM_DOMAINS_ENABLED,
        "in_plan": plan is not None and plan.includes_custom_domain,
        "domain": custom_domain_of(row, language, validation=_validation_of(row)) if row is not None else None,
    }


def _validation_of(row: CustomDomain) -> tuple[str, str] | None:
    """ACM's validation record the row does not have yet, for a few seconds: the next check keeps it."""
    if row.state != CustomDomain.State.PENDING or row.validation_name or not row.certificate_arn:
        return None
    if not settings.CUSTOM_DOMAINS_ENABLED:
        return None
    try:
        facts = edge_client.describe_certificate(row.certificate_arn)
    except edge_client.EdgeUnavailable as error:
        logger.warning("hubs.custom_domain.unread domain=%s: %s", row.hostname, error)
        return None
    return facts.validation_name, facts.validation_value


@operation(
    "hubs.custom_domain.get",
    kind="query",
    permission="hubs.view",
    input=ByIdIn,
    output=CustomDomainStatusOut,
    expose_api=True,
    ai=AI(
        description=(
            "Whether a business can connect its own domain to its public website, the one it has, what state it is in "
            "and the two DNS records its owner has to create. Its owner and administrators."
        ),
        asks={
            "en": ("how is my domain doing?", "which DNS records do I have to create for my domain?"),
            "es": ("¿cómo va mi dominio?", "¿qué registros DNS tengo que crear para mi dominio?"),
        },
    ),
)
def custom_domain_get(ctx: OperationContext, data: ByIdIn) -> dict[str, Any]:
    member = access(account_of(ctx), data.id, Role.ADMIN)
    return custom_domain_status(member.hub, ctx.language)


def custom_domain_ids() -> list[UUID]:
    """Every domain the hourly check looks at, the oldest first."""
    return list(CustomDomain.objects.order_by("created_at", "id").values_list("id", flat=True))


def custom_domain_row(domain_id: UUID) -> CustomDomain | None:
    return CustomDomain.objects.select_related("hub").filter(pk=domain_id).first()


def certificates_attached() -> int:
    """The certificates on the shared listener: AWS gives these roles no list of them."""
    return CustomDomain.objects.filter(attached_at__isnull=False).count()


def listener_has_room() -> bool:
    """Whether one more certificate fits under ``CUSTOM_DOMAINS_MAX_CERTIFICATES``."""
    return certificates_attached() < settings.CUSTOM_DOMAINS_MAX_CERTIFICATES
