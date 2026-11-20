"""The templates of the legal pages: they share the public reading pattern, and every message has its Spanish entry
in ``public``'s compiled catalog.
"""

import gettext

import pytest

from public.tests.legal_pages import LEGAL_TEMPLATES, ROOT
from public.tests.template_messages import template_messages

CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"


# --- The shared reading pattern ----------------------------------------------------------------


#: What a page with a date extends: the reading pattern and where the date goes.
DATED_PAGE = 'extends "public/legal/_dated_page.html"'


@pytest.mark.parametrize("template", ["legal_notice", "privacy", "cookies", "terms"])
def test_a_legal_page_uses_the_shared_public_reading_pattern(template):
    source = (LEGAL_TEMPLATES / f"{template}.html").read_text(encoding="utf-8")
    shared = (LEGAL_TEMPLATES / "_dated_page.html").read_text(encoding="utf-8") if DATED_PAGE in source else source
    hero = next(
        line
        for line in source.splitlines()
        if 'include "public/partials/page_hero.html"' in line
    )

    assert "{% block page_content %}" in shared
    assert "{% block content %}" not in source
    assert "hero_compact=True" in hero
    assert 'class="ep-section--compact ep-section--divider"' in shared
    assert 'class="ep-container ep-section-content"' in shared
    assert 'class="ep-prose max-w-4xl mx-auto"' in shared
    for html in (source, shared):
        assert "<ion-card" not in html
        assert "max-width:" not in html
        assert 'style="' not in html
        assert "<style" not in html


@pytest.mark.parametrize("template", ["privacy", "terms", "cookies"])
def test_a_dated_legal_page_says_its_date_in_the_one_place(template):
    """Of the terms and the privacy policy, that date is the version an account accepts (``accounts/models.py``)."""
    source = (LEGAL_TEMPLATES / f"{template}.html").read_text(encoding="utf-8")

    assert DATED_PAGE in source
    assert "{% block updated %}" in source
    assert "Last updated:" not in source


# --- Every message has its Spanish entry -------------------------------------------------------


def test_the_template_messages_are_read_like_makemessages(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '{% load i18n %}{% trans "It\'s here" %}'
        "{% blocktrans trimmed with v=x %}\n  Version\n  {{ v }}\n{% endblocktrans %}"
        '{% button href="/launch" label=_("It\'s a button") %}',
        encoding="utf-8",
    )

    assert template_messages(page) == ["It's here", "Version %(v)s", "It's a button"]


@pytest.mark.parametrize(
    "template", sorted(LEGAL_TEMPLATES.glob("*.html")), ids=lambda path: path.name
)
def test_every_message_of_a_legal_template_has_its_spanish_entry(template):
    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    messages = template_messages(template)

    assert messages, f"{template.name} has no translatable message"
    assert [m for m in messages if not catalog.get(m)] == [], (
        "add the msgid/msgstr to public/locale/es/LC_MESSAGES/django.po and compile"
    )
