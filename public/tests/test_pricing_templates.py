"""The templates of ``/pricing/``: the shared UI patterns they use, and a Spanish entry for every message they
and public/pricing.py show."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation

from hubs.models import Plan
from public import pricing
from public.tests.pricing_pages import html_of, make_plan
from public.tests.template_messages import template_messages

pytestmark = [pytest.mark.django_db]

ROOT = Path(settings.BASE_DIR)
PRICING_TEMPLATES = ROOT / "public" / "templates" / "public" / "pricing"
VAT_NOTE = ROOT / "public" / "templates" / "public" / "partials" / "_vat_note.html"
CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"


# --- The shared UI patterns of the pricing page -----------------------------------------------


def source(name: str) -> str:
    return (PRICING_TEMPLATES / name).read_text(encoding="utf-8")


def test_pricing_tables_use_the_shared_surface_without_nested_frames():
    page = source("index.html")

    assert page.count('class="ep-table-surface"') == 3
    assert page.count('class="ep-container ep-section-content"') >= 3
    assert (
        "overflow-x-auto bg-surface border border-surface-3/60 rounded-xl" not in page
    )
    assert 'class="cat ep-table-group"' in page


def test_pricing_faq_uses_the_shared_container():
    faq = (
        source("index.html")
        .split("<!-- FAQ -->", 1)[1]
        .split("<!-- Closing CTA -->", 1)[0]
    )

    assert re.search(r'<section id="faq" class="ep-section--compact[^"]*ep-section--divider">', faq)
    assert '<div class="ep-container ep-section-content">' in faq


SECTION_TAG = re.compile(r'<section\b(?:\s+id="([^"]+)")?\s+class="([^"]*)"')


def page_sections(html: str) -> list[tuple[str, bool]]:
    """The sections of the page's content, in page order: ``(id or "", on the soft surface)``."""
    content = html.split("<!-- PLAN CARDS -->", 1)[1]
    return [(section_id, "ep-section--soft" in classes.split()) for section_id, classes in SECTION_TAG.findall(content)]


def assert_the_surfaces_alternate(sections: list[tuple[str, bool]]) -> None:
    """Plain under the hero, then soft and plain in turn: never two of the same surface side by side."""
    assert [soft for _, soft in sections] == [index % 2 == 1 for index in range(len(sections))], sections


def test_pricing_uses_the_shared_alternating_section_surface(client, seeded):
    """Cards, «More capacity» (soft), the table, the competitors (soft) and the FAQ."""
    sections = page_sections(html_of(client))

    assert [section_id for section_id, _ in sections] == ["", "more-capacity", "", "comparativa", "faq"]
    assert_the_surfaces_alternate(sections)


def test_the_surfaces_still_alternate_without_upgrade_only_plans(client, seeded):
    Plan.objects.filter(upgrade_only=True).update(is_active=False)

    sections = page_sections(html_of(client))

    assert [section_id for section_id, _ in sections] == ["", "", "comparativa", "faq"]
    assert_the_surfaces_alternate(sections)


def test_the_surfaces_still_alternate_without_plans_on_sale(no_plans, client):
    make_plan("pro", upgrade_only=True)

    sections = page_sections(html_of(client))

    assert [section_id for section_id, _ in sections] == ["", "comparativa", "faq"]
    assert_the_surfaces_alternate(sections)


@pytest.mark.parametrize(
    ("shown", "soft"),
    [
        (["plans", "upgrades", "compare", "competitors", "faq"], {"upgrades", "competitors"}),
        (["plans", "compare", "competitors", "faq"], {"compare", "faq"}),
        (["plans", "competitors", "faq"], {"competitors"}),
    ],
)
def test_every_other_section_shown_is_soft(shown, soft):
    surfaces = pricing.section_surfaces(shown)

    assert {name for name, is_soft in surfaces.items() if is_soft} == soft
    assert set(surfaces) == set(shown)


def test_the_template_has_no_offer_by_contact_above_the_plans():
    """No «Upgrade-only plans» band nor a dedicated-infrastructure band: above the plans on sale only the
    upgrade-only rows themselves, under «More capacity»."""
    page = source("index.html")

    assert "<!-- PLAN CARDS -->" in page
    assert "plans_pro" not in page
    assert "Upgrade-only" not in page
    assert "dedicated" not in page.lower()
    assert "{% url 'public:contact' %}" not in page


def test_pricing_is_a_primary_page_with_the_compact_hero_and_the_shared_rhythm():
    page = source("index.html")
    hero = next(
        line
        for line in page.splitlines()
        if 'include "public/partials/page_hero.html"' in line
    )

    assert "hero_compact=True" in hero
    assert not re.search(r"\bpy-(?:14|16|20)\b", page)


def test_the_pricing_look_lives_in_a_stylesheet_not_in_the_page():
    """No <style> block in the page: its rules are public/static/public/pricing.css."""
    for name in ("index.html", "detail.html", "_plan_compare_cells.html"):
        assert "<style" not in source(name), name
    css = (ROOT / "public" / "static" / "public" / "pricing.css").read_text(
        encoding="utf-8"
    )
    assert ".compare-table" in css
    assert "{% static 'public/pricing.css' %}" in source("index.html")


@pytest.mark.parametrize(
    "template",
    [*sorted(PRICING_TEMPLATES.glob("*.html")), VAT_NOTE],
    ids=lambda path: path.name,
)
def test_every_message_of_a_pricing_template_has_its_spanish_entry(template):
    import gettext

    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    messages = template_messages(template)

    assert messages, f"{template.name} has no translatable message"
    assert [m for m in messages if not catalog.get(m)] == []


def test_the_python_messages_have_their_spanish_entry(no_plans):
    """The FAQ, the trial note and the period labels live in public/pricing.py."""
    make_plan("starter", trial_days=15)
    make_plan("standard", trial_days=30)
    with translation.override("es"):
        texts = [
            *(str(item["question"]) for item in pricing.faq_items()),
            *(str(item["answer"]) for item in pricing.faq_items()),
            pricing.trial_note((15, 30)),
            pricing.trial_note((15, 15)),
            pricing.trial_note((None, None)),
            pricing.apps_at_once(20),
            pricing.apps_at_once(1),
            pricing.apps_at_once(0),
            pricing.apps_at_once_label(0),
        ]
    with translation.override("en"):
        english = [
            *(str(item["question"]) for item in pricing.faq_items()),
            *(str(item["answer"]) for item in pricing.faq_items()),
            pricing.trial_note((15, 30)),
            pricing.trial_note((15, 15)),
            pricing.trial_note((None, None)),
            pricing.apps_at_once(20),
            pricing.apps_at_once(1),
            pricing.apps_at_once(0),
            pricing.apps_at_once_label(0),
        ]

    assert [es for es, en in zip(texts, english) if es == en] == []
