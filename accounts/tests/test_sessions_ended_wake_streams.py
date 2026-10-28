"""A session that ends outside the Account page wakes the account's live streams (ACCOUNTS-F08, ACCOUNTS-F09;
FIX-SAAS-ACCOUNTS-SIGNOUT-AND-PASSWORD-DO-NOT-WAKE-STREAMS).

Signing out (allauth.headless ``DELETE auth/session``), a new password (``account/password/change``, its first one or the
reset's: allauth's ``password_changed``, ``password_set`` and ``password_reset``) and allauth's ``DELETE auth/sessions``
record ``accounts.session.closed`` on the account's channel, as «Close the other sessions» does: every stream of the
account re-runs, and the ones whose session ended leave for the sign-in (``base.operations``, saas#142). The event is
the system's (no email in the outbox, ``forget_in_outbox``), and its notice goes once the session is gone.
"""

import re
from importlib import import_module

import pytest
from allauth.usersessions.models import UserSession
from django.conf import settings
from django.core import mail
from django.test import Client
from live import operations
from live.models import OutboxEvent

from accounts import events
from accounts.tests.conftest import BROWSER, HOST, sign_in

pytestmark = pytest.mark.django_db

SESSION = f"{BROWSER}/auth/session"
SESSIONS = f"{BROWSER}/auth/sessions"
CHANGE = f"{BROWSER}/account/password/change"
NEW_PASSWORD = "a brand new pass phrase 2026"


def _recorded() -> list[tuple[str, str, str, str]]:
    return list(OutboxEvent.objects.order_by("id").values_list("scope_kind", "scope_key", "name", "actor"))


def _woken(user) -> list[tuple[str, str, str, str]]:
    """What wakes ``user``'s streams: one ``accounts.session.closed`` on its channel, by the system."""
    return [("user", str(user.pk), events.SESSION_CLOSED, "system")]


def _session_exists(session_key: str) -> bool:
    return import_module(settings.SESSION_ENGINE).SessionStore().exists(session_key)


def _csrf(client) -> str:
    client.get(SESSION, HTTP_HOST=HOST)
    return client.cookies["csrftoken"].value


class TestSigningOut:
    def test_it_wakes_the_accounts_streams(self, signed_in, ana):
        response = signed_in.delete(SESSION, HTTP_HOST=HOST)

        assert response.status_code == 401
        assert _recorded() == _woken(ana)

    def test_an_anonymous_visitor_wakes_nobody(self, client):
        response = client.delete(SESSION, HTTP_HOST=HOST)

        assert response.status_code == 401
        assert _recorded() == []

    def test_the_event_keeps_no_email(self, signed_in, ana):
        signed_in.delete(SESSION, HTTP_HOST=HOST)

        assert not OutboxEvent.objects.filter(actor__contains="@").exists()


@pytest.mark.django_db(transaction=True)
def test_signing_out_notifies_once_the_session_is_gone(client, ana, password, monkeypatch):
    """The stream re-runs on the notice and looks its session up: notified while it still existed, the stream would
    find it and stay (Django's ``user_logged_out`` comes before the session is flushed)."""
    sign_in(client, ana.email, password)
    key = client.session.session_key
    heard = []
    monkeypatch.setattr(
        operations, "notify_hook", lambda scope, names: heard.append((scope.key, sorted(names), _session_exists(key)))
    )

    client.delete(SESSION, HTTP_HOST=HOST)

    assert heard == [(str(ana.pk), [events.SESSION_CLOSED], False)]


class TestANewPassword:
    def test_changing_it_wakes_the_accounts_streams(self, signed_in, ana, password):
        phone = sign_in(Client(), ana.email, password)

        response = signed_in.post(
            CHANGE, {"current_password": password, "new_password": NEW_PASSWORD}, content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code == 200
        assert phone.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 401
        assert _recorded() == _woken(ana)

    def test_a_wrong_current_password_wakes_nobody(self, signed_in):
        response = signed_in.post(
            CHANGE, {"current_password": "not my password", "new_password": NEW_PASSWORD}, content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code == 400
        assert _recorded() == []

    def test_the_resets_wakes_them_too(self, client, ana, password):
        """«Forgot your password?»: the key mailed to the account sets a new one (allauth's ``password_reset``). It is
        also how an account without one (it entered with Google) gets its first: ``account/password/change`` refuses
        it (``password_required``), so allauth's ``password_set`` never comes here."""
        laptop = sign_in(Client(), ana.email, password)
        mail.outbox.clear()
        client.post(f"{BROWSER}/auth/password/request", {"email": ana.email}, content_type="application/json", HTTP_HOST=HOST)
        [link] = re.findall(r"http://localhost:8001/password/reset/key/(\S+)", mail.outbox[-1].body)

        response = client.post(
            f"{BROWSER}/auth/password/reset", {"key": link, "password": NEW_PASSWORD}, content_type="application/json", HTTP_HOST=HOST
        )

        assert response.status_code in (200, 401), response.content
        ana.refresh_from_db()
        assert ana.check_password(NEW_PASSWORD)
        assert laptop.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 401
        assert _recorded() == _woken(ana)


class TestAllauthsSessionsEndpoint:
    def test_ending_another_session_wakes_the_accounts_streams(self, signed_in, ana, password):
        phone = sign_in(Client(), ana.email, password)
        other = UserSession.objects.get(session_key=phone.session.session_key)

        response = signed_in.delete(SESSIONS, {"sessions": [other.pk]}, content_type="application/json", HTTP_HOST=HOST)

        assert response.status_code == 200, response.content
        assert phone.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 401
        assert _recorded() == _woken(ana)

    def test_ending_several_sessions_of_the_account_wakes_its_streams_once(self, signed_in, ana, password):
        """One event per account, however many of its sessions end together: its streams re-run once."""
        phone = sign_in(Client(), ana.email, password)
        tablet = sign_in(Client(), ana.email, password)
        others = [
            UserSession.objects.get(session_key=device.session.session_key).pk for device in (phone, tablet)
        ]

        response = signed_in.delete(SESSIONS, {"sessions": others}, content_type="application/json", HTTP_HOST=HOST)

        assert response.status_code == 200, response.content
        assert [device.get("/api/accounts/profile", HTTP_HOST=HOST).status_code for device in (phone, tablet)] == [401, 401]
        assert _recorded() == _woken(ana)


def test_no_role_may_announce_ended_sessions(signed_in):
    """Only the system wakes an account's streams this way: no role holds the permission, and no route serves it."""
    from live.meta import all_live_app_configs, permissions_for_role

    from accounts import services
    from base.operations import ACCOUNT_ROLE

    assert services.ANNOUNCE_ENDED_SESSIONS not in permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE)
    assert signed_in.post("/api/accounts/sessions/announce_ended", {}, content_type="application/json", HTTP_HOST=HOST).status_code == 404
