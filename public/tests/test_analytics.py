"""GA4 and Microsoft Clarity load only after the analytical consent, never on credential pages.

Port of ``tests/unit/test_ga4_analytics.py`` (9), ``test_clarity_analytics.py`` (11) and
``test_analytics_consent_gate.py`` (6) of the old SaaS (issue #958). The partial is
``public/partials/analytics.html``; its context comes from ``public.context_processors.public_site``.

What moved or changed, with the reason:

* the CSP allowlist of Clarity and GA (2 cases) and the ``is_public_page`` /
  ``is_credentials_page`` flags (2 cases) are the public CSP's and the context processor's, and
  their tests live with them: ``public/tests/test_csp.py`` and ``test_context_processors.py``;
* the full-stack cases went through the old dashboard (``overview:index``), a Django page with the
  analytics partial and the banner. saas-next's panel is the SPA, which carries no analytics at
  all; those cases now go through a page that extends the public base (``public/tests/urls.py``)
  and assert that the SPA never loads a tracker, whatever the consent;
* ``/shell/`` does not exist in saas-next: the launcher of a signed-in customer is the SPA's
  ``/launch``.
"""

from __future__ import annotations

import pytest
from cookie_consent.conf import settings as cookie_consent_settings
from cookie_consent.models import CookieGroup
from cookie_consent.util import dict_to_cookie_str
from django.conf import settings
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import Client, RequestFactory
from django.urls import reverse

from accounts.handoff import LAUNCHER
from public.context_processors import public_site

pytestmark = pytest.mark.django_db

GA_SCRIPT_MARKER = "googletagmanager.com/gtag/js"
CLARITY_MARKER = "clarity.ms"
BANNER_MARKER = 'id="cookie-consent-banner"'


def _request_with_consent(path: str, *, analytical_accepted: bool | None):
    """``True`` accepted, ``False`` explicitly declined, ``None`` no decision yet (no cookie).

    Compared with ``None`` on purpose: ``if analytical_accepted`` would make «declined» and «no
    decision» the same request, and the declined cases would test nothing of their own.
    """
    call_command("init_cookie_groups")
    request = RequestFactory().get(path)
    if analytical_accepted is None:
        return request
    if analytical_accepted:
        version = CookieGroup.objects.get(varname="analytical").get_version()
    else:
        version = cookie_consent_settings.COOKIE_CONSENT_DECLINE
    request.COOKIES[settings.COOKIE_CONSENT_NAME] = dict_to_cookie_str(
        {"analytical": version}
    )
    return request


def _render(
    request, *, ga_id="", clarity_id="", is_public_page=True, is_credentials_page=False
) -> str:
    return render_to_string(
        "public/partials/analytics.html",
        {
            "request": request,
            "csp_nonce": "testnonce",
            "GA_MEASUREMENT_ID": ga_id,
            "CLARITY_PROJECT_ID": clarity_id,
            "is_public_page": is_public_page,
            "is_credentials_page": is_credentials_page,
        },
    )


def _signed_in_client(ana) -> Client:
    client = Client()
    client.force_login(ana)
    return client


# --- The helper itself ------------------------------------------------------------------------


def test_consent_helper_distinguishes_declined_from_no_decision():
    declined = _request_with_consent("/", analytical_accepted=False)
    no_decision = _request_with_consent("/", analytical_accepted=None)

    assert settings.COOKIE_CONSENT_NAME in declined.COOKIES
    assert settings.COOKIE_CONSENT_NAME not in no_decision.COOKIES


# --- GA4 (test_ga4_analytics.py) ---------------------------------------------------------------


def test_context_processor_exposes_ga_measurement_id(settings):
    settings.GA_MEASUREMENT_ID = "G-CTXTEST"

    assert public_site(RequestFactory().get("/"))["GA_MEASUREMENT_ID"] == "G-CTXTEST"


def test_ga4_script_not_loaded_without_any_consent_decision():
    """A first-time visitor's IP, user agent and referer must not reach Google before a choice."""
    assert GA_SCRIPT_MARKER not in _render(
        _request_with_consent("/", analytical_accepted=None), ga_id="G-TEST123"
    )


def test_ga4_script_not_loaded_when_consent_declined():
    assert GA_SCRIPT_MARKER not in _render(
        _request_with_consent("/", analytical_accepted=False), ga_id="G-TEST123"
    )


def test_ga4_script_loaded_when_analytical_consent_accepted():
    html = _render(
        _request_with_consent("/", analytical_accepted=True), ga_id="G-TEST123"
    )

    assert GA_SCRIPT_MARKER in html
    assert "id=G-TEST123" in html
    assert 'nonce="testnonce"' in html


def test_ga4_script_not_loaded_when_measurement_id_empty():
    assert GA_SCRIPT_MARKER not in _render(
        _request_with_consent("/", analytical_accepted=True), ga_id=""
    )


def test_ga4_authentication_is_not_consent():
    request = _request_with_consent("/", analytical_accepted=None)
    request.user = type("U", (), {"is_authenticated": True})()

    assert GA_SCRIPT_MARKER not in _render(request, ga_id="G-TEST123")


def test_ga4_authenticated_and_declined_stays_denied():
    request = _request_with_consent("/", analytical_accepted=False)
    request.user = type("U", (), {"is_authenticated": True})()

    assert GA_SCRIPT_MARKER not in _render(request, ga_id="G-TEST123")


