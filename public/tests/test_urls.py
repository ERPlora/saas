"""The public web's routes (``public/urls.py``, namespace ``public``) and how the project mounts them
(``config/urls.py``): before the SPA's catch-all, its first segments out of the SPA."""

import pytest
from django.urls import resolve, reverse

from config.urls import NON_SPA_PREFIXES
from public.urls import PUBLIC_PREFIXES

HOST = "localhost:8001"


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("public:set_language", "/set-language/"),
        ("public:robots_txt", "/robots.txt"),
        ("public:llms_txt", "/llms.txt"),
        ("public:sitemap", "/sitemap.xml"),
        # django-cookie-consent's own names, without a namespace: its templates reverse them so.
        ("cookie_consent_cookie_group_list", "/cookies/"),
        ("cookie_consent_accept", "/cookies/accept/"),
        ("cookie_consent_decline", "/cookies/decline/"),
        ("cookie_consent_status", "/cookies/status/"),
    ],
)
def test_the_public_routes(name, path):
    assert reverse(name) == path
    assert resolve(path).view_name == name


def test_the_indexnow_key_file_route():
    assert (
        reverse("public:indexnow_key", args=["0123456789abcdef"])
        == "/0123456789abcdef.txt"
    )


def test_robots_and_llms_win_over_the_key_file():
    assert resolve("/robots.txt").view_name == "public:robots_txt"
    assert resolve("/llms.txt").view_name == "public:llms_txt"


# Each first segment the public web serves (now or in a later batch of the port) and the retired
# ones that must answer 404, never the SPA's shell (spec §8.1, §8.3).
PUBLIC_SEGMENTS = (
    "set-language",
    "robots.txt",
    "llms.txt",
    "sitemap.xml",
    "cookies",
    "legal",
    "pricing",
    "industries",
    "apps",
    "app",
    "about",
    "company",
    "collaborate",
    "blog",
    "careers",
    "press",
    "features",
    "security",
    "updates",
    "documentation",
    "support",
    "help",
    "contact",
    "download",
    "marketplace",
    "solutions",
    "modules",
)
RETIRED_SEGMENTS = ("developers", "bridge", "compliance")


@pytest.mark.parametrize("segment", [*PUBLIC_SEGMENTS, *RETIRED_SEGMENTS])
def test_the_public_segments_never_reach_the_spa(segment):
    assert segment in PUBLIC_PREFIXES
    assert segment in NON_SPA_PREFIXES


def test_the_public_web_declares_exactly_its_segments():
    """The app owns its first segments (public/urls.py); the project only mounts them."""
    assert sorted(PUBLIC_PREFIXES) == sorted((*PUBLIC_SEGMENTS, *RETIRED_SEGMENTS))


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize(
    "path", ["/developers/", "/bridge/", "/compliance/", "/pricing/nope/"]
)
def test_a_retired_or_unknown_public_page_is_a_404_not_the_shell(client, path):
    response = client.get(path, HTTP_HOST=HOST)

    assert response.status_code == 404
    assert '<div id="app"></div>' not in response.content.decode()
