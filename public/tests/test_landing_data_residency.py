"""Where the home ``/`` (public/landing.py) says the assistant's data is processed and the servers are.

* No page names Hetzner as the host: the servers are on AWS, Ireland region.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from public.tests.landing_pages import CONTACT, HOME, html_of

pytestmark = [pytest.mark.django_db]


# --- Where the assistant's data is processed --------------------------------------------------


def test_the_landing_states_the_ai_runs_on_european_servers(client):
    html = html_of(client, language="es").lower()

    assert "servidores europeos" in html or "servidores en europa" in html


def test_the_landing_says_the_assistant_data_stays_in_the_eu(client):
    html = html_of(client, language="es").lower()

    assert "unión europea" in html or "no sale" in html


@pytest.mark.parametrize(
    ("language", "claim", "whole_assistant"),
    [
        (
            "en",
            "Your assistant's language model is served from the European Union",
            "Your assistant is served from the European Union",
        ),
        (
            "es",
            "El modelo de lenguaje de tu asistente se sirve desde la Unión Europea",
            "Tu asistente se sirve desde la Unión Europea",
        ),
    ],
)
def test_the_landing_puts_in_the_eu_the_language_model_not_the_whole_assistant(client, language, claim, whole_assistant):
    """Frankfurt serves the language model; a dictation is transcribed by the voice provider, which may process it
    outside the EEA (sections 5 and 6 of the privacy policy)."""
    html = html_of(client, language=language)

    assert claim in html
    assert whole_assistant not in html


def test_the_landing_links_the_residency_claim_to_the_privacy_policy(client):
    assert reverse("public:privacy") in html_of(client, language="es")


def test_no_page_of_this_lot_names_hetzner_as_the_host(client):
    """The servers are on AWS (Ireland region); the AI stays in Frankfurt."""
    for path in (HOME, CONTACT):
        for language in ("en", "es"):
            html = html_of(client, path, language)
            assert "Hetzner" not in html, (path, language)
            assert "Falkenstein" not in html, (path, language)
