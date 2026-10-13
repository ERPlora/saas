"""The Spanish copy of the taxonomy is written in Spanish, not copied from English (saas#2027).

Ported from ERPlora/saas ``public/catalog/tests/test_taxonomy_speaks_spanish.py`` (origin/develop).
Six business types served their ``name_es`` / ``description_es`` straight out of the English
column: «Restaurant — Full-service restaurant with kitchen…», under «Pizzería». An accent guard
cannot see it («Tapas Bar» carries no diacritic), so language needs two guards of its own:

- a verbatim copy of the English twin (``name_es == name_en``) reaches the NAMES, with a pinned
  list for the words Spanish spells the same («Bar», «Pub», «Hotel»);
- an English function word («with», «and», «or»…) reaches the DESCRIPTIONS.

Changed from the original: no functional units (round 16, PLAN §21); no tests of migration
``catalog.0008``, which translated the rows already in production (saas-next starts empty and the
seed ships the Spanish); its captured English strings stay as the positive control of the guards;
the list is read through ``GET /api/catalog/business-types`` (ninja, PLAN §21.4).
"""

import json
from io import StringIO
from pathlib import Path

import pytest
from django.apps import apps as registry
from django.core.exceptions import ValidationError
from django.core.management import call_command

from hubs.spanish_copy import english_function_words_in, untranslated_copy_complaint

TAXONOMY_FILE = Path(__file__).resolve().parents[1] / "data" / "taxonomy.json"
COLLECTIONS = ("sectors", "activities")
CATALOG_MODELS = {"Sector": "sectors", "BusinessType": "activities"}
#: The translatable pairs of every row: the Spanish column and the English one it mirrors.
TRANSLATED_PAIRS = (("name_es", "name_en"), ("description_es", "description_en"))
BUSINESS_TYPES = "/api/catalog/business-types"


def _seed():
    return json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))


def _spanish_copy():
    """``(key, spanish, english)`` for every translatable pair of the seed."""
    data = _seed()
    for collection in COLLECTIONS:
        for row in data[collection]:
            for spanish_field, english_field in TRANSLATED_PAIRS:
                spanish = row.get(spanish_field)
                if spanish is None:
                    continue
                yield f"{collection}:{row['code']}:{spanish_field}", spanish, row.get(english_field)


#: ``name_es`` strings equal to ``name_en`` because Spanish spells the word the same way.
SPELLED_THE_SAME_IN_BOTH = {
    "activities:bar:name_es",
    "activities:food_truck:name_es",
    "activities:hotel:name_es",
    "activities:pub:name_es",
}


def test_no_spanish_string_is_a_verbatim_copy_of_the_english_one():
    """Equality both ways: an untranslated row fails, and so does a pin that stopped being true."""
    copied = {key for key, spanish, english in _spanish_copy() if english is not None and spanish == english}
    assert copied == SPELLED_THE_SAME_IN_BOTH


def test_no_spanish_string_uses_an_english_function_word():
    """«with», «and», «or» in a ``_es`` column: the sentence was never translated."""
    in_english = {
        key: sorted(words) for key, spanish, _ in _spanish_copy() if (words := english_function_words_in(spanish))
    }
    assert in_english == {}


def test_the_complaint_names_the_words_that_gave_the_copy_away():
    """The admin has to be able to act on it: the message names each word it objected to."""
    complaint = untranslated_copy_complaint("Tapas bar with shared plates and wine pairing")
    assert complaint is not None
    for word in ("with", "and"):
        assert f"«{word}»" in complaint


def test_spanish_copy_draws_no_complaint():
    assert untranslated_copy_complaint("Bar de tapas con platos para compartir") is None
    assert untranslated_copy_complaint("") is None


@pytest.mark.parametrize("collection", COLLECTIONS)
def test_every_row_carries_the_spanish_columns_the_guards_measure(collection):
    """A row that shipped without ``name_es`` would slip past both guards in silence."""
    missing = [row["code"] for row in _seed()[collection] if not row.get("name_es") or not row.get("name_en")]
    assert missing == []


# ── positive control: what production served before saas#2027 ──────────────────────────────

