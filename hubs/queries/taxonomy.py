"""The sectors and business types a business belongs to, as the sign-up and the industry pages read them."""

from typing import Any

from live.context import OperationContext
from live.operations import AI, operation

from hubs.models import BusinessType, Sector
from hubs.retired_codes import current_business_type_code
from hubs.schemas import BusinessTypeListIn, BusinessTypeListOut, SectorListIn, SectorListOut


def _entry(row: Sector | BusinessType, language: str) -> dict[str, Any]:
    return {
        "code": row.code,
        "name": row.name(language),
        "description": row.description(language),
        "icon": row.icon,
        "color": row.color,
        "updated_at": row.updated_at,
    }


@operation(
    "hubs.sector.list",
    kind="query",
    permission=None,
    input=SectorListIn,
    output=SectorListOut,
    expose_api=True,
    ai=AI(
        description="The sectors a business can belong to (hospitality, beauty…), to choose its type.",
        asks={
            "en": (
                "which sectors can a business be in?",
                "is retail one of the sectors?",
                "what industries do you cover?",
            ),
            "es": ("¿qué sectores hay?", "¿estáis para comercio o solo hostelería?", "¿a qué sectores os dedicáis?"),
        },
    ),
)
def sector_list(ctx: OperationContext, data: SectorListIn) -> dict[str, Any]:
    """The active sectors, by their display order."""
    sectors = Sector.objects.filter(is_active=True).order_by("display_order", "code")
    return {"sectors": [_entry(sector, ctx.language) for sector in sectors]}


@operation(
    "hubs.business_type.list",
    kind="query",
    permission=None,
    input=BusinessTypeListIn,
    output=BusinessTypeListOut,
    expose_api=True,
    ai=AI(
        description="The types of business of each sector (a restaurant, a hair salon…).",
        asks={
            "en": (
                "what kinds of business can I choose?",
                "is there a type for a barbershop?",
                "which types are there in hospitality?",
            ),
            "es": ("¿qué tipos de negocio hay?", "¿hay un tipo para barbería?", "¿qué tipos tenéis de hostelería?"),
        },
    ),
)
def business_type_list(
    ctx: OperationContext, data: BusinessTypeListIn
) -> dict[str, Any]:
    """The active business types by their display order, then code, across sectors (the origin ``catalog``'s
    ``ordering = ["order", "code"]``: ``/industries/`` interleaves them as the seed orders them)."""
    business_types = BusinessType.objects.filter(is_active=True).select_related(
        "sector"
    )
    if data.sector:
        business_types = business_types.filter(sector__code=data.sector)
    ordered = business_types.order_by("display_order", "code")
    return {
        "business_types": [
            {
                **_entry(business_type, ctx.language),
                "sector": _sector_ref(business_type.sector, ctx.language),
                "vertical": business_type.vertical,
            }
            for business_type in ordered
        ]
    }


def _sector_ref(sector: Sector | None, language: str) -> dict[str, str] | None:
    return (
        None if sector is None else {"code": sector.code, "name": sector.name(language)}
    )


def business_type_for(code: str | None) -> BusinessType | None:
    """The active business type of ``code`` (a retired code resolves to its survivor); else «not said»."""
    if not code:
        return None
    return BusinessType.objects.filter(
        code=current_business_type_code(code), is_active=True
    ).first()
