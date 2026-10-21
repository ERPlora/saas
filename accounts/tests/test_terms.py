"""ACCOUNTS-G119: the terms and the privacy policy an account accepted, with when and which version.

The launcher says «By continuing you agree to our Terms & Privacy Policy» under both of its tabs and under
«Continue with Google», as today's SaaS did, which kept no record of it (old-saas:SAAS_PUBLIC-F72, «no hecho»).
Here the account keeps the date it accepted and the versions it accepted (the «Last updated» date of each page),
like Stripe's ``tos_acceptance``: creating the account records them, and signing in while they are older than
today's records the new ones (the terms: «continued use after they take effect implies acceptance»).
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import formats, timezone, translation

from accounts.models import PRIVACY_VERSION, TERMS_VERSION
from accounts.tests.conftest import BROWSER, HOST, sign_in
from accounts.tests.test_google import STRANGER_UID, _claims, _sign_in_with_google

pytestmark = pytest.mark.django_db

User = get_user_model()
SIGNUP = f"{BROWSER}/auth/signup"
OLDER = TERMS_VERSION - timedelta(days=30)


def _create_account(email: str):
    client = Client(HTTP_HOST=HOST)
    return client.post(SIGNUP, {"email": email, "password": "a long new pass phrase 2026"}, content_type="application/json")


def _acceptance(user) -> tuple:
    user.refresh_from_db()
    return user.terms_version, user.privacy_version


def test_creating_the_account_records_what_it_accepted_and_when():
    before = timezone.now()

    assert _create_account("new@example.com").status_code == 401

    new = User.objects.get(email="new@example.com")
    assert _acceptance(new) == (TERMS_VERSION, PRIVACY_VERSION)
    assert before <= new.terms_accepted_at <= timezone.now()


def test_an_account_google_creates_records_it_too(client, google):
    _sign_in_with_google(client, _claims(STRANGER_UID, "stranger@gmail.com"))

    stranger = User.objects.get(email="stranger@gmail.com")
    assert _acceptance(stranger) == (TERMS_VERSION, PRIVACY_VERSION)
    assert stranger.terms_accepted_at is not None


def test_an_account_nobody_signed_up_has_accepted_nothing(ana):
    """An invitation or the admin makes the account: its person has not seen the notice yet."""
    assert (ana.terms_accepted_at, ana.terms_version, ana.privacy_version) == (None, None, None)


def test_signing_in_accepts_todays_versions_once(ana, password):
    sign_in(Client(), ana.email, password)

    assert _acceptance(ana) == (TERMS_VERSION, PRIVACY_VERSION)
    first = ana.terms_accepted_at
    assert first is not None

    sign_in(Client(), ana.email, password)

    ana.refresh_from_db()
    assert ana.terms_accepted_at == first


def test_signing_in_after_the_terms_changed_records_the_new_ones(ana, password):
    long_ago = timezone.now() - timedelta(days=200)
    User.objects.filter(pk=ana.pk).update(terms_accepted_at=long_ago, terms_version=OLDER, privacy_version=PRIVACY_VERSION)

    sign_in(Client(), ana.email, password)

    assert _acceptance(ana) == (TERMS_VERSION, PRIVACY_VERSION)
    assert ana.terms_accepted_at > long_ago


def test_a_wrong_password_accepts_nothing(ana):
    Client(HTTP_HOST=HOST).post(
        f"{BROWSER}/auth/login", {"email": ana.email, "password": "wrong"}, content_type="application/json"
    )

    assert _acceptance(ana) == (None, None)


@pytest.mark.parametrize(("page", "version"), [("/legal/terms/", TERMS_VERSION), ("/legal/privacy/", PRIVACY_VERSION)])
def test_the_versions_are_the_dates_the_pages_say(client, spa_manifest, page, version):
    """A page updated without its version (or the other way round) would record a text nobody accepted."""
    with translation.override("en"):
        updated = formats.date_format(version, "F j, Y")
    response = client.get(page, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="en")

    assert response.status_code == 200
    assert f"<strong>Last updated:</strong> {updated}" in response.content.decode()
