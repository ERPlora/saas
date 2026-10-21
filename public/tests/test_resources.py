"""``/documentation/`` (a 301 to the help center, PUBLIC-G07) and ``/support/`` (public/resources.py).

Port of ``apps/public/resources`` (origin/develop c5ca8ca): ``resources/test_views.py`` (2; its help
case lives in test_help.py, with the help) and the cases of ``tests/unit/test_public_pages.py`` for
these pages. What changed, and why:

* the URL names live in the ``public`` namespace;
* OutfitKit is gone: ``ok-container``/``ok-grid-cards``/``<ok-feature-card>`` are the ``ep-*``
  classes and the feature-card partial of L2;
* the contact page comes with the landing (L7) at the address it has today, ``/contact/``: the
  support page links that address (``landing:contact_page`` does not exist here).
"""

import pytest
from django.conf import settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

PAGES = ("/support/",)


def page(client, path: str, language: str = "en") -> str:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response.content.decode()


@pytest.mark.parametrize("path", PAGES)
def test_the_page_answers_with_the_brand_the_navbar_and_the_footer(client, path):
    html = page(client, path)

    assert "ERPlora" in html
    assert '<nav class="ep-navbar"' in html
    assert f'href="{reverse("public:features")}"' in html
    assert '<footer class="ep-footer"' in html


@pytest.mark.parametrize("path", PAGES)
def test_the_page_only_answers_safe_methods(client, path):
    assert client.post(path).status_code == 405


@pytest.mark.parametrize("path", PAGES)
def test_the_page_is_not_indexed(client, path):
    assert '<meta name="robots" content="noindex, follow">' in page(client, path)


def test_the_url_names():
    assert reverse("public:documentation") == "/documentation/"
    assert reverse("public:support") == "/support/"


@pytest.mark.parametrize("path", ["/documentation/", "/documentation/?q=print"])
def test_documentation_leads_to_the_help_center_for_good(client, path):
    """PUBLIC-G07: the documentation that exists is the help center's guides; never a «coming soon»."""
    response = client.get(path)

    assert response.status_code == 301
    assert response["Location"] == reverse("public:help")


def test_documentation_answers_no_other_method(client):
    assert client.post("/documentation/").status_code == 405


def test_support_uses_shared_layout_and_real_contact_routes(client, settings):
    settings.SUPPORT_EMAIL = "support@erplora.test"
    html = page(client, "/support/")

    assert 'class="ep-container ep-section-content"' in html
    assert 'class="ep-grid-cards"' in html
    assert html.count('class="ep-feature-card"') == 3
    assert f'href="{reverse("public:help")}"' in html
    assert 'href="/contact/"' in html
    assert "mailto:support@erplora.test?subject=ERPlora%20Support" in html
    assert "Email support@erplora.test when you cannot use the contact form." in html
    assert "max-w-3xl" not in html
    assert "Report a Problem" in html


def test_support_tells_what_to_send_and_what_never_to_send(client):
    html = page(client, "/support/")

    for heading in (
        "Identify the affected Hub",
        "Describe the exact steps",
        "Copy the visible message",
        "Add device context",
        "Keep credentials private",
    ):
        assert heading in html
    # No <ion-icon> (no runtime icon set): the SVG is painted on the server.
    assert "<ion-icon" not in html


def test_support_in_spanish(client, settings):
    settings.SUPPORT_EMAIL = "support@erplora.test"
    html = page(client, "/support/", "es")

    assert "Estamos aquí para ayudarte." in html
    assert "support@erplora.test" in html


def test_the_footer_support_column_links_help_and_support(client):
    html = page(client, "/features/")
    footer = html[html.index('<footer class="ep-footer"') :]
    support = footer[footer.index(">Support</h2>") :]

    assert support.index(f'href="{reverse("public:help")}"') < support.index(
        f'href="{reverse("public:support")}"'
    )
    assert "Help Center" in support
