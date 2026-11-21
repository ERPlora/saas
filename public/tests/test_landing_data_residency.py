"""What the marketing pages say of the AI assistant and where the servers are.

* Of the AI they say one thing only: it has no direct access to the database. Which model it is, who serves it and
  where are the privacy policy's to say (sections 5 and 6), never the marketing's: the model changes, and a claim that
  the assistant runs in the European Union would be false (its default model may process data outside the EEA).
* No page names Hetzner as the host: the servers are on AWS, Ireland region.
"""

from __future__ import annotations

import re

import pytest

from public.tests.landing_pages import CONTACT, HOME, html_of

pytestmark = [pytest.mark.django_db]

MARKETING_PAGES = (HOME, "/pricing/", "/features/", "/security/", "/about/")

NO_DIRECT_ACCESS = {
    "en": "The AI has no direct access to the database.",
    "es": "La IA no tiene acceso directo a la base de datos.",
}

#: The AI models and their providers, by name: the marketing names none of them.
AI_NAMES = (
    "Anthropic",
    "Claude",
    "Haiku",
    "Sonnet",
    "Alibaba",
    "Qwen",
    "Model Studio",
    "OpenAI",
    "GPT",
    "Gemini",
    "DeepSeek",
    "Brave Search",
)

#: What says which AI it is or where it runs.
WHERE_THE_AI_RUNS = (
    "AI assistant on European servers",
    "Asistente IA en servidores europeos",
    "language model",
    "modelo de lenguaje",
    "European servers",
    "servidores europeos",
)


# --- What the marketing says of the AI ---------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", MARKETING_PAGES)
def test_no_marketing_page_names_an_ai_model_or_its_provider(client, path, language):
    html = html_of(client, path, language)

    assert [name for name in AI_NAMES if re.search(rf"\b{re.escape(name)}\b", html)] == []


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", MARKETING_PAGES)
def test_no_marketing_page_says_which_ai_it_is_or_where_it_runs(client, path, language):
    html = html_of(client, path, language)

    assert [claim for claim in WHERE_THE_AI_RUNS if claim in html] == []


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_home_says_the_ai_has_no_direct_access_to_the_database(client, language):
    assert NO_DIRECT_ACCESS[language] in html_of(client, HOME, language)


# --- Where the servers are ---------------------------------------------------------------------


def test_no_page_of_this_lot_names_hetzner_as_the_host(client):
    """The servers are on AWS (Ireland region)."""
    for path in (HOME, CONTACT):
        for language in ("en", "es"):
            html = html_of(client, path, language)
            assert "Hetzner" not in html, (path, language)
            assert "Falkenstein" not in html, (path, language)
