"""Who may crawl what: the private half of erplora.com is never indexable (ported from ERPlora/saas
``apps/public/crawlers.py`` and ``landing/tests/test_ai_crawlers.py``, origin/develop c5ca8ca).

robots.txt (``public/seo.py``, ``test_seo.py``) is only a polite request; the ``X-Robots-Tag``
header is the enforcement. In saas-next the private half is the account and sign-in flows (allauth,
its headless API, the jump to a hub), the API, the internal calls, the admin and every page of the
Ionic Vue SPA, which is the account panel: none of it belongs in a search index.
"""

import pytest

from public.crawlers import (
    ANSWER_ENGINE_AGENTS,
    NOINDEX_HEADER,
    is_private,
    private_prefixes,
)

HOST = "localhost:8001"


def test_the_private_prefixes_are_those_of_saas_next():
    assert private_prefixes() == (
        "/admin/",
        "/api/",
        "/internal/",
        "/_allauth/",
        "/accounts/",
        "/auth/",
        "/hub-login/",
        "/webhooks/",
        "/launch",
        "/login",
        "/signup",
        "/password",
        "/verify-email",
        "/2fa",
        "/reauthenticate",
    )


def test_the_answer_engines_are_named_one_by_one():
    """Named explicitly, so a managed robots.txt upstream cannot silently speak for us."""
    assert ANSWER_ENGINE_AGENTS == (
        "OAI-SearchBot",
        "ChatGPT-User",
        "PerplexityBot",
        "Perplexity-User",
        "ClaudeBot",
        "Claude-User",
        "Google-Extended",
        "Applebot-Extended",
        "GPTBot",
        "CCBot",
        "meta-externalagent",
        "Amazonbot",
        "Bytespider",
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/admin/",
        "/accounts/login/",
        "/hub-login/",
        "/api/nope",
        "/_allauth/nope",
        "/webhooks/stripe/",
    ],
)
def test_the_private_paths_carry_noindex(client, path):
    """A redirect to the login is still a URL a crawler can index: the header rides on it too."""
    response = client.get(path, HTTP_HOST=HOST, follow=False)

    assert (
        response.get("X-Robots-Tag") == NOINDEX_HEADER == "noindex, nofollow, noarchive"
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize(
    "path", ["/login", "/launch", "/2fa", "/a-panel-page-not-built-yet"]
)
def test_every_page_of_the_spa_carries_noindex(client, path):
    """The SPA is the account panel: a page it gains later is private without touching this list."""
    response = client.get(path, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.get("X-Robots-Tag") == NOINDEX_HEADER


@pytest.mark.django_db
def test_the_public_files_stay_indexable(client):
    response = client.get("/robots.txt", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.get("X-Robots-Tag") is None


def test_is_private_needs_the_path_or_the_spa_route(rf):
    """Unit cover: a public path resolved to a public route is not private."""
    request = rf.get("/robots.txt")
    request.resolver_match = None

    assert is_private(request) is False
    assert is_private(rf.get("/accounts/login/")) is True


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize(
    "path", ["/", "/features/", "/robots.txt", "/llms.txt", "/sitemap.xml", "/login", "/accounts/login/"]
)
def test_outside_prod_every_response_is_noindex(client, settings, path):
    """pre.erplora.com (plan 2026-10-14-entorno-pre) is the team's: not even its public web is indexed."""
    settings.ERPLORA_ENVIRONMENT = "pre"

    response = client.get(path, HTTP_HOST=HOST)

    assert response.get("X-Robots-Tag") == NOINDEX_HEADER
