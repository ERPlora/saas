"""``seed_taxonomy`` seeds the 12 sectors and the 70 business types, each under its sector.

Ported from ERPlora/saas ``public/catalog/tests/test_seed_taxonomy.py`` (origin/develop). Changed:
``FunctionalUnit``, ``Category`` and ``Subcategory`` are gone (round 16, PLAN §21), so there is no
reorg tree to delete nor units to seed; ``BusinessType`` gains ``vertical``, the template a new hub
of that type is cloned from (PLAN §15.2, §21.4).
"""

from io import StringIO

import pytest
from django.core.management import call_command

from hubs.models import BusinessType, Sector

pytestmark = pytest.mark.django_db

#: The vertical of each business type that has one; every other type is seeded without one.
VERTICALS = {
    "restaurant": "restaurant",
    "bar": "restaurant",
    "cafeteria": "restaurant",
    "pizzeria": "restaurant",
    "pub": "restaurant",
    "sushi_restaurant": "restaurant",
    "tapas_bar": "restaurant",
    "hair_salon": "hair_salon",
    "barber_shop": "hair_salon",
}


def _seed(*args):
    call_command("seed_taxonomy", *args, stdout=StringIO())


def test_seed_restores_the_taxonomy():
    # A business type that is not in the seed is kept: hubs may reference it.
    BusinessType.objects.create(code="saas", name_en="SaaS")
    # A business type that is in the seed gets its sector.
    BusinessType.objects.create(code="restaurant", name_en="Restaurant")

    _seed()

    assert Sector.objects.count() == 12
    assert Sector.objects.filter(code="hospitality").exists()

    assert BusinessType.objects.get(code="restaurant").sector.code == "hospitality"
    assert BusinessType.objects.get(code="bar").sector.code == "hospitality"
    assert BusinessType.objects.get(code="hair_salon").sector.code == "personal_services"

    assert BusinessType.objects.filter(code="saas").exists()

    # English is the source, Spanish its translation.
    hair_salon = BusinessType.objects.get(code="hair_salon")
    assert (hair_salon.name_en, hair_salon.name_es) == ("Hair Salon", "Peluquería")

    assert BusinessType.objects.count() == 71
    assert BusinessType.objects.filter(sector__isnull=False).count() == 70


def test_seed_sets_the_vertical_of_the_types_that_have_one():
    _seed()

    seeded = dict(BusinessType.objects.exclude(vertical="").values_list("code", "vertical"))
    assert seeded == VERTICALS


def test_seed_is_idempotent():
    _seed()
    _seed()

    assert Sector.objects.count() == 12
    assert BusinessType.objects.filter(sector__isnull=False).count() == 70


def test_seed_dry_run_makes_no_changes():
    out = StringIO()
    call_command("seed_taxonomy", "--dry-run", stdout=out)

    assert Sector.objects.count() == 0
    assert BusinessType.objects.count() == 0
    assert "12 sectors" in out.getvalue() and "70 business types" in out.getvalue()
