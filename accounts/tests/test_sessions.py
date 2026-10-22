"""Account → Security → Active sessions: ``accounts.session.list``, ``accounts.session.close`` and
``accounts.session.close_others`` (plan 2026-10-13, L3-A; ``allauth.usersessions``, PLAN-SAAS §6).

Ported from ERPlora/saas ``apps/dashboard/profile`` (``sessions``, ``handle_session_action``), whose sessions
were JWT refresh tokens: here they are the browser sessions of the SaaS. The location is the address (GeoIP is
out of scope, plan §6). Closing a session also asks every business to end the account's sessions there
(PLAN-SAAS §2.1; ``signals.sessions_ended``, which hubs turns into ``POST /internal/sessions/revoke``).
"""

import json
import string
from datetime import timedelta
from importlib import import_module

import pytest
from allauth.usersessions.models import UserSession
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.crypto import get_random_string
from live.executor import Executor, Stream, Subscription
from live.live_registry import live_registry
from live.operations import get
from live.sse import MAX_RESULT_BYTES

from accounts import events, signals
from accounts.tests.conftest import HOST, api_get, api_post, ctx_for, sign_in

pytestmark = pytest.mark.django_db

LIST = "/api/accounts/sessions"
CLOSE = "/api/accounts/sessions/close"
CLOSE_OTHERS = "/api/accounts/sessions/close_others"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130.0.6723.92 Safari/537.36"
APP = "Mozilla/5.0 (Linux; Android 14; wv) Chrome/130.0 Mobile Safari/537.36 ERPloraApp/4.0.2"
#: Sessions whose rows add up to more than one live result carries (every row is well over 150 bytes).
PAST_THE_CAP = MAX_RESULT_BYTES // 150


def _session_store():
    return import_module(settings.SESSION_ENGINE).SessionStore


def _more_sessions(user, count: int) -> list[str]:
    """``count`` more sessions that still sign ``user`` in, used one minute apart before now, as as many sign-ins
    on other browsers leave them. Written in bulk: as many sign-ins through allauth would take minutes."""
    store = _session_store()
    model = store.get_model_class()
    data = store().encode(
        {
            SESSION_KEY: str(user.pk),
            BACKEND_SESSION_KEY: settings.AUTHENTICATION_BACKENDS[0],
            HASH_SESSION_KEY: user.get_session_auth_hash(),
        }
    )
    now = timezone.now()
    keys = [get_random_string(32, string.ascii_lowercase + string.digits) for _ in range(count)]
    model.objects.bulk_create(model(session_key=key, session_data=data, expire_date=now + timedelta(days=1)) for key in keys)
    UserSession.objects.bulk_create(
        UserSession(user=user, session_key=key, ip="81.33.10.4", user_agent=MAC, last_seen_at=now - timedelta(minutes=n + 1))
        for n, key in enumerate(keys)
    )
    return keys


def _live_frame(client, user, **params) -> bytes:
    """The frame ``/api/live`` sends ``client``'s browser for ``accounts.session.list``: the executor's own run."""
    request = RequestFactory().get("/")
    request.session = _session_store()(client.session.session_key)
    op = get("accounts.session.list")
    return Executor()._run_in_language(Stream(ctx_for(user, request=request)), Subscription("sessions", op, op.input(**params)))


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

    def test_a_session_that_expired_is_not_listed(self, laptop, phone):
        model = _session_store().get_model_class()
        model.objects.filter(session_key=phone.session.session_key).update(expire_date=timezone.now() - timedelta(seconds=1))

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