AS_PRODUCTION_SERVED = {
    "activities:bar:description_es": (
        "Bar with drinks service, tapas, cocktails, and table management for pubs, taverns, and nightlife venues"
    ),
    "activities:cafeteria:description_es": (
        "Coffee shop with specialty beverages, pastries, light meals, and relaxed dining atmosphere"
    ),
    "activities:manufacturing:name_es": "Manufacturing / Factory",
    "activities:manufacturing:description_es": (
        "Manufacturing or factory with bills of materials, work orders, MRP, quality control, and cost tracking"
    ),
    "activities:pub:description_es": "Pub with craft beers, cocktails, and bar snacks",
    "activities:restaurant:name_es": "Restaurant",
    "activities:restaurant:description_es": (
        "Full-service restaurant with kitchen, table management, reservations, and complete dining experience"
    ),
    "activities:tapas_bar:name_es": "Tapas Bar",
    "activities:tapas_bar:description_es": "Tapas bar with shared plates, wine pairing, and casual dining",
}


def _reads_as_english(key, text):
    """True when either guard of this module would flag ``text`` sitting in ``key``."""
    english_twin = {k: en for k, _, en in _spanish_copy()}[key]
    return bool(english_function_words_in(text)) or text == english_twin


@pytest.mark.parametrize("key", sorted(AS_PRODUCTION_SERVED))
def test_the_guards_of_this_module_flag_the_copy_this_issue_is_about(key):
    """Gutting either guard to go green turns this red instead: the English production served is
    caught, and the Spanish the seed ships is not."""
    seeded = {k: es for k, es, _ in _spanish_copy()}
    assert _reads_as_english(key, AS_PRODUCTION_SERVED[key]), f"{key}: the control no longer catches the English"
    assert not _reads_as_english(key, seeded[key]), f"{key}: the translation still reads as English"


# ── the admin door ─────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_admin_cannot_type_an_english_name(model_name):
    row = registry.get_model("hubs", model_name)(code="tapas_bar", name_es="Bar with tapas and wine", name_en="Tapas Bar")
    with pytest.raises(ValidationError) as raised:
        row.full_clean()
    assert "name_es" in raised.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_admin_cannot_type_an_english_description(model_name):
    row = registry.get_model("hubs", model_name)(
        code="restaurant",
        name_es="Restaurante",
        name_en="Restaurant",
        description_es="Full-service restaurant with kitchen and table management",
    )
    with pytest.raises(ValidationError) as raised:
        row.full_clean()
    assert "description_es" in raised.value.message_dict


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_english_columns_still_take_english(model_name):
    """Only the ``_es`` columns are measured: ``_en`` is where the English belongs."""
    registry.get_model("hubs", model_name)(
        code="restaurant",
        name_en="Restaurant",
        name_es="Restaurante",
        description_en="Full-service restaurant with kitchen and table management",
        description_es="Restaurante con cocina y gestión de sala",
    ).full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("model_name", CATALOG_MODELS)
def test_the_spanish_copy_that_borrows_an_english_word_is_still_accepted(model_name):
    """«check-in», «walk-in», «dark kitchen» and «Servicios IT» are how Spanish says it here."""
    registry.get_model("hubs", model_name)(
        code="hotel",
        name_en="Hotel",
        name_es="Servicios IT",
        description_es="Hotel con gestión de habitaciones, reservas, check-in/out y dark kitchen",
    ).full_clean()


# ── the whole way through, by the door a shop owner uses ────────────────────────────────────

THE_SIX = {
    "bar": "Bar",
    "cafeteria": "Cafetería",
    "manufacturing": "Manufactura / Fábrica",
    "pub": "Pub",
    "restaurant": "Restaurante",
    "tapas_bar": "Bar de tapas",
}


def _served_in_spanish(client):
    call_command("seed_taxonomy", stdout=StringIO())
    response = client.get(BUSINESS_TYPES, HTTP_ACCEPT_LANGUAGE="es")
    assert response.status_code == 200
    return {row["code"]: row for row in response.json()["business_types"]}


@pytest.mark.django_db
def test_the_list_a_spanish_shop_owner_reads_is_in_spanish(client):
    served = _served_in_spanish(client)

    assert set(THE_SIX) <= set(served), "the six business types have to be in the list"
    for code, name in THE_SIX.items():
        assert served[code]["name"] == name
        assert not english_function_words_in(served[code]["description"]), (
            f"{code} is served in English: {served[code]['description']!r}"
        )


@pytest.mark.django_db
def test_no_business_type_of_the_whole_list_is_served_in_english(client):
    """And not just the six: the guard is on the list, not on the rows that were reported."""
    in_english = {
        code: sorted(words)
        for code, row in _served_in_spanish(client).items()
        if (words := english_function_words_in(row["name"]) | english_function_words_in(row["description"]))
    }
    assert in_english == {}
