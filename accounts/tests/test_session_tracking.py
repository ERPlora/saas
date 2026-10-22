"""The account's sessions as ``allauth.usersessions`` keeps them (Account → Security; PLAN-SAAS §6).

``SessionActivityMiddleware``: a signed-in request records its session (address, browser, last use) at most
once every ``TOUCH_EVERY`` seconds, so a session opened before ``allauth.usersessions`` existed shows too and
«last used» moves without a write per request. ``UserSessionsAdapter``: however a session is ended (the Account page's
operations or allauth.headless ``auth/sessions``), its businesses are asked to end theirs (``signals``).
"""

import pytest
from allauth.usersessions.models import UserSession
from django.test import Client

from accounts import session_tracking, signals
from accounts.tests.conftest import BROWSER, HOST, sign_in

pytestmark = pytest.mark.django_db

CHROME = "Mozilla/5.0 (Macintosh) Chrome/130.0 Safari/537.36"


@pytest.fixture
def received():
    calls = []

    def sessions_ended(sender, user_id, **kwargs):
        calls.append(user_id)

    signals.sessions_ended.connect(sessions_ended, dispatch_uid="test-tracking-ended")
    yield calls
    signals.sessions_ended.disconnect(dispatch_uid="test-tracking-ended")


class TestTheActivity:
    def test_signing_in_records_the_session(self, client, ana, password):
        sign_in(client, ana.email, password)

        [session] = UserSession.objects.filter(user=ana)
        assert session.session_key == client.session.session_key

    def test_signing_in_records_the_session_with_the_cache_down_too(self, client, ana, password, settings):
        """The sign-in records its session itself (``services.record_sign_in``): with the cache down the activity's
        mark is never kept, so the middleware records nothing."""
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}

        sign_in(client, ana.email, password)

        [session] = UserSession.objects.filter(user=ana)
        assert session.session_key == client.session.session_key

    def test_a_session_opened_some_other_way_is_recorded_at_its_next_request(self, client, ana):
        client.force_login(ana)

        client.get("/api/accounts/profile", HTTP_HOST=HOST, HTTP_USER_AGENT=CHROME)

        [session] = UserSession.objects.filter(user=ana)
        assert (session.user_agent, session.ip) == (CHROME, "127.0.0.1")

    def test_the_last_use_moves_at_most_once_every_few_minutes(self, client, ana, monkeypatch):
        client.force_login(ana)
        client.get("/api/accounts/profile", HTTP_HOST=HOST)
        first = UserSession.objects.get(user=ana).last_seen_at

        client.get("/api/accounts/profile", HTTP_HOST=HOST)
        assert UserSession.objects.get(user=ana).last_seen_at == first

        from django.core.cache import cache

        cache.clear()  # TOUCH_EVERY later
        client.get("/api/accounts/profile", HTTP_HOST=HOST)
        assert UserSession.objects.get(user=ana).last_seen_at > first

    def test_a_request_that_does_not_use_its_session_is_left_alone(self, client, db):
        """Loading a session nobody asked for would make Django drop a cookie it cannot read (the public web
        must never sign anybody out, saas#975): the tracker only looks at a session the request already used."""
        from django.conf import settings

        client.cookies[settings.SESSION_COOKIE_NAME] = "not-a-session"

        response = client.get("/robots.txt", HTTP_HOST=HOST)

        assert settings.SESSION_COOKIE_NAME not in response.cookies
        assert not UserSession.objects.exists()

    def test_an_anonymous_request_records_nothing(self, client, db):
        client.get("/api/me", HTTP_HOST=HOST)

        assert not UserSession.objects.exists()

    def test_with_the_cache_down_nothing_is_written_per_request(self, client, ana, settings):
        """A cache that keeps nothing (``base.cache.FailSoftRedisCache`` with Valkey down answers as Django's dummy
        one: every ``add`` succeeds) must not turn the tracker into a write per request: it records nothing."""
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
        client.force_login(ana)

        for _ in range(3):
            assert client.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 200

        assert not UserSession.objects.exists()

    def test_a_request_acting_with_an_api_key_never_moves_a_session_to_the_keys_account(self, ana, password, rf):
        """A browser signed in as Bo sending Ana's key: Bo's session stays Bo's."""
        from django.contrib.auth import get_user_model
        from django.contrib.sessions.backends.db import SessionStore
        from django.http import HttpResponse

        from accounts.models import ApiKey

        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        bos_browser = sign_in(Client(), bo.email, password)
        bos_session = UserSession.objects.get(user=bo)
        _, prefix, key_hash = ApiKey.new_secret()
        key = ApiKey.objects.create(user=ana, name="k", prefix=prefix, key_hash=key_hash, scopes=["hubs.read"])
        request = rf.get("/api/hubs/businesses", HTTP_USER_AGENT="curl/8")
        request.session = SessionStore(bos_browser.session.session_key)
        request.session.get("_auth_user_id")  # the request used its session
        request.user = ana  # as accounts.api_auth leaves it
        request.auth = key
        from django.core.cache import cache

        cache.clear()  # past TOUCH_EVERY since Bo's sign-in

        session_tracking.SessionActivityMiddleware(lambda request: HttpResponse())(request)

        bos_session.refresh_from_db()
        assert (bos_session.user_id, bos_session.user_agent) == (bo.pk, "")

    def test_touch_every_is_a_few_minutes(self):
        assert session_tracking.TOUCH_EVERY == 300


class TestEndingSessions:
    def test_ending_them_through_allauth_also_ends_them_in_the_businesses(self, client, ana, password, received):
        sign_in(client, ana.email, password)
        phone = sign_in(Client(), ana.email, password)
        other = UserSession.objects.get(session_key=phone.session.session_key)

        response = client.delete(
            f"{BROWSER}/auth/sessions",
            {"sessions": [other.pk]},
            content_type="application/json",
            HTTP_HOST=HOST,
        )

        assert response.status_code == 200
        assert received == [ana.pk]
        assert phone.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 401

    def test_the_adapter_is_ours(self, settings):
        from allauth.usersessions.adapter import get_adapter

        assert isinstance(get_adapter(), session_tracking.UserSessionsAdapter)
