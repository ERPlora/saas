"""The questions of ``/pricing/``: an Ionic accordion and its ``FAQPage`` structured data, in English and
Spanish."""

from __future__ import annotations

import pytest

from public import pricing
from public.tests.pricing_pages import faq_page_of, html_of, visible_markup

pytestmark = [pytest.mark.django_db]


# --- The FAQ and its structured data ----------------------------------------------------------


def test_there_is_a_faq_page_block(client):
    assert faq_page_of(html_of(client))["@context"] == "https://schema.org"


def test_every_faq_entry_is_a_question_with_an_answer(client):
    for entry in faq_page_of(html_of(client))["mainEntity"]:
        assert entry["@type"] == "Question"
        assert entry["name"].strip()
        assert entry["acceptedAnswer"]["@type"] == "Answer"
        assert entry["acceptedAnswer"]["text"].strip()


def test_the_faq_has_one_entry_per_real_question(client):
    assert len(faq_page_of(html_of(client))["mainEntity"]) == len(pricing.faq_items())


def test_every_marked_up_question_is_visible_on_the_page(client):
    """The rule Google enforces: markup describes what the user can see."""
    html = html_of(client)
    body = visible_markup(html)
    # Control: the JSON-LD really is gone, so a question cannot match its own markup.
    assert "FAQPage" not in body

    for entry in faq_page_of(html)["mainEntity"]:
        assert entry["name"] in body, f"{entry['name']!r} is marked up but not rendered"


def test_the_questions_render_in_spanish(client):
    assert "¿Puedo cambiar de plan en cualquier momento?" in html_of(
        client, language="es"
    )


def test_the_faq_json_ld_is_translated_too(client):
    questions = [
        entry["name"]
        for entry in faq_page_of(html_of(client, language="es"))["mainEntity"]
    ]

    assert "¿Puedo cambiar de plan en cualquier momento?" in questions


def test_the_faq_is_an_ionic_accordion_opened_on_its_first_question(client):
    html = html_of(client)
    faq = html[html.index('<section id="faq"') :]

    assert f'<ion-accordion-group value="{pricing.faq_items()[0]["key"]}">' in faq
    assert faq.count("<ion-accordion ") == len(pricing.faq_items())
