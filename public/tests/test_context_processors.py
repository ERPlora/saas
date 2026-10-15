"""What every template of the public web knows (ported from ERPlora/saas ``site_settings``,
``config/context_processors.py``, origin/develop c5ca8ca; only the public part)."""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.template import engines

from public.context_processors import public_site


def _context(rf, path, user=None):
    request = rf.get(path)
    request.user = user or AnonymousUser()
    return public_site(request)


def test_the_analytics_ids_and_the_support_address_come_from_the_settings(rf, settings):
    settings.GA_MEASUREMENT_ID = "G-TEST123"
    settings.CLARITY_PROJECT_ID = "clarity-test"
    settings.SUPPORT_EMAIL = "help@example.com"

    context = _context(rf, "/")

    assert context["GA_MEASUREMENT_ID"] == "G-TEST123"
    assert context["CLARITY_PROJECT_ID"] == "clarity-test"
    assert context["SUPPORT_EMAIL"] == "help@example.com"


def test_analytics_is_off_unless_configured(rf):
    """Empty by default: production sets them, local and the tests stay out of GA and Clarity."""
    context = _context(rf, "/")

    assert context["GA_MEASUREMENT_ID"] == ""
    assert context["CLARITY_PROJECT_ID"] == ""


@pytest.mark.parametrize(
    "path", ["/", "/pricing/", "/legal/privacy/", "/apps/inventory/"]
)
def test_an_anonymous_visitor_on_the_public_web_is_on_a_public_page(rf, path):
    assert _context(rf, path)["is_public_page"] is True


@pytest.mark.django_db
def test_a_signed_in_person_is_never_on_a_public_page(rf, ana):
    """Clarity records the screen: the boundary is the session, not the URL (saas#958)."""
    assert _context(rf, "/pricing/", user=ana)["is_public_page"] is False


@pytest.mark.parametrize("path", ["/admin/", "/api/me", "/launch", "/hub-login/"])
def test_the_private_half_is_never_a_public_page(rf, path):
    assert _context(rf, path)["is_public_page"] is False


@pytest.mark.parametrize(
    "path",
    [
        "/_allauth/browser/v1/auth/login",
        "/launch",
        "/login",
        "/login/error",
        "/verify-email",
        "/password/reset",
        "/password/reset/key/abc",
        "/2fa/authenticate",
        "/2fa",
        "/reauthenticate",
    ],
)
def test_the_pages_that_show_credentials_are_flagged(rf, path):
    """Passwords and one-time codes: no analytics there, whatever the consent (saas#958)."""
    assert _context(rf, path)["is_credentials_page"] is True


@pytest.mark.parametrize("path", ["/", "/pricing/", "/launchpad", "/loginx"])
def test_the_other_pages_do_not_show_credentials(rf, path):
    assert _context(rf, path)["is_credentials_page"] is False


@pytest.mark.parametrize("path", ["/accounts/login/", "/accounts/signup/", "/signup", "/password"])
def test_the_addresses_that_render_no_credentials_page_are_not_flagged(rf, path):
    """``/accounts/`` only redirects now (HEADLESS_ONLY), and the SPA has no ``/signup`` nor a
    ``/password`` page of its own: the list names the pages that exist, not every old address."""
    assert _context(rf, path)["is_credentials_page"] is False


def test_an_error_page_without_the_auth_middleware_still_renders(rf):
    """A 404 raised before AuthenticationMiddleware has no ``request.user`` (saas#1631)."""
    request = rf.get("/missing/")

    assert public_site(request)["is_public_page"] is True


def test_the_processor_is_installed_for_every_template(rf):
    template = engines["django"].from_string("{{ is_public_page }}|{{ SUPPORT_EMAIL }}")
    request = rf.get("/")
    request.user = AnonymousUser()

    assert template.render({}, request) == "True|support@erplora.com"
