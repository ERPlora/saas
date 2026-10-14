"""Account → Security → Active sessions: ``accounts.session.list``, ``accounts.session.close`` and
``accounts.session.close_others`` (plan 2026-10-13, L3-A; ``allauth.usersessions``, PLAN-SAAS §6).

Ported from ERPlora/saas ``apps/dashboard/profile`` (``sessions``, ``handle_session_action``), whose sessions
were JWT refresh tokens: here they are the browser sessions of the SaaS. The location is the address (GeoIP is
out of scope, plan §6). Closing a session also asks every business to end the account's sessions there
(PLAN-SAAS §2.1; ``signals.sessions_ended``, which hubs turns into ``POST /internal/sessions/revoke``).
"""

import pytest
from allauth.usersessions.models import UserSession
from django.contrib.auth import get_user_model
from django.test import Client
from live.live_registry import live_registry

from accounts import events, signals
from accounts.tests.conftest import HOST, api_get, api_post, sign_in

pytestmark = pytest.mark.django_db

LIST = "/api/accounts/sessions"
CLOSE = "/api/accounts/sessions/close"
CLOSE_OTHERS = "/api/accounts/sessions/close_others"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130.0.6723.92 Safari/537.36"
APP = "Mozilla/5.0 (Linux; Android 14; wv) Chrome/130.0 Mobile Safari/537.36 ERPloraApp/4.0.2"


@pytest.fixture
def received():
    calls = []

    def sessions_ended(sender, user_id, **kwargs):
        calls.append(user_id)

    signals.sessions_ended.connect(sessions_ended, dispatch_uid="test-sessions-ops")
    yield calls
    signals.sessions_ended.disconnect(dispatch_uid="test-sessions-ops")


def _browser(email, password, user_agent, address="127.0.0.1"):
    client = Client(HTTP_USER_AGENT=user_agent, REMOTE_ADDR=address)
    return sign_in(client, email, password)


@pytest.fixture
def laptop(ana, password):
    return _browser(ana.email, password, MAC, "81.33.10.4")


@pytest.fixture
def phone(ana, password):
    return _browser(ana.email, password, APP, "88.12.0.7")


class TestTheList:
    def test_each_session_with_its_device_browser_address_and_last_use_this_one_first(self, laptop, phone, ana):
        rows = api_get(laptop, LIST).json()["rows"]

        assert [
            (row["device"], row["browser"], row["browser_version"], row["app_version"], row["ip"], row["is_current"])
            for row in rows
        ] == [
            ("mac", "Chrome", "130", None, "81.33.10.4", True),
            ("android", "", "", "4.0.2", "88.12.0.7", False),
        ]
        assert {"id", "created_at", "last_seen_at"} <= set(rows[0])
        assert api_get(laptop, LIST).json()["total"] == 2

    def test_a_session_that_ended_is_not_listed(self, laptop, phone):
        phone.delete("/_allauth/browser/v1/auth/session", HTTP_HOST=HOST)  # «Sign out» on the phone

        assert [row["is_current"] for row in api_get(laptop, LIST).json()["rows"]] == [True]

    def test_a_session_left_behind_by_a_password_change_is_not_listed(self, laptop, phone, ana):
        """Django ends the other sessions when the password changes (their hash no longer matches)."""
        ana.set_password("another long password 42")
        ana.save()
        session = laptop.session
        session["_auth_user_hash"] = get_user_model().objects.get(pk=ana.pk).get_session_auth_hash()
        session.save()

        assert len(api_get(laptop, LIST).json()["rows"]) == 1

    def test_only_the_accounts_own_sessions(self, laptop, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _browser(bo.email, password, MAC)

        assert len(api_get(laptop, LIST).json()["rows"]) == 1

    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_get(client, LIST).status_code == 401

    def test_closing_re_runs_the_live_list(self):
        assert "accounts.session.list" in live_registry.affected([events.SESSION_CLOSED])


class TestClosingOne:
    def test_closing_the_phone_signs_it_out_and_asks_the_businesses_too(self, laptop, phone, ana, received):
        [row] = [row for row in api_get(laptop, LIST).json()["rows"] if not row["is_current"]]

        response = api_post(laptop, CLOSE, {"id": row["id"]})

        assert response.json() == {"closed": 1}
        assert api_get(phone, LIST).status_code == 401
        assert api_get(laptop, LIST).status_code == 200
        assert received == [ana.pk]

    def test_closing_this_session_signs_out(self, laptop):
        [row] = [row for row in api_get(laptop, LIST).json()["rows"] if row["is_current"]]

        assert api_post(laptop, CLOSE, {"id": row["id"]}).json() == {"closed": 1}
        assert api_get(laptop, LIST).status_code == 401

    def test_a_session_of_another_account_is_not_found(self, laptop, password, received):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        bos = _browser(bo.email, password, MAC)
        other = UserSession.objects.get(session_key=bos.session.session_key)

        response = api_post(laptop, CLOSE, {"id": other.pk})

        assert (response.status_code, response.json()["error"]["code"]) == (404, "not_found")
        assert api_get(bos, LIST).status_code == 200
        assert received == []

    def test_the_event_is_recorded(self, laptop, phone):
        from live.models import OutboxEvent

        [row] = [row for row in api_get(laptop, LIST).json()["rows"] if not row["is_current"]]
        api_post(laptop, CLOSE, {"id": row["id"]})

        assert list(OutboxEvent.objects.values_list("name", flat=True)) == [events.SESSION_CLOSED]


class TestClosingTheOthers:
    def test_every_other_session_ends_this_one_stays(self, laptop, phone, ana, password, received):
        tablet = _browser(ana.email, password, MAC)

        response = api_post(laptop, CLOSE_OTHERS)

        assert response.json() == {"closed": 2}
        assert api_get(phone, LIST).status_code == 401
        assert api_get(tablet, LIST).status_code == 401
        assert [row["is_current"] for row in api_get(laptop, LIST).json()["rows"]] == [True]
        assert received == [ana.pk]

    def test_alone_it_still_asks_the_businesses(self, laptop, ana, received):
        """«Close the other sessions» also closes the apps, whose sessions in the businesses may outlive their
        session here."""
        assert api_post(laptop, CLOSE_OTHERS).json() == {"closed": 0}
        assert received == [ana.pk]

    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_post(client, CLOSE_OTHERS).status_code == 401
