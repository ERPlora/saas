"""Reads of hubs: the public taxonomy as operations (PLAN §21.4).

The ninja routes (``test_api.py``), a live subscription and ``public/`` call the same operation,
so the operation itself is what decides who may read and in which language.
"""

import pytest
from django.utils import translation
from live.context import OperationContext, Scope
from live.operations import get

from hubs import queries
from hubs.models import BusinessType, Sector
from hubs.schemas import BusinessTypeListIn, SectorListIn

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
    sectors = queries.sector_list(_anonymous(), SectorListIn())
    business_types = queries.business_type_list(_anonymous(), BusinessTypeListIn())

    assert [row.code for row in sectors.sectors] == ["hospitality"]
    assert [row.code for row in business_types.business_types] == ["restaurant"]


def test_the_language_is_the_callers_not_the_threads(hospitality):
    """A live stream re-runs the query outside the request: the context carries the language."""
    with translation.override("en"):
        sectors = queries.sector_list(_anonymous("es"), SectorListIn())
        business_types = queries.business_type_list(_anonymous("es"), BusinessTypeListIn())

    assert sectors.sectors[0].name == "Hostelería y Alimentación"
    assert (business_types.business_types[0].name, business_types.business_types[0].sector.name) == (
        "Restaurante",
        "Hostelería y Alimentación",
    )


def test_an_inactive_row_is_never_read(hospitality):
    Sector.objects.update(is_active=False)
    BusinessType.objects.update(is_active=False)

    assert queries.sector_list(_anonymous(), SectorListIn()).sectors == []
    assert queries.business_type_list(_anonymous(), BusinessTypeListIn()).business_types == []


def test_every_row_says_when_it_last_changed(hospitality):
    """The sitemap of the public web takes ``lastmod`` from it (ISO 8601)."""
    from datetime import datetime

    sectors = queries.sector_list(_anonymous(), SectorListIn()).model_dump(mode="json")["sectors"]
    business_types = queries.business_type_list(_anonymous(), BusinessTypeListIn()).model_dump(mode="json")["business_types"]

    assert datetime.fromisoformat(sectors[0]["updated_at"]) == hospitality.updated_at
    restaurant = BusinessType.objects.get(code="restaurant")
    assert datetime.fromisoformat(business_types[0]["updated_at"]) == restaurant.updated_at
