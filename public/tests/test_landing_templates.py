"""The templates of the home ``/`` and the contact page ``/contact/`` (public/landing.py): the shared UI patterns they
use and the Spanish entry of every message, theirs and those of public/landing.py.

* The contact page uses the ``ep-*`` classes.
* The contact mail is rendered from ``public/templates/public/email/``: support reads it, in English.
"""

from __future__ import annotations

import gettext
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation

from apps.tests.factories import CUBE_SVG
from public import landing
from public.tests.template_messages import template_messages

pytestmark = [pytest.mark.django_db]

ROOT = Path(settings.BASE_DIR)
LANDING_TEMPLATES = ROOT / "public" / "templates" / "public" / "landing"
EMAIL_TEMPLATES = ROOT / "public" / "templates" / "public" / "email"
CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"


# --- The shared UI patterns of the home and the contact page ----------------------------------


def landing_source(*parts: str) -> str:
    return LANDING_TEMPLATES.joinpath(*parts).read_text(encoding="utf-8")


def test_the_contact_form_uses_ionic_validation_without_native_browser_feedback():
    form = landing_source("_contact_form.html")

    assert '<form id="contact-form"' in form
    assert "novalidate" in form
    assert "el.setAttribute('aria-invalid', invalid ? 'true' : 'false')" in form
    assert "el.removeAttribute('aria-invalid')" in form
    assert (
        "if (isEmail) el.setAttribute('error-text', val ? EMAIL_ERROR : REQUIRED_ERROR)"
        in form
    )
    assert '<script nonce="{{ csp_nonce }}">' in form
    # mode="md": an outline field does not paint in ios mode.
    assert form.count('fill="outline"') == form.count('mode="md"') == 5


def test_the_contact_page_uses_the_shared_patterns():
    contact = landing_source("contact.html")
    hero = next(
        line
        for line in contact.splitlines()
        if 'include "public/partials/page_hero.html"' in line
    )

    assert "hero_compact=True" in hero
    assert '<h2 class="font-display font-semibold text-2xl mb-6">' in contact
    assert '<h3 class="font-semibold mb-4">' in contact
    assert '<section id="contacto" class="ep-section">' in contact
    assert "style=" not in contact


def test_the_home_sections_use_the_shared_section_rhythm():
    offenders = [
        path.name
        for path in sorted((LANDING_TEMPLATES / "home").glob("*.html"))
        if re.search(r"\bpy-(?:14|16|20)\b", path.read_text(encoding="utf-8"))
    ]

    assert offenders == []


def test_the_home_is_the_eleven_sections_of_the_old_landing_in_order():
    home = landing_source("home.html")

    assert re.findall(r'include "public/landing/home/(_[a-z_]+)\.html"', home) == [
        "_hero",
        "_cost_vs_stack",
        "_platform_bento",
        "_apps",
        "_app",
        "_ecosystem",
        "_plans",
        "_comparison",
        "_build_to_fit",
        "_cta",
        "_contact",
    ]


# --- Every message has its Spanish entry ------------------------------------------------------


def landing_templates() -> list[Path]:
    return sorted(LANDING_TEMPLATES.rglob("*.html"))


@pytest.mark.parametrize("template", landing_templates(), ids=lambda path: path.name)
def test_every_message_of_a_landing_template_has_its_spanish_entry(template):
    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    messages = template_messages(template)

    assert [m for m in messages if not catalog.get(m)] == []


def test_the_python_messages_have_their_spanish_entry(client):
    """The form's answers and the contact section's trial line live in public/landing.py."""
    texts = {}
    for language in ("en", "es"):
        with translation.override(language):
            texts[language] = [
                str(text)
                for text in (
                    *landing.FORM_MESSAGES.values(),
                    landing.sent_message(),
                    landing.contact_trial_note((15, 15)),
                    landing.contact_trial_note((15, 30)),
                )
            ]

    assert [en for en, es in zip(texts["en"], texts["es"]) if en == es] == []


def test_the_mail_templates_are_plain_text_and_internal():
    """Support reads them: English, no i18n, no HTML escaping."""
    subject = (EMAIL_TEMPLATES / "contact_subject.txt").read_text(encoding="utf-8")
    body = (EMAIL_TEMPLATES / "contact_body.txt").read_text(encoding="utf-8")

    assert "{% autoescape off %}" in subject and "{% autoescape off %}" in body
    assert "trans" not in subject + body


def test_the_feature_card_paints_an_inline_icon_svg():
    """public/components/feature_card.html takes the app's cleaned ``icon_svg`` as product_card does."""
    from django.template.loader import render_to_string
    from django.utils.safestring import mark_safe

    html = render_to_string(
        "public/components/feature_card.html",
        {"icon_svg": mark_safe(CUBE_SVG), "heading": "Inventory", "body": "Stock"},
    )

    assert '<span class="ep-feature-card__icon"><svg' in html
