"""The routes of the legal pages of the public web, ``/legal/privacy/``, ``/legal/cookies/``, ``/legal/legal-notice/``
and ``/legal/terms/``, and the links to them: no internal link of a legal page is dead, and the footer, the sitemap and
``llms.txt`` link the pages. The declaración responsable has its own file, ``test_declaracion.py``.
"""

import re

import pytest
from django.urls import resolve, reverse

from public.sitemaps import StaticPagesSitemap
from public.tests.legal_pages import PAGES, spanish

HOST = "localhost:8001"


# --- Routes ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "path"), PAGES.items())
def test_the_legal_routes(name, path):
    assert reverse(name) == path
    assert resolve(path).view_name == name


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
def test_each_legal_page_is_public(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
def test_a_legal_page_only_answers_safe_methods(client, path):
    assert client.post(path).status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
def test_no_internal_link_of_a_legal_page_is_dead(client, path):
    """A link from a legal page to a 404 is a broken promise."""
    html = client.get(path).content.decode()
    links = {
        href
        for href in re.findall(r'href="(/[^"]*)"', html)
        if not href.startswith("/static/")
    }

    for href in sorted(links):
        # follow: an old address may answer a redirect to its page.
        assert client.get(href, follow=True).status_code == 200, f"{path} links {href}"


# --- Links to the legal pages: footer, sitemap, llms.txt ---------------------------------------


def footer_legal_links(html: str) -> list[str]:
    begin = html.index('<span class="ep-footer__legal">')
    return re.findall(r'href="([^"]*)"', html[begin : html.index("</span>", begin)])


@pytest.mark.django_db
def test_the_footer_links_the_legal_pages_in_the_old_order(client):
    """Legal Notice, Privacy, Terms, Cookies, as in the footer's bottom bar. The declaración responsable joins it:
    art. 13.2 RRSIF wants it at hand when buying, before any account."""
    links = footer_legal_links(client.get("/legal/privacy/").content.decode())

    assert links == [
        reverse("public:legal_notice"),
        reverse("public:privacy"),
        reverse("public:terms"),
        reverse("cookie_consent_cookie_group_list"),
        reverse("public:declaracion_responsable"),
    ]


@pytest.mark.django_db
def test_the_footer_legal_links_are_translated(client):
    html = spanish(client, "/legal/privacy/")
    begin = html.index('<span class="ep-footer__legal">')
    legal = html[begin : html.index("</span>", begin)]

    assert "Aviso legal" in legal
    assert "Privacidad" in legal
    assert "Declaración responsable" in legal


@pytest.mark.parametrize(
    ("name", "priority"),
    [
        # Privacy and terms at 0.4 and the others below them, save the declaración responsable, which customers,
        # resellers and the AEAT look up by name.
        ("public:privacy", 0.4),
        ("public:terms", 0.4),
        ("public:declaracion_responsable", 0.4),
        ("public:legal_notice", 0.3),
        ("public:cookies", 0.3),
    ],
)
def test_the_legal_pages_are_in_the_sitemap(name, priority):
    assert (name, priority) in StaticPagesSitemap.pages


@pytest.mark.django_db
def test_llms_txt_links_the_privacy_policy_as_optional_reading(client):
    body = client.get("/llms.txt", HTTP_HOST=HOST).content.decode()
    optional = body[body.index("## Optional") :]

    assert f"- [Privacy](https://{HOST}/legal/privacy/)" in optional
