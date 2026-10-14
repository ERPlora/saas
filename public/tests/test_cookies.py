"""The cookie cleaner of django-cookie-consent, only where there is something to clean.

``cookie_consent.middleware.CleanCookiesMiddleware`` deletes the cookies of a group that was
declined or never accepted. It reads the cookie groups (cache, then database) on every response,
also for a request that carries no cookie at all (an API client, ``/readyz``, a crawler), where it
can delete nothing. ``public.cookies.CleanCookiesMiddleware`` skips those.
"""

import logging
from io import StringIO

import pytest
import redis.exceptions
from cookie_consent.util import dict_to_cookie_str
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

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


# --- A Valkey that is down never takes the site with it -------------------------------------------


class BrokenCache:
    """The cookie groups' cache with Valkey down: every call raises ``error``."""

    def __init__(self, error: Exception):
        self.error = error

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise self.error

        return fail


@pytest.fixture
def broken_cache(monkeypatch):
    def install(error: Exception) -> None:
        monkeypatch.setattr(
            "cookie_consent.cache._get_cache", lambda: BrokenCache(error)
        )

    return install


@pytest.mark.parametrize(
    "error",
    [
        redis.exceptions.ConnectionError("Error 111 connecting to valkey:6379."),
        redis.exceptions.TimeoutError("Timeout reading from socket"),
        ConnectionError("Connection refused"),
        OSError("Network is unreachable"),
    ],
    ids=["redis-connection", "redis-timeout", "connection", "os"],
)
def test_a_cache_that_is_down_skips_the_cleaning_and_says_so(
    client, broken_cache, caplog, error
):
    """The cleaning is housekeeping: the next response with the cache back does it. A 500 on every
    request that carries a cookie is the site down."""
    broken_cache(error)
    client.cookies["_ga"] = "GA1.1.123"
    client.cookies[settings.COOKIE_CONSENT_NAME] = dict_to_cookie_str(
        {"analytical": "-1"}
    )

    with caplog.at_level(logging.WARNING, logger="public.cookies"):
        response = client.get("/robots.txt", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert "_ga" not in response.cookies
    assert [record.levelno for record in caplog.records if record.name == "public.cookies"] == [
        logging.WARNING
    ]


def test_a_bug_that_is_not_the_cache_is_not_swallowed(client, broken_cache):
    """Only the cache's own failures are tolerated: anything else stays a visible error."""
    broken_cache(RuntimeError("a bug"))
    client.cookies["_ga"] = "GA1.1.123"

    with pytest.raises(RuntimeError, match="a bug"):
        client.get("/robots.txt", HTTP_HOST=HOST)


#: The shared Valkey down, for real: nothing listens on port 1, every call is a refused connection.
VALKEY_DOWN = {
    "default": {
        "BACKEND": "base.cache.FailSoftRedisCache",
        "LOCATION": "redis://127.0.0.1:1",
        "KEY_PREFIX": "saas",
        "OPTIONS": {"socket_connect_timeout": 0.5, "socket_timeout": 0.5},
    }
}


@pytest.mark.usefixtures("cookie_groups")
@pytest.mark.parametrize("path", ["/", "/cookies/", "/apps/"])
@override_settings(CACHES=VALKEY_DOWN)
def test_with_valkey_down_the_public_pages_still_answer(client, path):
    """The banner's tags read the cookie groups through the cache on every public page: with
    Valkey down they come from the database, and the declined tracker still goes."""
    client.cookies["_ga"] = "GA1.1.123"
    client.cookies[settings.COOKIE_CONSENT_NAME] = dict_to_cookie_str(
        {"analytical": "-1"}
    )

    response = client.get(path, HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response.cookies["_ga"]["max-age"] == 0
