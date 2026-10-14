"""``seed_taxonomy`` seeds the 12 sectors and the 70 business types, each under its sector.

Ported from ERPlora/saas ``public/catalog/tests/test_seed_taxonomy.py`` (origin/develop). Changed:
``FunctionalUnit``, ``Category`` and ``Subcategory`` are gone (round 16, PLAN §21), so there is no
reorg tree to delete nor units to seed; ``BusinessType`` gains ``vertical``, the template a new hub
of that type is cloned from (PLAN §15.2, §21.4); and the seed runs in the ``saas-migrate`` task on every
deploy, so by default it only creates the rows missing by ``code`` and keeps what staff edited in the
admin, while ``--update`` refreshes every field from ``hubs/data/taxonomy.json``.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

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


def _seed(*args) -> str:
    out = StringIO()
    call_command("seed_taxonomy", *args, stdout=out)
    return out.getvalue()


def _edit_in_the_admin():
    """What staff may change in the admin on rows the seed also carries."""
    hospitality = Sector.objects.create(
        code="hospitality", name_en="Food & Drink", icon="ion:pizza-outline", display_order=99
    )
    BusinessType.objects.create(
        code="bar", name_en="Bar", name_es="Barra", icon="mdi:glass-cocktail", sector=hospitality
    )


def _edited_rows():
    hospitality = Sector.objects.get(code="hospitality")
    bar = BusinessType.objects.get(code="bar")
    return (
        (hospitality.name_en, hospitality.icon, hospitality.display_order),
        (bar.name_es, bar.icon, bar.vertical),
    )


def test_seed_with_update_restores_the_taxonomy():
    # A business type that is not in the seed is kept: hubs may reference it.
    BusinessType.objects.create(code="saas", name_en="SaaS")
    # A business type that is in the seed gets its sector.
    BusinessType.objects.create(code="restaurant", name_en="Restaurant")

    _seed("--update")

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


def test_seed_keeps_what_staff_edited_in_the_admin():
    """Every deploy runs the seed: without ``--update`` it only creates the missing codes."""
    _edit_in_the_admin()

    out = _seed()

    assert _edited_rows() == (
        ("Food & Drink", "ion:pizza-outline", 99),
        ("Barra", "mdi:glass-cocktail", ""),
    )
    assert Sector.objects.count() == 12
    assert BusinessType.objects.filter(sector__isnull=False).count() == 70
    assert "Sectors: 11 created, 1 existing" in out
    assert "Business types: 69 created, 1 existing" in out


def test_seed_with_update_refreshes_every_field_from_the_seed():
    _edit_in_the_admin()

    out = _seed("--update")

    assert _edited_rows() == (
        ("Hospitality & Food", "ion:restaurant-outline", 1),
        ("Bar", "material-symbols:local-bar", "restaurant"),
    )
    assert "Sectors: 11 created, 1 updated" in out
    assert "Business types: 69 created, 1 updated" in out


def test_seed_is_idempotent():
    _seed()
    out = _seed()

    assert Sector.objects.count() == 12
    assert BusinessType.objects.filter(sector__isnull=False).count() == 70
    assert "Sectors: 0 created, 12 existing" in out
    assert "Business types: 0 created, 70 existing" in out


def test_seed_dry_run_makes_no_changes():
    out = _seed("--dry-run")

    assert Sector.objects.count() == 0
    assert BusinessType.objects.count() == 0
    assert "Sectors: 12 to create, 0 existing" in out
    assert "Business types: 70 to create, 0 existing" in out


def test_seed_dry_run_with_update_counts_what_it_would_overwrite():
    _edit_in_the_admin()

    out = _seed("--dry-run", "--update")

    assert _edited_rows() == (
        ("Food & Drink", "ion:pizza-outline", 99),
        ("Barra", "mdi:glass-cocktail", ""),
    )
    assert Sector.objects.count() == 1
    assert "Sectors: 11 to create, 1 to update" in out
    assert "Business types: 69 to create, 1 to update" in out


def test_a_business_type_with_an_unknown_sector_writes_nothing(tmp_path, monkeypatch):
    """The seed is checked before the first write: a broken file leaves no half-seeded taxonomy."""
    broken = tmp_path / "taxonomy.json"
    broken.write_text(
        json.dumps(
            {
                "sectors": [{"code": "retail", "name_en": "Retail"}],
                "activities": [{"code": "kiosk", "name_en": "Kiosk", "sector": "nowhere"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("hubs.management.commands.seed_taxonomy.TAXONOMY_FILE", broken)

    with pytest.raises(CommandError, match="unknown sector 'nowhere'"):
        _seed()

    assert Sector.objects.count() == 0
    assert BusinessType.objects.count() == 0
