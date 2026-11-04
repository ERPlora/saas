"""Each template that writes a per-response token has an alarm of its own (saas#266).

Under the public CSP a script without the response's nonce does not run, and a POST without a valid
CSRF token gets a 403. A test that reads the whole page sees neither: the rest of the page carries
the same tokens (the footer's language forms, the navbar's script), and Django's test client does
not ask for the token unless told to. So each test reads one site: a nonce is compared with the
header's, and a CSRF token goes back to its own door through a client that enforces the check.
"""

from __future__ import annotations

import re

import pytest
from django.test import Client
from django.urls import reverse

from hubs.tests.conftest import hub_double  # noqa: F401 - the Hub's /internal, behind the demo's door
from public.tests.test_analytics import GA_SCRIPT_MARKER, trackers  # noqa: F401 - a tracker on, the groups seeded
from public.tests.test_response_tokens import CSRF_INPUT, HEADER_NONCE

pytestmark = [pytest.mark.django_db, pytest.mark.urls("public.tests.urls")]

SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL)


@pytest.fixture
def fixed_response_tokens():
    """Overrides the autouse fixture of conftest.py: under it, a nonce drawn apart looks like the header's."""


@pytest.fixture
def browser():
    """A client that has to bring the CSRF token, as a browser has to."""
    return Client(enforce_csrf_checks=True)


def script_holding(html: str, marker: str) -> tuple[str, str]:
    """The attributes and the body of the one script of the page that holds ``marker``."""
    (script,) = [match.groups() for match in SCRIPT.finditer(html) if marker in match.group(0)]
    return script


def assert_it_may_run(response, marker: str) -> None:
    """The script that holds ``marker`` carries the header's nonce, the only one the CSP lets run."""
    nonce = HEADER_NONCE.search(response.headers["Content-Security-Policy"]).group(1)
    attributes, _ = script_holding(response.content.decode(), marker)

    assert f'nonce="{nonce}"' in attributes, attributes


def token_of_the_form(html: str, action: str) -> str:
    """The CSRF token inside the form that posts to ``action``: the footer's forms carry their own."""
    (form,) = re.findall(rf'<form\b[^>]*\baction="{action}"[^>]*>.*?</form>', html, re.DOTALL)
    (token,) = CSRF_INPUT.findall(form)
    return token


def assert_the_server_takes_it(browser: Client, door: str, **with_the_token) -> None:
    """Without a token the door answers 403, so it does check; with this one the POST gets in."""
    assert browser.post(door).status_code == 403
    assert browser.post(door, **with_the_token).status_code == 302


def test_the_help_search_script_may_run(client):
    assert_it_may_run(client.get(reverse("public:help")), "help-search")


def test_the_cookie_banner_script_may_run(client, trackers):
    assert_it_may_run(client.get(reverse("test_public_page")), "cookie-accept")


def test_the_cookie_banner_sends_a_csrf_token_the_server_takes(browser, trackers):
    html = browser.get(reverse("test_public_page")).content.decode()
    _, script = script_holding(html, "cookie-accept")
    (token,) = re.findall(r"'X-CSRFToken': '([^']*)'", script)

    assert_the_server_takes_it(
        browser,
        reverse("cookie_consent_accept"),
        data={"all_groups": "on"},
        headers={"X-CSRFToken": token},
    )


def test_the_cookie_page_script_may_run(client, trackers):
    assert_it_may_run(client.get(reverse("cookie_consent_cookie_group_list")), "ion-toggle.cookie-toggle")


def test_the_cookie_page_toggles_post_a_csrf_token_the_server_takes(browser, trackers):
    html = browser.get(reverse("cookie_consent_cookie_group_list")).content.decode()
    _, script = script_holding(html, "ion-toggle.cookie-toggle")
    (token,) = re.findall(r'var CSRF = "([^"]*)"', script)

    assert_the_server_takes_it(
        browser,
        reverse("cookie_consent_accept"),
        data={"csrfmiddlewaretoken": token, "cookie_groups": "analytical"},
    )


@pytest.mark.parametrize("marker", [GA_SCRIPT_MARKER, "gtag('js'"], ids=["library", "setup"])
def test_the_gtag_scripts_may_run(client, trackers, marker):
    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    assert_it_may_run(client.get(reverse("test_public_page")), marker)


def test_the_contact_form_carries_a_csrf_token_the_server_takes(browser):
    door = reverse("public:contact_submit")
    html = browser.get(reverse("public:contact")).content.decode()

    assert_the_server_takes_it(browser, door, data={"csrfmiddlewaretoken": token_of_the_form(html, door)})


def test_the_demo_form_carries_a_csrf_token_the_server_takes(browser, hub_double, settings):
    settings.DEMO_ENABLED = True
    door = reverse("public:demo_start")
    html = browser.get(reverse("public:demo")).content.decode()

    assert_the_server_takes_it(browser, door, data={"csrfmiddlewaretoken": token_of_the_form(html, door)})
