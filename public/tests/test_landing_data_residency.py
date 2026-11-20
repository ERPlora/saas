"""Where the home ``/`` (public/landing.py) says the assistant's data is processed and the servers are.

* The home makes no claim that the assistant runs in the European Union: its default language model may process data
  outside the EEA (sections 5 and 6 of the privacy policy), so the claim would be false.
* No page names Hetzner as the host: the servers are on AWS, Ireland region.
"""

from __future__ import annotations

import pytest

from public.tests.landing_pages import CONTACT, HOME, html_of

pytestmark = [pytest.mark.django_db]


# --- Where the assistant's data is processed --------------------------------------------------


@pytest.mark.parametrize(
    ("language", "claims"),
    [
        ("en", ("AI assistant on European servers", "language model is served from the European Union")),
        ("es", ("Asistente IA en servidores europeos", "se sirve desde la Unión Europea")),
    ],
)
def test_the_landing_never_says_the_assistant_runs_in_the_eu(client, language, claims):
    html = html_of(client, language=language)

    assert [claim for claim in claims if claim in html] == []


def test_no_page_of_this_lot_names_hetzner_as_the_host(client):
    """The servers are on AWS (Ireland region)."""
    for path in (HOME, CONTACT):
        for language in ("en", "es"):
            html = html_of(client, path, language)
            assert "Hetzner" not in html, (path, language)
            assert "Falkenstein" not in html, (path, language)
