"""The Spanish taxonomy of sectors and business types keeps its diacritics (saas#2017).

Ported from ERPlora/saas ``public/catalog/tests/test_taxonomy_diacritics.py`` (origin/develop). The
seed is the list a Spanish shop owner reads to say what their business does (sign-up, industry
pages, ``/api/catalog/business-types``). It reached production ASCII-folded end to end:
«Barberia», «Panaderia / Pasteleria», «Servicios de Automocion».

Two guards, because one of them cannot be complete:

- ``test_the_seed_carries_no_folded_spanish`` runs the closed list of ``hubs.spanish_copy``, which
  also covers the admin door (``Sector.clean()``), but is deliberately not exhaustive: a word whose
  unaccented spelling is a Spanish word of its own (``número``/``numero``) can never go in it.
- ``test_only_the_pinned_entries_carry_no_accent`` closes that hole for the seed: the entries whose
  Spanish text is pure ASCII are pinned by name, so folding any string back fails.

Changed from the original: no functional units (round 16, PLAN §21), and no tests of migration
``catalog.0007``, which repaired the rows already in production: saas-next starts from an empty
database and the seed ships the corrected copy. The eight strings captured from production stay,
as the positive control of the two guards.
"""

import json
import re
import unicodedata
from pathlib import Path

import pytest
from django.apps import apps as registry
from django.core.exceptions import ValidationError

from apps.tests.factories import make_app
from hubs.spanish_copy import find_stripped_diacritics, spanish_copy_complaint

TAXONOMY_FILE = Path(__file__).resolve().parents[1] / "data" / "taxonomy.json"

COLLECTIONS = ("sectors", "activities")
SPANISH_FIELDS = ("name_es", "description_es")
CATALOG_MODELS = {"Sector": "sectors", "BusinessType": "activities"}

#: ``<collection>:<code>:<field>`` of every Spanish string that carries no accent BECAUSE IT NEEDS
#: NONE: «Compras», «Recursos Humanos», «Agencia de Viajes».
ACCENT_FREE_ON_PURPOSE = {
    "sectors:retail:name_es",
    "sectors:personal_services:name_es",
    "sectors:hotels_tourism:name_es",
    "sectors:construction:description_es",
    "sectors:manufacturing:name_es",
    "sectors:professional_services:name_es",
    "sectors:real_estate:name_es",
    "activities:car_dealership:name_es",
    "activities:cleaning_company:name_es",
    "activities:cleaning_company:description_es",
    "activities:construction_company:name_es",
    "activities:construction_company:description_es",
    "activities:home_services:name_es",
    "activities:installer:name_es",
    "activities:maintenance_company:name_es",
    "activities:driving_school:name_es",
    "activities:online_courses:name_es",
    "activities:school:name_es",
    "activities:bar:name_es",
    "activities:catering:name_es",
    "activities:food_delivery:name_es",
    "activities:food_truck:name_es",
    "activities:kebab_shop:name_es",
    "activities:pub:name_es",
    "activities:restaurant:name_es",
    "activities:sushi_restaurant:name_es",
    "activities:tapas_bar:name_es",
    "activities:tapas_bar:description_es",
    "activities:hostel:name_es",
    "activities:hotel:name_es",
    "activities:travel_agency:name_es",
    "activities:transport_company:name_es",
    "activities:food_workshop:name_es",
    "activities:gym:name_es",
    "activities:massage_therapy:name_es",
    "activities:spa:name_es",
    "activities:spa:description_es",
    "activities:tattoo_studio:name_es",
    "activities:it_services:name_es",
    "activities:law_firm:name_es",
    "activities:law_firm:description_es",
    "activities:marketing_agency:name_es",
    "activities:real_estate_agency:name_es",
    "activities:fashion_retail:name_es",
    "activities:pet_shop:name_es",
    "activities:pharmacy:name_es",
    "activities:wholesale_distributor:name_es",
}

#: The entries that carry an «ñ»: one folded inside a string accented elsewhere stays non-ASCII.
CARRIES_ENYE = {
    "activities:car_rental:description_es",
    "activities:pizzeria:description_es",
    "activities:tattoo_studio:description_es",
}

#: A run of letters, so «check-in/out» and «BOM/recetas» split into words, not into noise.
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)


def _fold(text):
    """``text`` stripped of every diacritic, the way the copy reached production."""
    return "".join(
        c
        for c in unicodedata.normalize("NFD", text.replace("ñ", "n").replace("Ñ", "N")).lower()
        if not unicodedata.combining(c)
    )


def _seed():
    return json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))


def _spanish_strings():
    """``(key, text)`` for every translatable Spanish string of the seed."""
    data = _seed()
    for collection in COLLECTIONS:
        for row in data[collection]:
            for field in SPANISH_FIELDS:
                text = row.get(field)
                if text is None:
                    continue
                yield f"{collection}:{row['code']}:{field}", text


def _is_ascii(text):
    return all(ord(char) < 128 for char in text)


def test_the_seed_carries_no_folded_spanish():
    """No ``name_es`` / ``description_es`` spells a word that Spanish writes with a diacritic."""
    folded = {key: find_stripped_diacritics(text) for key, text in _spanish_strings() if find_stripped_diacritics(text)}
    assert folded == {}


def test_only_the_pinned_entries_carry_no_accent():
    """Re-folding any Spanish string makes it pure ASCII, which this set does not allow."""
    plain = {key for key, text in _spanish_strings() if _is_ascii(text)}
    assert plain == ACCENT_FREE_ON_PURPOSE


