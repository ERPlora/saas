"""``POST /set-language/``: the public web's language switcher (plan §3.a).

Ported from the ``set_language`` tests of ERPlora/saas ``apps/public/landing/tests/test_views.py``
(origin/develop c5ca8ca). Not ported: ``test_set_language_authenticated_user`` — the switcher keeps
only the ``_lang`` cookie and never writes ``User.language``, which the panel manages (its
preferences page), so a public view does not write into ``accounts``.

The order Django reads (``LocaleMiddleware``): the ``_lang`` cookie, then ``Accept-Language``, then
``en``; Django 4+ no longer reads the session for it.
"""

import re

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

URL = "/set-language/"
HOST = "localhost:8001"


def test_the_route_is_named():
    assert reverse("public:set_language") == URL


def test_the_language_cookie_is_ours_and_lasts_a_year():
    assert settings.LANGUAGE_COOKIE_NAME == "_lang"
    assert settings.LANGUAGE_COOKIE_AGE == 60 * 60 * 24 * 365
    assert settings.LANGUAGE_COOKIE_SAMESITE == "Lax"


@pytest.mark.django_db
def test_a_known_language_is_kept_in_the_cookie(client):
    response = client.post(URL, {"language": "es", "next": "/"}, HTTP_HOST=HOST)

    assert (response.status_code, response.url) == (302, "/")
    cookie = response.cookies["_lang"]
    assert cookie.value == "es"
    assert cookie["max-age"] == 60 * 60 * 24 * 365
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/"


@pytest.mark.django_db
def test_only_the_cookie_is_written_never_the_session(client):
    response = client.post(URL, {"language": "es", "next": "/"}, HTTP_HOST=HOST)

    assert response.cookies["_lang"].value == "es"
    assert "_lang" not in client.session


@pytest.mark.django_db
def test_a_signed_in_persons_account_language_is_not_touched(client, ana):
    """``User.language`` belongs to the panel's preferences page (plan §3.a)."""
    client.force_login(ana)

    response = client.post(URL, {"language": "en", "next": "/"}, HTTP_HOST=HOST)

    assert response.cookies["_lang"].value == "en"
    ana.refresh_from_db()
    assert ana.language == "es"


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
def test_the_next_page_is_served_in_the_chosen_language(client):
    client.post(URL, {"language": "es", "next": "/"}, HTTP_HOST=HOST)

    response = client.get("/launch", HTTP_HOST=HOST)

    assert response["Content-Language"] == "es"


@pytest.mark.django_db
def test_the_switch_is_post_only(client):
    """Changing a persistent preference is POST-only."""
    response = client.get(URL, {"language": "es", "next": "/"}, HTTP_HOST=HOST)

    assert response.status_code == 405


@pytest.mark.django_db
def test_the_switch_is_protected_against_csrf():
    response = Client(enforce_csrf_checks=True).post(
        URL, {"language": "es", "next": "/"}, HTTP_HOST=HOST
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_an_unknown_language_changes_nothing(client):
    response = client.post(
        URL, {"language": "invalid", "next": "/pricing/"}, HTTP_HOST=HOST
    )

    assert (response.status_code, response.url) == (302, "/pricing/")
    assert "_lang" not in response.cookies


@pytest.mark.django_db
def test_without_next_it_goes_back_to_the_referer(client):
    response = client.post(
        URL, {"language": "es"}, HTTP_HOST=HOST, HTTP_REFERER="/some-page/"
    )

    assert (response.status_code, response.url) == (302, "/some-page/")


@pytest.mark.django_db
def test_without_next_nor_referer_it_goes_home(client):
    response = client.post(URL, {"language": "es"}, HTTP_HOST=HOST)

    assert response.url == "/"


@pytest.mark.django_db
def test_the_query_of_next_is_kept(client):
    response = client.post(
        URL, {"language": "es", "next": "/apps/?category=sales"}, HTTP_HOST=HOST
    )

    assert response.url == "/apps/?category=sales"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "next_url", ["https://example.com/phishing", "//example.com/x", "/\\example.com"]
)
def test_an_external_next_is_refused(client, next_url):
    response = client.post(URL, {"language": "es", "next": next_url}, HTTP_HOST=HOST)

    assert (response.status_code, response.url) == (302, "/")


@pytest.mark.django_db
def test_an_external_referer_is_refused(client):
    response = client.post(
        URL, {"language": "es"}, HTTP_HOST=HOST, HTTP_REFERER="https://example.com/x"
    )

    assert response.url == "/"


# --- PUBLIC-F13: a visitor without an account can switch (SAAS_PUBLIC-F68) ----------------------
# The old menu lost its selector and nothing called /set-language/: a visitor could only change the
# browser's language. As Stripe, Shopify, Square and Odoo do, the footer of every public page carries
# the languages of the site, each the button of its own POST form back to the same page.

FOOTER_SWITCHER = re.compile(r'<div class="ep-footer__language".*?</form>\s*</div>', re.S)


def footer_switcher(client, path="/", language="en") -> str:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200
    (switcher,) = FOOTER_SWITCHER.findall(response.content.decode())
    return switcher


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/", "/pricing/", "/compliance/", "/about/"])
def test_every_public_page_offers_the_languages_in_its_footer(client, path):
    switcher = footer_switcher(client, path)
    forms = re.findall(r"<form .*?</form>", switcher, re.S)

    assert re.findall(r'name="language" value="(\w+)"', switcher) == [code for code, _ in settings.LANGUAGES]
    assert len(forms) == len(settings.LANGUAGES)
    for form in forms:
        assert 'method="post"' in form
        assert f'action="{reverse("public:set_language")}"' in form
        assert 'name="csrfmiddlewaretoken"' in form
        assert f'name="next" value="{path}"' in form
        assert '<ion-button type="submit"' in form


@pytest.mark.django_db
def test_each_language_reads_in_its_own_name_and_the_current_one_is_marked(client):
    switcher = footer_switcher(client, language="es")

    assert ">English</ion-button>" in switcher
    assert ">Español</ion-button>" in switcher
    assert re.findall(r'lang="(\w+)" aria-current="true"', switcher) == ["es"]


@pytest.mark.django_db
def test_the_next_page_keeps_its_query(client):
    switcher = footer_switcher(client, "/pricing/?ref=footer")

    assert 'name="next" value="/pricing/?ref=footer"' in switcher


@pytest.mark.django_db
def test_the_switcher_is_labelled_in_the_reading_language(client):
    assert 'aria-label="Idioma"' in footer_switcher(client, language="es")
