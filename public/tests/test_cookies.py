"""The cookie cleaner of django-cookie-consent, only where there is something to clean.

``cookie_consent.middleware.CleanCookiesMiddleware`` deletes the cookies of a group that was
declined or never accepted. It reads the cookie groups (cache, then database) on every response,
also for a request that carries no cookie at all (an API client, ``/readyz``, a crawler), where it
can delete nothing. ``public.cookies.CleanCookiesMiddleware`` skips those.
"""

from io import StringIO

import pytest
from cookie_consent.util import dict_to_cookie_str
from django.conf import settings
from django.core.management import call_command

HOST = "localhost:8001"


@pytest.fixture
def cookie_groups(db):
    call_command("init_cookie_groups", stdout=StringIO())


def test_the_project_uses_the_wrapper():
    assert "public.cookies.CleanCookiesMiddleware" in settings.MIDDLEWARE
    assert "cookie_consent.middleware.CleanCookiesMiddleware" not in settings.MIDDLEWARE


def test_a_request_without_cookies_never_reads_the_cookie_groups(client):
    """No ``django_db`` mark: a database query here raises."""
    response = client.post(
        "/csp-report/", "{}", content_type="application/json", HTTP_HOST=HOST
    )

    assert response.status_code == 204


@pytest.mark.usefixtures("cookie_groups")
def test_a_declined_groups_cookie_is_deleted(client):
    client.cookies["_ga"] = "GA1.1.123"
    client.cookies[settings.COOKIE_CONSENT_NAME] = dict_to_cookie_str(
        {"analytical": "-1"}
    )

    response = client.get("/robots.txt", HTTP_HOST=HOST)

    assert response.cookies["_ga"]["max-age"] == 0


@pytest.mark.usefixtures("cookie_groups")
def test_a_never_accepted_groups_cookie_is_deleted(client):
    """Opt-in: without a decision, the tracker's cookie goes."""
    client.cookies["_clck"] = "abc"

    response = client.get("/robots.txt", HTTP_HOST=HOST)

    assert response.cookies["_clck"]["max-age"] == 0


@pytest.mark.usefixtures("cookie_groups")
def test_an_accepted_groups_cookie_stays(client):
    client.cookies["_ga"] = "GA1.1.123"
    client.cookies[settings.COOKIE_CONSENT_NAME] = dict_to_cookie_str(
        {"analytical": "2026-10-13T20:00:00"}
    )

    response = client.get("/robots.txt", HTTP_HOST=HOST)

    assert "_ga" not in response.cookies


@pytest.mark.usefixtures("cookie_groups")
def test_the_essential_cookies_are_never_deleted(client):
    """Declining everything must not sign the person out (saas#975)."""
    client.cookies[settings.SESSION_COOKIE_NAME] = "a-session"
    client.cookies[settings.COOKIE_CONSENT_NAME] = dict_to_cookie_str(
        {"analytical": "-1", "marketing": "-1"}
    )

    response = client.get("/robots.txt", HTTP_HOST=HOST)

    assert settings.SESSION_COOKIE_NAME not in response.cookies