@pytest.mark.parametrize("collection", COLLECTIONS)
def test_every_row_is_pinned_or_accented(collection):
    """Nothing escapes the two guards above: a row added later is judged the same way."""
    for row in _seed()[collection]:
        for field in SPANISH_FIELDS:
            text = row.get(field)
            if text is None:
                continue
            key = f"{collection}:{row['code']}:{field}"
            accented = any(unicodedata.combining(char) for char in unicodedata.normalize("NFD", text)) or "ñ" in text
            assert accented or key in ACCENT_FREE_ON_PURPOSE, f"{key} carries no accent and is not pinned"


def test_only_the_entries_pinned_here_carry_an_enye():
    """An ñ folded to ``n`` or transliterated to ``ni`` drops its entry out of this set."""
    with_enye = {key for key, text in _spanish_strings() if "ñ" in text or "Ñ" in text}
    assert with_enye == CARRIES_ENYE


def test_the_seed_never_writes_the_same_word_both_ways():
    """Self-consistency: if the file writes «vehículos» once, «vehiculos» is a defect."""
    strings = dict(_spanish_strings())
    accented = {}
    for text in strings.values():
        for word in _WORDS.findall(text):
            if _fold(word) != word.lower():
                accented[_fold(word)] = word
    both_ways = {
        key: (word, accented[word.lower()])
        for key, text in strings.items()
        for word in _WORDS.findall(text)
        if word.lower() in accented and _fold(word) == word.lower()
    }
    assert both_ways == {}


# ── positive control: what production served before saas#2017 ──────────────────────────────
#
# Rows captured from production on 2026-09-11 (the eighth was a functional unit, now gone). Put
# back into the seed, each one has to turn one of the two guards above red: either the closed list
# names a word, or the string is pure ASCII where the pinned set expects an accent.

AS_PRODUCTION_SERVED = {
    "sectors:hospitality:name_es": "Hosteleria y Alimentacion",
    "sectors:personal_services:description_es": "Peluquerias, barberas, spas, gimnasios, masajes",
    "activities:auto_services:name_es": "Servicios de Automocion (ITV, Neumaticos, Lavado)",
    "activities:assembly:name_es": "Linea de Montaje",
    "activities:butcher_shop:description_es": "Carniceria con trazabilidad lotes, despiece, balanza, alergenos",
    "activities:driving_school:description_es": "Autoescuela con agenda practicas, teorico/practico, examenes, flota",
    "activities:car_rental:description_es": (
        "Empresa de alquiler de vehiculos con gestion de flota, sistema de reservas, "
        "seguimiento de danios, seguros y reserva online"
    ),
}


@pytest.mark.parametrize(("key", "served"), sorted(AS_PRODUCTION_SERVED.items()))
def test_the_guards_catch_the_folded_copy_production_served(key, served):
    seeded = dict(_spanish_strings())
    assert key in seeded, f"{key} is no longer in the seed: the control went blind"
    assert served != seeded[key]
    assert find_stripped_diacritics(served) or (_is_ascii(served) and key not in ACCENT_FREE_ON_PURPOSE)


def test_the_complaint_names_each_fix_in_the_case_it_was_typed():
    complaint = spanish_copy_complaint("Peluqueria y barberia")
    assert "«Peluqueria» → «Peluquería»" in complaint
    assert "«barberia» → «barbería»" in complaint


def test_a_word_that_is_spanish_without_its_accent_is_not_flagged():
    """«mas», «publico», «numero» are words of their own: rejecting them would block real copy."""
    assert spanish_copy_complaint("Mas publico y numero de serie") is None
    assert spanish_copy_complaint("") is None


# ── the admin door ─────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_admin_cannot_type_a_folded_spanish_name(model_name):
    row = registry.get_model("hubs", model_name)(code="barber_shop", name_es="Barberia", name_en="Barber Shop")
    with pytest.raises(ValidationError) as raised:
        row.full_clean()
    assert "name_es" in raised.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_admin_cannot_type_a_folded_spanish_description(model_name):
    row = registry.get_model("hubs", model_name)(
        code="barber_shop", name_es="Barbería", name_en="Barber Shop", description_es="Barberia con cola walk-in"
    )
    with pytest.raises(ValidationError) as raised:
        row.full_clean()
    assert "description_es" in raised.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_english_columns_are_not_measured_against_spanish(model_name):
    """«Barber Shop» and «Menu» are English: only the ``_es`` columns are Spanish copy."""
    registry.get_model("hubs", model_name)(
        code="barber_shop", name_en="Menu", name_es="Barbería", description_en="Salon with walk-in queue"
    ).full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_seeded_copy_passes_the_admin_guard(model_name):
    """Closing the loop: what the seed ships is what the admin would accept.

    Its verticals are the ones the Hub's apps build: with the catalog registered, they are known.
    """
    make_app("appointment", verticals=["hair_salon"])
    make_app("table", verticals=["restaurant"])
    for row in _seed()[CATALOG_MODELS[model_name]]:
        fields = {
            "code": row["code"],
            "name_en": row["name_en"],
            "name_es": row["name_es"],
            "description_en": row.get("description_en", ""),
            "description_es": row.get("description_es", ""),
        }
        if model_name == "BusinessType":
            fields["vertical"] = row.get("vertical", "")
        registry.get_model("hubs", model_name)(**fields).full_clean(validate_unique=False)
