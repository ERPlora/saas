"""The web address of a business: the one its name proposes and whether another business has it."""

import re
from typing import Any
from uuid import UUID

from django.db.models import Q
from django.utils.text import slugify
from live.context import OperationContext
from live.operations import AI, operation
from live.slugs import is_demo_slug, is_reserved_hub_slug, validate_hub_slug

from hubs.models import Hub
from hubs.queries.access_control import account_of, host_of
from hubs.schemas.signup import AddressProposeIn, AddressProposeOut


#: The address of a business whose name slugifies to nothing (emoji, other scripts).
FALLBACK_SLUG = "my-business"
#: Room for the counter within a DNS label.
SLUG_BASE_MAX_LENGTH = 30


def slug_taken(slug: str, excluding: UUID | None = None) -> bool:
    """A business has it, now or as the address it had before (HUBS-F16). ``excluding``: the business that asks,
    whose own addresses are free to it."""
    businesses = Hub.objects.filter(Q(slug=slug) | Q(previous_slug=slug))
    if excluding is not None:
        businesses = businesses.exclude(pk=excluding)
    return businesses.exists()


def base_slug(name: str) -> str:
    """The address a name proposes, always one the Hub accepts (``live.slugs``).

    ``slugify`` keeps ``_``, which no DNS label admits: it becomes ``-``, runs of hyphens collapse and
    none is left at an end (also after the cut). A reserved or too short name gets ``-store``. ``demo-…`` is
    the demo hubs' prefix (``live.slugs``): its hyphen goes, so «Demo Bar» proposes
    ``demobar`` and «Demo» ``demostore``, never the fallback that loses the name.
    """
    base = re.sub(r"-+", "-", slugify(name).replace("_", "-"))[
        :SLUG_BASE_MAX_LENGTH
    ].strip("-")
    if not base:
        return FALLBACK_SLUG
    if is_reserved_hub_slug(base) or len(base) < 3:
        base = f"{base}-store"
    if is_demo_slug(base):
        base = base.replace("-", "", 1)
    return base if is_valid_slug(base) else FALLBACK_SLUG


def is_valid_slug(slug: str) -> bool:
    try:
        validate_hub_slug(slug)
    except ValueError:
        return False
    return True


def free_slug(name: str) -> str:
    """The first free address of ``name``: ``bar-manolo``, ``bar-manolo-2``…"""
    base = base_slug(name)
    taken = set(
        Hub.objects.filter(slug__startswith=base).values_list("slug", flat=True)
    )
    taken |= set(Hub.objects.filter(previous_slug__startswith=base).values_list("previous_slug", flat=True))
    candidate, counter = base, 1
    while candidate in taken or not is_valid_slug(candidate):
        counter += 1
        candidate = f"{base}-{counter}"
    return candidate


@operation(
    "hubs.address.propose",
    kind="query",
    permission="hubs.view",
    input=AddressProposeIn,
    output=AddressProposeOut,
    ai=AI(
        description="The web address proposed for a new business from its name, before creating it.",
        asks={
            "en": (
                "what web address would Bar Manolo get?",
                "suggest a URL for my new café",
                "which link would my new shop have?",
            ),
            "es": (
                "¿qué dirección web le tocaría a Bar Manolo?",
                "sugiéreme una URL para el café nuevo",
                "si creo Café Luna, ¿qué dirección web tendría?",
                "¿qué enlace tendría mi nueva tienda?",
            ),
        },
    ),
)
def address_propose(ctx: OperationContext, data: AddressProposeIn) -> dict[str, Any]:
    """The address «Create a business» proposes while the name is typed."""
    account_of(ctx)
    slug = free_slug(data.name)
    return {"slug": slug, "host": host_of(slug)}