class TestALongList:
    """An account with more sessions than one live result carries (the sign-ins of the end-to-end runs) still
    sees its list: the server pages it, this session first (FIX-SAAS-SESSIONS-RESULT-TOO-BIG)."""

    def test_the_live_list_loads_with_more_sessions_than_a_result_carries(self, laptop, ana):
        _more_sessions(ana, PAST_THE_CAP)

        sent = _live_frame(laptop, ana)

        assert sent.startswith(b"event: result\n"), sent[:300]
        data = json.loads(sent.split(b"\ndata: ", 1)[1])["data"]
        assert (data["total"], data["rows"][0]["is_current"]) == (PAST_THE_CAP + 1, True)

    def test_a_page_holds_its_limit_this_session_first_and_the_total_counts_them_all(self, laptop, ana):
        keys = _more_sessions(ana, 30)
        UserSession.objects.filter(session_key=keys[-1]).update(last_seen_at=timezone.now() + timedelta(minutes=5))

        pages = [api_get(laptop, LIST, limit=10, offset=offset).json() for offset in (0, 10, 20, 30)]

        assert [len(page["rows"]) for page in pages] == [10, 10, 10, 1]
        assert {page["total"] for page in pages} == {31}
        assert [(page["limit"], page["offset"]) for page in pages] == [(10, 0), (10, 10), (10, 20), (10, 30)]
        rows = [row for page in pages for row in page["rows"]]
        assert [row["is_current"] for row in rows] == [True] + [False] * 30, "this session first, even used before others"
        assert rows[1]["id"] == UserSession.objects.get(session_key=keys[-1]).pk
        assert len({row["id"] for row in rows}) == 31
        others = [row["last_seen_at"] for row in rows[1:]]
        assert others == sorted(others, reverse=True)

    def test_a_page_past_the_end_is_empty_and_still_counts_them_all(self, laptop, phone):
        page = api_get(laptop, LIST, limit=10, offset=10).json()

        assert (page["rows"], page["total"]) == ([], 2)

    def test_a_page_never_holds_more_than_the_servers_maximum(self, laptop):
        response = api_get(laptop, LIST, limit=101)

        assert response.status_code == 422
        assert "limit" in response.json()["error"]["fields"]

    def test_the_other_sessions_are_counted_on_every_page(self, laptop, ana):
        _more_sessions(ana, 30)

        assert [api_get(laptop, LIST, limit=10, offset=offset).json()["others"] for offset in (0, 20)] == [30, 30]

    def test_which_sessions_still_sign_in_costs_the_same_queries_however_many(self, laptop, ana):
        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                assert api_get(laptop, LIST, limit=10).status_code == 200
            return len(captured)

        _more_sessions(ana, 5)
        queries()  # «last used» is recorded at most every few minutes: the first request may record it
        few = queries()
        _more_sessions(ana, 50)

        assert queries() == few


class TestSigningIn:
    """Each sign-in drops the account's sessions that no longer sign it in and records its own. allauth's
    ``purge_and_list`` did it one session at a time, about three queries for each open one: with 1680 sessions of
    one account the SaaS answered the mailed code after 30 and 37 s (FIX-HUB-E2E-LOGIN-FLAKY-UNDER-LOAD)."""

    def test_signing_in_costs_the_same_queries_however_many_sessions_the_account_has(self, ana, password):
        def queries() -> int:
            client = Client(HTTP_USER_AGENT=MAC, REMOTE_ADDR="81.33.10.4")
            with CaptureQueriesContext(connection) as captured:
                sign_in(client, ana.email, password)
            return len(captured)

        queries()  # the first sign-in also proves the address
        few = queries()
        _more_sessions(ana, 50)

        assert queries() == few

    def test_the_sessions_that_no_longer_sign_in_go_and_the_others_stay(self, ana, password):
        store = _session_store()
        model = store.get_model_class()
        live = _more_sessions(ana, 2)
        expired, stale, gone = _more_sessions(ana, 3)
        model.objects.filter(session_key=expired).update(expire_date=timezone.now() - timedelta(minutes=1))
        model.objects.filter(session_key=stale).update(
            session_data=store().encode({SESSION_KEY: str(ana.pk), BACKEND_SESSION_KEY: settings.AUTHENTICATION_BACKENDS[0], HASH_SESSION_KEY: "stale"})
        )
        model.objects.filter(session_key=gone).delete()

        client = sign_in(Client(HTTP_USER_AGENT=MAC, REMOTE_ADDR="81.33.10.4"), ana.email, password)

        assert set(UserSession.objects.filter(user=ana).values_list("session_key", flat=True)) == {*live, client.session.session_key}

    def test_a_session_signed_in_meanwhile_on_another_device_stays(self, ana, password, monkeypatch):
        """Two sign-ins of one account at once: the one that is recorded while this one is telling the live sessions
        apart is not among them yet, and still must not go (it is live: its session row came first)."""
        from accounts import queries

        meanwhile = []
        live_sessions = queries.live_sessions

        def live_sessions_while_another_device_signs_in(user):
            live = live_sessions(user)
            meanwhile.extend(_more_sessions(user, 1))
            return live

        monkeypatch.setattr(queries, "live_sessions", live_sessions_while_another_device_signs_in)

        sign_in(Client(HTTP_USER_AGENT=MAC, REMOTE_ADDR="81.33.10.4"), ana.email, password)

        assert UserSession.objects.filter(user=ana, session_key__in=meanwhile).count() == 1


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

    def test_a_session_that_no_longer_signs_in_is_not_counted_among_the_closed(self, laptop, phone, ana, password):
        """«Sessions closed: n» counts the sessions that still signed in: one left behind by its expiry is ended too,
        but not counted (the count comes from ``live_sessions``, FIX-SAAS-SESSIONS-RESULT-TOO-BIG)."""
        tablet = _browser(ana.email, password, MAC)
        model = _session_store().get_model_class()
        model.objects.filter(session_key=phone.session.session_key).update(expire_date=timezone.now() - timedelta(seconds=1))

        assert api_post(laptop, CLOSE_OTHERS).json() == {"closed": 1}
        assert api_get(tablet, LIST).status_code == 401
        assert [row["is_current"] for row in api_get(laptop, LIST).json()["rows"]] == [True]

    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_post(client, CLOSE_OTHERS).status_code == 401
