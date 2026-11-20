"""How the home ``/`` and the contact page ``/contact/`` (public/landing.py) are reached: their routes, the brand, the
navbar and the footer they carry, the pages that answer and the ones that do not, the sitemap and ``llms.txt``.

* ``/`` is the landing; the project-wide URL name ``home`` reverses to ``/`` (allauth's templates and the error pages
  use it).
"""

from __future__ import annotations

import re

import pytest
from django.urls import resolve, reverse

from public.tests.landing_pages import CONTACT, HOME, html_of, section

pytestmark = [pytest.mark.django_db]


# --- Routes -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("public:home", "/"),
        ("public:contact", "/contact/"),
        ("public:contact_submit", "/contact/submit/"),
    ],
)
def test_the_routes(name, path):
    assert reverse(name) == path
    assert resolve(path).view_name == name


def test_the_project_wide_home_name_is_the_landing():
    """allauth's templates and the error pages reverse ``home``: it is ``/``, served by the landing."""
    assert reverse("home") == "/"
    assert resolve("/").view_name == "public:home"


def test_the_root_is_the_landing_not_the_launcher(client):
    response = client.get(HOME)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert "ERPlora" in response.content.decode()


@pytest.mark.parametrize("path", [HOME, CONTACT])
def test_the_pages_only_answer_safe_methods(client, path):
    assert client.post(path).status_code == 405


# --- Smoke of the pages of this file ----------------------------------------------------------


@pytest.mark.parametrize("path", [HOME, CONTACT])
def test_the_page_carries_the_brand_the_navbar_and_the_footer(client, path):
    html = html_of(client, path)

    assert "ERPlora" in html
    assert '<nav class="ep-navbar"' in html
    assert '<footer class="ep-footer"' in html


def test_the_navbar_links_features_apps_pricing_and_contact_in_that_order(client):
    html = html_of(client)
    links = html[html.index('<div class="ep-navbar__links">') :]
    links = links[: links.index("</div>")]

    assert re.findall(r'href="([^"]+)"', links) == [
        reverse("public:features"),
        reverse("public:store"),
        reverse("public:pricing"),
        reverse("public:contact"),
    ]


def test_the_footer_has_its_social_links_and_the_legal_ones(client):
    html = html_of(client)
    footer = html[html.index('<footer class="ep-footer"') :]

    assert "linkedin.com" in footer
    assert "Privacy" in footer and "Terms" in footer
    assert f'href="{reverse("public:pricing")}"' in footer
    assert f'href="{reverse("public:contact")}"' in footer
    assert f'href="{reverse("public:collaborate")}"' in footer


@pytest.mark.parametrize(
    "path",
    [
        "/contact/does-not-exist/",
        "/pricing/does-not-exist/deeper/",
        "/api/nonexistent/",
    ],
)
def test_a_page_that_does_not_exist_is_a_404(client, path):
    """Under the public web's segments and the API. Any other unknown path is the SPA's (its
    router paints the not-found page): config/tests/test_urls.py pins that the shell answers."""
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/features/",
        "/security/",
        "/updates/",
        "/about/",
        "/careers/",
        "/blog/",
        "/press/",
        "/help/",
        "/support/",
        "/legal/privacy/",
        "/legal/terms/",
        "/pricing/",
        "/collaborate/",
        "/contact/",
        "/",
    ],
)
def test_every_public_page_answers(client, path):
    assert client.get(path).status_code == 200


# --- The sitemap and llms.txt -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "priority"),
    [("public:home", 1.0), ("public:pricing", 0.9), ("public:contact", 0.6)],
)
def test_the_pages_of_this_lot_are_in_the_sitemap_with_the_old_priorities(name, priority):
    from public.sitemaps import StaticPagesSitemap

    assert (name, priority) in StaticPagesSitemap.pages


def test_llms_txt_starts_with_the_home_and_the_pricing(client):
    body = client.get("/llms.txt").content.decode()
    start = body[body.index("## Start here") :]

    lines = [line for line in start.splitlines() if line.startswith("- [")]
    assert lines[0] == (
        "- [What ERPlora is](https://testserver/): the product in one page — apps, pricing and "
        "the counter app."
    )
    assert lines[1] == (
        "- [Pricing](https://testserver/pricing/): plans, what each includes, and the answers to "
        "the usual billing questions."
    )


def test_llms_txt_offers_the_terms_and_the_contact_page_as_optional_reading(client):
    body = client.get("/llms.txt").content.decode()
    optional = body[body.index("## Optional") :]

    assert "- [Terms](https://testserver/legal/terms/)" in optional
    assert "- [Contact](https://testserver/contact/)" in optional


def test_the_home_points_to_the_app_page(client):
    app_section = section(html_of(client), "app")

    assert f'href="{reverse("public:app")}"' in app_section
    assert "/bridge/" not in app_section
