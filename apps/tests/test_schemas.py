"""Inputs of the catalog's reads (spec §5.1): every filter optional, and a ``category`` or a
``premium`` that is not understood is ignored, never a 422: the store's links carry them in the
query string (``/apps/?category=…&premium=0|1``) and an old or mistyped link still lists apps."""

import pytest

from apps.schemas import AppListIn


def test_no_filter_at_all():
    data = AppListIn()

    assert (data.q, data.category, data.premium, data.vertical) == (
        None,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "category", ["sales", "catalog", "people", "restaurant", "organization"]
)
def test_a_known_category_filters(category):
    assert AppListIn(category=category).category == category


@pytest.mark.parametrize("category", ["", "marketing", "SALES", "42"])
def test_an_unknown_category_is_ignored(category):
    assert AppListIn(category=category).category is None


@pytest.mark.parametrize(
    ("premium", "expected"),
    [
        ("1", True),
        ("true", True),
        ("0", False),
        ("false", False),
        (True, True),
        (False, False),
    ],
)
def test_premium_reads_the_store_links(premium, expected):
    assert AppListIn(premium=premium).premium is expected


@pytest.mark.parametrize("premium", ["", "maybe", "2", "paid"])
def test_a_premium_that_is_not_understood_is_ignored(premium):
    assert AppListIn(premium=premium).premium is None


def test_the_search_is_trimmed_and_an_empty_one_is_none():
    assert AppListIn(q="  stock  ").q == "stock"
    assert AppListIn(q="   ").q is None
    assert AppListIn(q="x" * 500).q == "x" * 120


def test_an_empty_vertical_is_none():
    assert AppListIn(vertical=" hair_salon ").vertical == "hair_salon"
    assert AppListIn(vertical="").vertical is None


@pytest.mark.parametrize("field", ["q", "vertical"])
@pytest.mark.parametrize("value", ["\x00", "\x00\x01\x1f", " \t\n\r "])
def test_a_filter_of_only_control_characters_is_none(field, value):
    """psycopg refuses a NUL in a query parameter (``DataError``): ``?q=%00`` was a 500 on a public
    door. Control characters never belong in a search or a vertical id, so they are dropped."""
    assert getattr(AppListIn(**{field: value}), field) is None


@pytest.mark.parametrize("field", ["q", "vertical"])
def test_control_characters_are_dropped_inside_a_filter(field):
    assert getattr(AppListIn(**{field: " st\x00o\x1bck\x07 "}), field) == "stock"


def test_control_characters_are_dropped_before_the_length_is_cut():
    assert AppListIn(q="\x00" * 10 + "x" * 500).q == "x" * 120
    assert AppListIn(q="in stock").q == "in stock"