def test_ga4_never_loads_on_credentials_page_even_with_consent():
    """`send_page_view` sends the full URL the moment gtag loads: on a password-reset page that is
    the one-time token itself."""
    request = _request_with_consent(
        "/password/reset/key/abc-def123-token", analytical_accepted=True
    )

    assert GA_SCRIPT_MARKER not in _render(
        request, ga_id="G-TEST123", is_credentials_page=True
    )


# --- Clarity (test_clarity_analytics.py) -------------------------------------------------------


def test_context_processor_exposes_clarity_id(settings):
    settings.CLARITY_PROJECT_ID = "ctxid42"

    assert public_site(RequestFactory().get("/"))["CLARITY_PROJECT_ID"] == "ctxid42"


def test_partial_renders_clarity_when_consented():
    html = _render(
        _request_with_consent("/", analytical_accepted=True), clarity_id="xhn93kfr5b"
    )

    # The snippet builds the tag URL at runtime ("…tag/" + id).
    assert "www.clarity.ms/tag/" in html
    assert '"xhn93kfr5b"' in html
    assert 'nonce="testnonce"' in html


def test_partial_hidden_without_consent():
    assert CLARITY_MARKER not in _render(
        _request_with_consent("/", analytical_accepted=None), clarity_id="xhn93kfr5b"
    )


def test_partial_hidden_when_consent_declined():
    assert CLARITY_MARKER not in _render(
        _request_with_consent("/", analytical_accepted=False), clarity_id="xhn93kfr5b"
    )


def test_partial_hidden_when_id_empty():
    assert CLARITY_MARKER not in _render(
        _request_with_consent("/", analytical_accepted=True), clarity_id=""
    )


def test_partial_hidden_outside_the_public_half():
    """Consent and id, but not a public page (a signed-in customer): Clarity records screens."""
    request = _request_with_consent("/pricing/", analytical_accepted=True)

    assert CLARITY_MARKER not in _render(
        request, clarity_id="xhn93kfr5b", is_public_page=False
    )


def test_partial_never_renders_clarity_for_merely_authenticated_user_without_consent():
    request = _request_with_consent("/", analytical_accepted=None)
    request.user = type("U", (), {"is_authenticated": True})()

    assert CLARITY_MARKER not in _render(request, clarity_id="xhn93kfr5b")


def test_partial_never_renders_clarity_on_credentials_page_even_when_consented():
    request = _request_with_consent("/launch", analytical_accepted=True)

    assert CLARITY_MARKER not in _render(
        request, clarity_id="xhn93kfr5b", is_credentials_page=True
    )


# --- Full stack (test_analytics_consent_gate.py) -----------------------------------------------


@pytest.fixture
def trackers(settings):
    settings.GA_MEASUREMENT_ID = "G-TEST123"
    settings.CLARITY_PROJECT_ID = "xhn93kfr5b"
    call_command("init_cookie_groups")


@pytest.mark.urls("public.tests.urls")
def test_a_public_page_offers_the_banner_and_no_tracker_before_a_choice(trackers):
    html = Client().get(reverse("test_public_page")).content.decode()

    assert BANNER_MARKER in html
    assert GA_SCRIPT_MARKER not in html
    assert CLARITY_MARKER not in html


@pytest.mark.urls("public.tests.urls")
def test_a_signed_in_customer_without_a_choice_gets_the_banner_and_no_tracker(
    trackers, ana
):
    """Being signed in is not consent."""
    html = _signed_in_client(ana).get(reverse("test_public_page")).content.decode()

    assert BANNER_MARKER in html
    assert GA_SCRIPT_MARKER not in html
    assert CLARITY_MARKER not in html


@pytest.mark.urls("public.tests.urls")
def test_after_explicit_consent_ga4_loads_but_clarity_not_for_a_signed_in_customer(
    trackers, ana
):
    client = _signed_in_client(ana)
    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    html = client.get(reverse("test_public_page")).content.decode()

    assert GA_SCRIPT_MARKER in html
    assert CLARITY_MARKER not in html
    assert BANNER_MARKER not in html


@pytest.mark.urls("public.tests.urls")
def test_after_explicit_consent_an_anonymous_visitor_gets_both(trackers):
    client = Client()
    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    html = client.get(reverse("test_public_page")).content.decode()

    assert GA_SCRIPT_MARKER in html
    assert CLARITY_MARKER in html


def test_no_tracker_on_the_login_page_even_with_full_consent(trackers, spa_manifest):
    """The sign-in is the launcher's (``/launch``): an anonymous visitor's credentials, no analytics."""
    client = Client()
    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    response = client.get("/launch")

    assert response.status_code == 200
    assert CLARITY_MARKER not in response.content.decode()
    assert GA_SCRIPT_MARKER not in response.content.decode()


def test_the_spa_of_a_signed_in_customer_never_loads_a_tracker(
    trackers, ana, spa_manifest
):
    """The launcher shows the customer's hubs by name: the SPA has no analytics, consent or not."""
    client = _signed_in_client(ana)
    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    html = client.get(LAUNCHER).content.decode()

    assert GA_SCRIPT_MARKER not in html
    assert CLARITY_MARKER not in html
