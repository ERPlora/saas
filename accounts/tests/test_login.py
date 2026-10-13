"""The sign-in page is today's SaaS login (templates ported from ERPlora/saas), served by allauth."""

import re

import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

LOGIN = "/accounts/login/"


def _nonce(response) -> str:
    return re.search(r"'nonce-([^']+)'", response["Content-Security-Policy"]).group(1)


def test_renders_the_ported_template_with_ionic_markup(client):
    response = client.get(LOGIN)

    html = response.content.decode()
    assert response.status_code == 200
    assert "account/login.html" in [t.name for t in response.templates]
    assert '<form method="post" action="">' in html
    assert '<ion-input mode="md" data-bind="login" type="email"' in html
    assert '<input type="hidden" name="login"' in html
    assert '<input type="hidden" name="password">' in html
    assert '<input type="checkbox" name="remember" id="id_remember">' in html
    assert '<span class="erp-logo lg"' in html
    assert "<ion-button type=\"submit\"" in html


def test_every_script_carries_the_nonce_of_the_response(client):
    response = client.get(LOGIN)

    html = response.content.decode()
    scripts = re.findall(r"<script\b[^>]*>", html)
    assert scripts
    assert all(f'nonce="{_nonce(response)}"' in tag for tag in scripts)


def test_ionic_and_the_fonts_are_served_from_static_not_a_cdn(client):
    html = client.get(LOGIN).content.decode()

    assert 'src="/static/vendor/ionic/ionic.esm.js"' in html
    assert "/static/css/erplora-fonts.css" in html
    assert "cdn.jsdelivr.net" not in html
    assert "https://" not in re.sub(r'href="https://erplora\.com/legal/[a-z]+/"', "", html)


def test_the_page_is_translated_to_spanish(client):
    html = client.get(LOGIN, headers={"Accept-Language": "es"}).content.decode()

    assert "Continuar" in html
    assert "Mantener la sesión iniciada" in html


def test_the_next_travels_in_a_hidden_input(client):
    html = client.get(LOGIN, {"next": "/hub-login/?hub=a&next=/"}).content.decode()

    assert '<input type="hidden" name="next" value="/hub-login/?hub=a&amp;next=/">' in html


def test_signing_in_follows_next(client, password):
    get_user_model().objects.create_user(email="ana@example.com", password=password)

    response = client.post(LOGIN + "?next=/launch/", {"login": "ana@example.com", "password": password})

    assert response.status_code == 302
    assert response.url == "/launch/"


def test_a_wrong_password_shows_the_error_in_the_ported_page(client, password):
    get_user_model().objects.create_user(email="ana@example.com", password=password)

    response = client.post(LOGIN, {"login": "ana@example.com", "password": "nope"})

    assert response.status_code == 200
    assert '<div class="non-field-error">' in response.content.decode()


def test_logout_is_allauths_post(client, password):
    user = get_user_model().objects.create_user(email="ana@example.com", password=password)
    client.force_login(user)

    response = client.post("/accounts/logout/")

    assert response.status_code == 302
    assert response.url == "/accounts/login/"
    assert "_auth_user_id" not in client.session


# «Continue with Google» on the login (ported from ERPlora/saas `templates/account/login.html`,
# `tests/test_unified_auth.py::TestGoogleConfig` and `tests/test_google_login_next.py`).

GOOGLE_LOGIN = "/auth/google/login/"


def _google_form(html: str) -> str:
    """The `<form>` of the Google button, apart from the rest of the page."""
    marker = f'action="{GOOGLE_LOGIN}"'
    assert marker in html, "the login has no form that posts to /auth/google/login/"
    start = html.rfind("<form", 0, html.index(marker))
    return html[start : html.index("</form>", start)]


def test_without_google_credentials_there_is_no_google_button(client):
    html = client.get(LOGIN).content.decode()

    assert GOOGLE_LOGIN not in html
    assert "Continue with Google" not in html


def test_with_google_configured_the_button_posts_to_the_registered_path(client, google):
    form = _google_form(client.get(LOGIN).content.decode())

    assert form.startswith(f'<form method="post" action="{GOOGLE_LOGIN}">')
    assert 'name="csrfmiddlewaretoken"' in form
    assert '<ion-button type="submit" fill="outline" size="large" expand="block">' in form
    assert '<span class="iconify" data-icon="ion:logo-google" aria-hidden="true"></span>' in form
    assert "Continue with Google" in form


def test_the_google_button_carries_the_next_of_the_login_page(client, google):
    """`/hub-login/?hub=a&next=…` must survive the round trip to Google (saas#945)."""
    html = client.get(LOGIN, {"next": "/hub-login/?hub=a&next=/sales/"}).content.decode()

    assert '<input type="hidden" name="next" value="/hub-login/?hub=a&amp;next=/sales/">' in _google_form(html)


def test_without_next_the_google_button_invents_none(client, google):
    assert 'name="next"' not in _google_form(client.get(LOGIN).content.decode())


@pytest.mark.parametrize("hostile", ["https://evil.com/steal", "//evil.com/steal", "/\\evil.com/steal"])
def test_a_foreign_next_is_not_carried_to_google(client, google, hostile):
    assert "evil.com" not in _google_form(client.get(LOGIN, {"next": hostile}).content.decode())


def test_the_google_button_is_translated_to_spanish(client, google):
    html = client.get(LOGIN, headers={"Accept-Language": "es"}).content.decode()

    assert "Continuar con Google" in _google_form(html)
