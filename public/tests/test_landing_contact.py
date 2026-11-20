"""The contact page ``/contact/`` and the contact section of the home (public/landing.py): the form they carry, the
other ways to reach us and the reply time, each written in one place.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.urls import reverse

from public import context_processors
from public.tests.landing_pages import CONTACT, form_of, hero, html_of, messages_of, section, submit

pytestmark = [pytest.mark.django_db]


# --- The contact page -------------------------------------------------------------------------


def test_the_contact_page_has_the_form_posting_to_the_submit_route(client):
    html = html_of(client, CONTACT)

    assert '<form id="contact-form"' in html
    assert f'action="{reverse("public:contact_submit")}"' in html
    assert 'name="csrfmiddlewaretoken"' in html
    assert '<input type="hidden" name="next" value="/contact/">' in html
    for field in ("first_name", "last_name", "email", "phone", "message"):
        assert f'name="{field}"' in html, field
    assert 'id="contacto"' in html


def test_the_contact_page_gives_the_other_ways_to_reach_us(client):
    """The support address of the footer (never «info@»), and the support chat."""
    html = html_of(client, CONTACT)

    assert f"mailto:{settings.SUPPORT_EMAIL}" in html
    assert 'href="https://wa.me/34643759040"' in html


def test_the_contact_page_in_spanish(client):
    html = html_of(client, CONTACT, language="es")

    assert "Ponte en contacto" in html or "Contacto" in html
    assert "Nombre" in html


@pytest.mark.parametrize(
    ("language", "availability", "reply"),
    [
        ("en", "High availability", "in business hours"),
        ("es", "Alta disponibilidad", "en horas laborables"),
    ],
)
def test_the_hero_promises_what_we_do_not_an_sla_or_round_the_clock_support(
    client, language, availability, reply
):
    """No «Uptime 99.95%» (there is no SLA) and no «Support 24/7»: the form's 4 business hours."""
    stats = hero(html_of(client, language=language))

    assert availability in stats
    assert ">AWS<" in stats
    assert ">4 h<" in stats
    assert reply in stats


@pytest.mark.parametrize(
    ("language", "cell"), [("en", "High availability on AWS"), ("es", "Alta disponibilidad en AWS")]
)
def test_the_platform_bento_says_high_availability_on_aws(client, language, cell):
    assert f'<h3 class="ep-bento-item__title">{cell}</h3>' in html_of(client, language=language)


@pytest.mark.parametrize(
    ("language", "heading", "reply"),
    [
        ("en", "Response time", "Within 4 business hours"),
        ("es", "Tiempo de respuesta", "En un plazo de 4 horas laborables"),
    ],
)
def test_the_contact_page_promises_the_reply_time_of_the_form(client, language, heading, reply):
    """No «Available 24/7/365»: the reply time is the form's 4 business hours."""
    html = html_of(client, CONTACT, language=language)
    other_ways = html[html.index('<h2 class="font-display') :]

    assert heading in other_ways
    assert reply in other_ways


def test_the_home_carries_the_contact_form_too(client):
    contact = section(html_of(client), "contacto")

    assert '<form id="contact-form"' in contact
    assert '<input type="hidden" name="next" value="/">' in contact


# --- One support address, one chat and one reply time, from one place ------------------------


def test_the_contact_page_email_is_the_support_address(client, settings):
    settings.SUPPORT_EMAIL = "help@erplora.test"

    for html in (html_of(client, CONTACT), section(html_of(client), "contacto")):
        assert "mailto:help@erplora.test" in html
        assert "info@erplora.com" not in html


def test_the_reply_time_is_written_once(client, monkeypatch):
    monkeypatch.setattr(context_processors, "SUPPORT_REPLY_HOURS", 6)

    contact = html_of(client, CONTACT)
    home = html_of(client)
    response = submit(client)

    assert "Within 6 business hours" in contact
    assert "We typically respond within 6 business hours." in form_of(contact)
    assert ">6 h<" in hero(home)
    assert any("within 6 business hours" in message for message in messages_of(response))
    assert "4 business hours" not in contact + home


def test_the_reply_time_in_spanish(client):
    html = html_of(client, CONTACT, language="es")

    assert "En un plazo de 4 horas laborables" in html
    assert "Normalmente respondemos en un plazo de 4 horas laborables." in html


def test_the_chat_is_written_once(client, monkeypatch):
    monkeypatch.setattr(context_processors, "SUPPORT_WHATSAPP_URL", "https://wa.me/34600000000")

    for html in (html_of(client, CONTACT), section(html_of(client), "contacto")):
        assert 'href="https://wa.me/34600000000"' in html
        assert "34643759040" not in html
