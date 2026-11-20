"""reCAPTCHA on the contact form of the home ``/`` and the contact page ``/contact/`` (public/landing.py)."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core import mail
from django.test import override_settings

from public import context_processors
from public.tests.landing_pages import CONTACT, HOME, form_of, html_of, messages_of, submit

pytestmark = [pytest.mark.django_db]


# --- reCAPTCHA on the contact form (live.recaptcha) -------------------------------------------------------------
# Both protections stand, in this order: the limit per address first (a throttled message never costs an assessment),
# then the fields, then Google's verdict on `recaptcha_token` (made for `contact` by frontend/recaptcha.ts), right
# before the mail. Google is played by `FakeGoogleRecaptcha` (conftest.py).

UNVERIFIED = "We could not check that you are a person. Try again."


def test_a_message_without_a_token_is_not_mailed_and_says_why(client, recaptcha):
    response = submit(client, next=CONTACT)

    assert response.status_code == 302
    assert mail.outbox == []
    assert UNVERIFIED in messages_of(response)
    assert recaptcha.asked == []


@pytest.mark.parametrize("token", ["bot:contact", "human:demo_request", "forged"], ids=["bot", "other-form", "forged"])
def test_a_bad_token_is_not_mailed(client, recaptcha, token):
    response = submit(client, recaptcha_token=token)

    assert mail.outbox == []
    assert UNVERIFIED in messages_of(response)


def test_a_persons_message_is_mailed(client, recaptcha):
    response = submit(client, recaptcha_token="human:contact")

    assert len(mail.outbox) == 1
    assert recaptcha.asked == [("human:contact", "contact")]
    assert any("Thanks" in message for message in messages_of(response))


def test_google_down_keeps_the_message_unsent_and_what_was_typed(client, recaptcha):
    recaptcha.down = True

    response = submit(client, next=CONTACT, recaptcha_token="human:contact")

    assert mail.outbox == []
    assert 'value="John"' in form_of(client.get(response["Location"].split("#")[0]).content.decode())


def test_an_incomplete_message_never_asks_google(client, recaptcha):
    submit(client, last_name="", recaptcha_token="human:contact")

    assert recaptcha.asked == []


@override_settings(RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="1/h")
def test_a_throttled_message_never_asks_google(client, recaptcha):
    submit(client, recaptcha_token="human:contact")

    submit(client, recaptcha_token="human:contact")

    assert recaptcha.asked == [("human:contact", "contact")]


def test_the_unverified_message_speaks_spanish(client, recaptcha):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    response = submit(client)

    assert "No hemos podido comprobar que eres una persona. Vuelve a intentarlo." in messages_of(response)


@pytest.mark.parametrize("path", [HOME, CONTACT])
def test_the_form_with_recaptcha_asks_google_for_its_token_and_says_so(client, recaptcha, path):
    html = html_of(client, path)

    form = form_of(html)
    assert 'data-recaptcha-action="contact"' in html
    assert 'data-recaptcha-site-key="test-site-key"' in html
    assert 'name="recaptcha_token"' in form
    assert "This site is protected by reCAPTCHA and the Google" in html
    assert 'href="https://policies.google.com/privacy"' in html
    assert 'href="https://policies.google.com/terms"' in html


def test_the_form_without_recaptcha_loads_nothing_of_google(client):
    html = html_of(client, CONTACT)

    assert "data-recaptcha" not in html
    assert "protected by reCAPTCHA" not in html


def test_the_notice_speaks_spanish(client, recaptcha):
    html = html_of(client, CONTACT, language="es")

    assert "Este sitio está protegido por reCAPTCHA" in html
    assert "Política de Privacidad" in html
    assert "Condiciones del Servicio" in html


def test_the_context_gives_the_templates_the_site_key(rf, recaptcha, settings):
    assert context_processors.public_site(rf.get("/"))["RECAPTCHA_SITE_KEY"] == "test-site-key"
    settings.LIVE = {**settings.LIVE, "recaptcha": {"enabled": False, "site_key": "test-site-key"}}
    assert context_processors.public_site(rf.get("/"))["RECAPTCHA_SITE_KEY"] == ""
