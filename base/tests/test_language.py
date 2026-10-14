"""``base.language``: on the panel, a signed-in account speaks its own language, whatever the cookie says.

``LocaleMiddleware`` reads the ``_lang`` cookie (the public web's switcher), then ``Accept-Language``. The
panel (the SPA's pages and ``/api/``, its live stream included, and allauth's headless API) speaks the
account's language instead (``User.language``, Cuenta → Preferencias), as Stripe's, Shopify's and Google's
dashboards do: a person changes it in one place and every device follows. Without an account the cookie
still decides, and the public web keeps its switcher's cookie, signed in or not.
"""

import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from base.operations import UserContextBuilder
from base.tests.test_operations import request_for

# Two tests render HTML (the SPA's page, the public web's): its assets come from a Vite manifest, which a
# run without `vite build` (CI) lacks, so every test reads the fixture's.
pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HOST = "localhost:8001"


@pytest.fixture
def bo(db):
    """An account that chose English."""
    return get_user_model().objects.create_user(email="bo@example.com", password=None, language="en")


def client_for(user=None, cookie=None):
    client = Client()
    if user is not None:
        client.force_login(user)
    if cookie is not None:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = cookie
    return client


class TestThePanel:
    def test_the_account_language_wins_over_the_cookie(self, ana):
        response = client_for(ana, cookie="en").get("/api/me", HTTP_HOST=HOST)

        assert (response.json()["language"], response.json()["account_language"]) == ("es", "es")
        assert response["Content-Language"] == "es"

    def test_and_over_the_browser(self, bo):
        response = client_for(bo).get("/api/me", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

        assert response.json()["language"] == "en"

    def test_the_apis_messages_speak_it_too(self, bo):
        response = client_for(bo, cookie="es").get(
            "/api/hubs/businesses/detail", {"id": str(uuid.uuid4())}, HTTP_HOST=HOST
        )

        assert response.status_code == 404
        assert response.json()["error"]["message"] == "This business does not exist or you have no access to it."

    def test_the_spa_page_is_served_in_it(self, ana):
        response = client_for(ana, cookie="en").get("/businesses", HTTP_HOST=HOST)

        assert '<html lang="es"' in response.content.decode()

    def test_a_change_in_preferences_holds_from_the_next_request(self, ana):
        client = client_for(ana, cookie="es")
        get_user_model().objects.filter(pk=ana.pk).update(language="en")

        assert client.get("/api/me", HTTP_HOST=HOST).json()["language"] == "en"

    def test_a_live_stream_follows_the_change_at_its_next_run(self, ana):
        """The live executor re-runs in ``ctx.language``; ``refresh`` re-reads the account before each run."""
        builder = UserContextBuilder()
        ctx = builder.from_request(request_for(ana, language="es"))
        get_user_model().objects.filter(pk=ana.pk).update(language="en")

        assert builder.refresh(ctx).language == "en"


class TestWithoutTheAccount:
    def test_without_a_session_the_cookie_still_decides(self):
        response = client_for(cookie="es").get("/api/me", HTTP_HOST=HOST)

        assert (response.json()["language"], response.json()["account_language"]) == ("es", None)

    def test_the_public_web_keeps_its_switchers_cookie(self, ana):
        response = client_for(ana, cookie="en").get("/", HTTP_HOST=HOST)

        assert response.status_code == 200
        assert response["Content-Language"] == "en"
