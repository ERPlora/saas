"""The reads of whatsapp: which business a door names, for the Hub's snapshot its WhatsApp channel, and the account
at Meta its templates live in.

``known_hub`` and ``channel_block`` are plain functions called inside the commands of ``services`` (in their
transaction) and by ``hubs.queries`` for the snapshot (the Hub reads the channel only there).
``whatsapp.template.account`` is the read ``gateway`` makes before it calls Meta for a business's templates, and
``whatsapp.number.renewal_due`` the numbers whose permission is renewed today (WHATSAPP-G12).
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from hubs.models import Hub
from hubs.services import LIVE_STATUSES
from whatsapp.models import PhoneNumber, Template, Usage
from whatsapp.schemas import DueNumber, RenewalDueIn, RenewalDueOut, TemplateAccountIn, TemplateAccountOut

#: Only the platform reads and writes here (``services.platform_context``); no account role holds it.
PERMISSION = "whatsapp.manage"

#: What the Hub's channel schema takes (``apps/whatsapp_inbox/schemas.py``): anything else would refuse the whole
#: snapshot, so it travels as the closest it knows.
HUB_CATEGORIES = ("UTILITY", "MARKETING", "AUTHENTICATION")
HUB_HEADER_FORMATS = ("", "TEXT", "IMAGE", "VIDEO", "DOCUMENT", "LOCATION")
HUB_STATUSES = ("APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED")


def known_hub(ref: str, *, live: bool = True) -> Hub | None:
    """The business ``ref`` names, by its slug or its UUID (lowercase, with hyphens, as the Hub sends it).

    ``live``: one that still works (preparing, active, past due or suspended); otherwise also one being deleted,
    whose data can still be forgotten. A purged one, never.
    """
    try:
        key = UUID(ref)
    except ValueError:
        key = None
    # 32 hex digits are a valid slug too: only the UUID's own spelling names it by id.
    named = Q(id=key) if key is not None and str(key) == ref else Q(slug=ref)
    hubs = Hub.objects.filter(named)
    hubs = hubs.filter(status__in=LIVE_STATUSES) if live else hubs.exclude(status=Hub.Status.DELETED)
    return hubs.first()


def channel_block(hub_id: UUID, *, version: int | None = None) -> dict[str, Any]:
    """The business's WhatsApp as the Hub keeps it: door 3's body without ``hub`` (WHATSAPP-G03, WHATSAPP-G05), the
    ``whatsapp`` key of its snapshot (door 4) at ``version`` (the snapshot's; its state version when missing).

    ``templates`` is ``None`` without a connected number (nothing is known of an account at Meta: the Hub keeps its
    own) and the mirror of Meta's otherwise. ``monthly_limit`` is the plan's ``whatsapp_messages_per_month`` (0: the
    plan includes none, and erplora.com refuses every send), ``monthly_usage`` this calendar month's (UTC) sends.
    """
    from hubs import queries as hubs_queries

    now = timezone.now()
    month = now.strftime("%Y-%m")
    if version is None:
        version = Hub.objects.filter(pk=hub_id).values_list("state_version", flat=True).get()
    plan = hubs_queries.effective_plan(hub_id, now)
    number = PhoneNumber.objects.filter(hub_id=hub_id, is_active=True).first()
    used = Usage.objects.filter(hub_id=hub_id, month=month).values_list("used", flat=True).first() or 0
    status = "not_connected" if number is None else "reconnect_needed" if number.needs_reconnect else "connected"
    return {
        "version": version,
        "status": status,
        "phone_number": _e164(number.display_phone) if number else "",
        "display_name": (number.display_name if number else "")[:200],
        "monthly_limit": plan.whatsapp_messages_per_month if plan is not None else 0,
        "monthly_usage": used,
        "usage_month": month,
        "templates": None if number is None else [_hub_template(t) for t in Template.objects.filter(hub_id=hub_id)],
    }


def _e164(display: str) -> str:
    digits = "".join(ch for ch in display if ch.isdigit())
    return f"+{digits}" if 7 <= len(digits) <= 15 and digits[0] != "0" else ""


def _hub_template(template: Template) -> dict[str, Any]:
    examples = [str(example)[:1024] for example in (template.body_examples or [])][:100]
    buttons = [button for button in (template.buttons or []) if isinstance(button, dict)][:10]
    return {
        "name": template.name,
        "language": template.language[:15],
        "category": template.category if template.category in HUB_CATEGORIES else "UTILITY",
        "status": template.status if template.status in HUB_STATUSES else "PENDING",
        "header_format": template.header_format if template.header_format in HUB_HEADER_FORMATS else "",
        "header": template.header[:200],
        "body": template.body[:4096],
        "body_examples": examples,
        "footer": template.footer[:200],
        "buttons": buttons,
        "variables": min(template.variables, 100),
        "rejected_reason": template.rejected_reason[:500],
        "meta_id": template.meta_id[:64],
    }


def unknown_hub() -> NotFound:
    return NotFound("No business the SaaS knows goes by that hub.", code="hub_unknown")


def not_connected() -> Conflict:
    return Conflict("The business has no WhatsApp number connected.", code="whatsapp.not_connected")


@operation(
    "whatsapp.template.account", kind="query", permission=PERMISSION, input=TemplateAccountIn, output=TemplateAccountOut
)
def template_account(ctx: OperationContext, data: TemplateAccountIn) -> TemplateAccountOut:
    """The account at Meta a business's templates live in (its active number's WhatsApp Business account and token)
    and, for ``name`` in ``language``, the template's id at Meta as the mirror knows it."""
    hub_id = data.hub_id
    if data.hub is not None:
        hub = known_hub(data.hub)
        if hub is None:
            raise unknown_hub()
        hub_id = hub.id
    number = PhoneNumber.objects.filter(hub_id=hub_id, is_active=True).first()
    if number is None or not number.access_token:
        raise not_connected()
    meta_id = ""
    if data.name:
        meta_id = (
            Template.objects.filter(hub_id=hub_id, name=data.name, language=data.language)
            .values_list("meta_id", flat=True)
            .first()
        ) or ""
    return TemplateAccountOut(hub_id=hub_id, waba_id=number.waba_id, token=number.access_token, meta_id=meta_id)


@operation(
    "whatsapp.number.renewal_due", kind="query", permission=PERMISSION, input=RenewalDueIn, output=RenewalDueOut
)
def renewal_due(ctx: OperationContext, data: RenewalDueIn) -> RenewalDueOut:
    """The connected numbers whose permission expires within ``window_days`` (or already did), of businesses that
    still work: one that left is not renewed any more. A token that never expires is never due."""
    deadline = timezone.now() + timedelta(days=data.window_days)
    numbers = (
        PhoneNumber.objects.filter(
            is_active=True, token_expires_at__isnull=False, token_expires_at__lte=deadline, hub__status__in=LIVE_STATUSES
        )
        .exclude(access_token="")
        .order_by("token_expires_at")
    )
    return RenewalDueOut(
        numbers=[
            DueNumber(id=number.id, hub_id=number.hub_id, token=number.access_token, expires_at=number.token_expires_at)
            for number in numbers
        ]
    )
