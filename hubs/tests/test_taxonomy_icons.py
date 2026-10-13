"""Every icon of the taxonomy is an Iconify name with its set prefix (working rules §11).

The seed came from the old SaaS with bare ionicons (``restaurant-outline``) and Material names in
its own notation (``material:local_bar``). The public web renders them with its baked icon registry,
which only knows ``<set>:<name>``: a bare name errors visibly in DEBUG. So the seed itself, and every
row ``seed_taxonomy`` leaves in the database, use ``ion:…``, ``material-symbols:…``, ``mdi:…``.
"""

import json
import re
from io import StringIO

import pytest
from django.core.management import call_command

from hubs.management.commands.seed_taxonomy import TAXONOMY_FILE
from hubs.models import BusinessType, Sector

ICONIFY_NAME = re.compile(r"^[a-z0-9-]+:[a-z0-9-]+$")


def seed_rows() -> list[dict]:
    data = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
    return data["sectors"] + data["activities"]


def test_every_icon_of_the_seed_is_an_iconify_name_with_its_set():
    wrong = {
        row["code"]: row.get("icon", "")
        for row in seed_rows()
        if not ICONIFY_NAME.match(row.get("icon", ""))
    }

    assert wrong == {}


def test_the_seed_keeps_the_meaning_of_each_icon():
    """Bare ionicons became ``ion:``, the old ``material:snake_case`` became ``material-symbols:kebab-case``."""
    icons = {row["code"]: row["icon"] for row in seed_rows()}

    assert icons["hospitality"] == "ion:restaurant-outline"
    assert icons["bar"] == "material-symbols:local-bar"
    assert icons["bakery"] == "material-symbols:bakery-dining"
    assert icons["hair_salon"] == "ion:cut-outline"


@pytest.mark.django_db
def test_after_the_seed_every_row_has_an_iconify_icon():
    call_command("seed_taxonomy", stdout=StringIO())

    icons = [
        *Sector.objects.values_list("icon", flat=True),
        *BusinessType.objects.values_list("icon", flat=True),
    ]
    assert len(icons) == 82
    assert [icon for icon in icons if not ICONIFY_NAME.match(icon)] == []


@pytest.mark.django_db
def test_seeding_again_updates_the_icon_of_an_existing_row():
    """Idempotent: a database seeded with the old names is fixed by running the seed again."""
    Sector.objects.create(
        code="hospitality", name_en="Hospitality & Food", icon="restaurant-outline"
    )
    BusinessType.objects.create(code="bar", name_en="Bar", icon="material:local_bar")

    call_command("seed_taxonomy", stdout=StringIO())
    call_command("seed_taxonomy", stdout=StringIO())

    assert Sector.objects.get(code="hospitality").icon == "ion:restaurant-outline"
    assert BusinessType.objects.get(code="bar").icon == "material-symbols:local-bar"
    assert Sector.objects.filter(code="hospitality").count() == 1
