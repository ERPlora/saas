"""Reads of hubs: the public taxonomy as operations.

The ninja routes (``test_api.py``), a live subscription and ``public/`` call the same operation,
so the operation itself is what decides who may read and in which language.
"""

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.operations import get

from hubs.queries import taxonomy
from hubs.models import BusinessType, Sector
from hubs.schemas.taxonomy import BusinessTypeListIn, SectorListIn

pytestmark = pytest.mark.django_db


def _anonymous(language="en"):
    return OperationContext(scope=Scope("user", "anonymous"), actor=None, language=language)


@pytest.fixture
def hospitality():
    sector = Sector.objects.create(code="hospitality", name_en="Hospitality & Food", name_es="Hostelería y Alimentación")
    BusinessType.objects.create(code="restaurant", name_en="Restaurant", name_es="Restaurante", sector=sector)
    return sector


@pytest.mark.parametrize("name", ["hubs.sector.list", "hubs.business_type.list"])
def test_the_taxonomy_reads_are_open_queries(name):
    """Anyone reads the taxonomy: the sign-up and the industry pages run before any account exists."""
    op = get(name)

    assert (op.kind, op.permission) == ("query", None)


def test_an_anonymous_visitor_reads_both_lists(hospitality):
    sectors = taxonomy.sector_list(_anonymous(), SectorListIn())
    business_types = taxonomy.business_type_list(_anonymous(), BusinessTypeListIn())

    assert [row.code for row in sectors.sectors] == ["hospitality"]
    assert [row.code for row in business_types.business_types] == ["restaurant"]


def test_the_language_is_the_callers_not_the_threads(hospitality):
    """A live stream re-runs the query outside the request: the context carries the language."""
    with translation.override("en"):
        sectors = taxonomy.sector_list(_anonymous("es"), SectorListIn())
        business_types = taxonomy.business_type_list(_anonymous("es"), BusinessTypeListIn())

    assert sectors.sectors[0].name == "Hostelería y Alimentación"
    assert (business_types.business_types[0].name, business_types.business_types[0].sector.name) == (
        "Restaurante",
        "Hostelería y Alimentación",
    )


@pytest.fixture
def mixed_sectors(hospitality):
    """Types of several sectors whose staff order interleaves them, as the seed does."""
    services = Sector.objects.create(code="professional_services", name_en="Professional Services")
    beauty = Sector.objects.create(code="personal_services", name_en="Personal Services")
    for code, name_en, name_es, sector, order in (
        ("hair_salon", "Hair Salon", "Peluquería", beauty, 1),
        ("optician", "Optician", "Óptica", beauty, 2),
        ("accounting_firm", "Accounting Firm", "Gestoría", services, 1),
        ("bar", "Bar", "Bar", hospitality, 1),
        ("ice_cream_shop", "Ice Cream Shop", "", hospitality, 3),
    ):
        BusinessType.objects.create(
            code=code, name_en=name_en, name_es=name_es, sector=sector, display_order=order
        )


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["Accounting Firm", "Bar", "Hair Salon", "Ice Cream Shop", "Optician", "Restaurant"]),
        ("es", ["Bar", "Gestoría", "Ice Cream Shop", "Óptica", "Peluquería", "Restaurante"]),
    ],
)
def test_the_business_types_come_in_alphabetical_order_of_the_callers_language(mixed_sectors, language, expected):
    """A list to choose from: by the name the caller reads, never by the staff's order inside each sector."""
    business_types = taxonomy.business_type_list(_anonymous(language), BusinessTypeListIn()).business_types

    assert [row.name for row in business_types] == expected


def test_one_sector_keeps_the_alphabetical_order(mixed_sectors):
    business_types = taxonomy.business_type_list(_anonymous("es"), BusinessTypeListIn(sector="personal_services"))

    assert [row.code for row in business_types.business_types] == ["optician", "hair_salon"]


def test_an_inactive_row_is_never_read(hospitality):
    Sector.objects.update(is_active=False)
    BusinessType.objects.update(is_active=False)

    assert taxonomy.sector_list(_anonymous(), SectorListIn()).sectors == []
    assert taxonomy.business_type_list(_anonymous(), BusinessTypeListIn()).business_types == []


def test_every_row_says_when_it_last_changed(hospitality):
    """The sitemap of the public web takes ``lastmod`` from it (ISO 8601)."""
    from datetime import datetime

    sectors = taxonomy.sector_list(_anonymous(), SectorListIn()).model_dump(mode="json")["sectors"]
    business_types = taxonomy.business_type_list(_anonymous(), BusinessTypeListIn()).model_dump(mode="json")["business_types"]

    assert datetime.fromisoformat(sectors[0]["updated_at"]) == hospitality.updated_at
    restaurant = BusinessType.objects.get(code="restaurant")
    assert datetime.fromisoformat(business_types[0]["updated_at"]) == restaurant.updated_at
