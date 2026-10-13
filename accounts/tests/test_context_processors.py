"""What every template of saas-next knows about «Continue with Google» (ported from ERPlora/saas:
``GOOGLE_OAUTH_ENABLED`` from ``config/context_processors.py`` and ``google_next`` from
``SubdomainLoginView._google_next`` in ``apps/auth/users/views.py``)."""

import pytest
from django.test import RequestFactory

from accounts.context_processors import google_login


def _context(query: str = "") -> dict:
    return google_login(RequestFactory().get("/accounts/login/" + query))


def test_google_is_off_without_credentials():
    assert _context()["GOOGLE_OAUTH_ENABLED"] is False


def test_google_is_on_with_credentials(google):
    assert _context()["GOOGLE_OAUTH_ENABLED"] is True


def test_the_next_of_the_page_is_carried():
    assert _context("?next=/hub-login/%3Fhub%3Da%26next%3D/sales/")["google_next"] == "/hub-login/?hub=a&next=/sales/"


def test_without_next_there_is_none():
    assert _context()["google_next"] == ""


@pytest.mark.parametrize(
    "hostile", ["https://evil.com/steal", "//evil.com/steal", "/\\evil.com/steal", "http://hub.localhost/x", "launch/"]
)
def test_only_a_path_of_this_site_is_carried(hostile):
    """A destination elsewhere would be open-redirect bait (and allauth would drop it anyway)."""
    assert google_login(RequestFactory().get("/accounts/login/", {"next": hostile}))["google_next"] == ""


def test_it_is_installed_for_every_template(settings):
    processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]

    assert "accounts.context_processors.google_login" in processors
