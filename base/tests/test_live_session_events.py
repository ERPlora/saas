"""A session that ends closes the tab of the panel it was open in, on any page (FIX-LIVE-SESSION-CLOSED-WAKES-ONLY-SESSION-LIST).

``LIVE["session_events"]`` lists ``accounts.session.closed``, which signing out, a new password and «Close the other
sessions» record on the account's channel (saas#144). Only ``accounts.session.list`` declares it in a ``live.py``, so
``live`` re-reads the context of every stream it reaches: the one whose session ended says ``bye`` (``base.operations``,
saas#142) and ``@erplora/ui`` takes its tab to the sign-in (ui#25); the others go on without re-running a query.
"""

import asyncio
from importlib import import_module

import pytest
from django.conf import settings
from django.core import checks
from django.test import Client, RequestFactory
from live import operations
from live.executor import BYE_FRAME, Executor, Stream, Subscription
from live.live_registry import session_events
from live.operations import get as get_operation

from accounts import events
from accounts.tests.conftest import BROWSER, HOST, sign_in
from base.operations import UserContextBuilder

#: What a tab of each page of the panel subscribes to; none of these queries declares ``accounts.session.closed``.
PAGES = {
    "businesses": [("businesses", "hubs.business.list", {})],
    "profile": [("profile", "accounts.profile.get", {}), ("preferences", "accounts.preferences.get", {})],
}


def test_the_platform_lists_the_account_session_event():
    assert session_events() == {events.SESSION_CLOSED}


def test_the_session_events_pass_the_live_checks():
    assert [message for message in checks.run_checks(tags=["live"]) if message.id == "live.E019"] == []


def tab(browser, user, page) -> Stream:
    """The ``/api/live`` stream of ``browser``'s tab on ``page``: opened with its cookie's session, as
    ``AuthenticationMiddleware`` hands it to the stream once."""
    request = RequestFactory().get("/api/live", HTTP_HOST=HOST)
    request.user = user
    request.LANGUAGE_CODE = "en"
    request.session = import_module(settings.SESSION_ENGINE).SessionStore(session_key=browser.session.session_key)
    stream = Stream(UserContextBuilder().from_request(request))
    for sub_id, op_name, params in PAGES[page]:
        op = get_operation(op_name)
        stream.subs[sub_id] = Subscription(sub_id, op, op.input(**params))
    return stream


@pytest.fixture
def notified(monkeypatch):
    """Every notification sent after a COMMIT, ``(scope, names)``, instead of ``pg_notify``."""
    heard = []
    monkeypatch.setattr(operations, "notify_hook", lambda scope, names: heard.append((scope, list(names))))
    return heard


def deliver(notified, *streams, wait: float = 0.5) -> list[list[bytes]]:
    """Hand each stream the notifications of its channel, as the broker does, and the frames each one queued."""

    async def run():
        executor = Executor(debounce=0.01)
        try:
            for scope, names in notified:
                for stream in streams:
                    if scope.channel == stream.channel:
                        await executor.on_events(stream, names)
            await asyncio.sleep(wait)
        finally:
            executor.reset()
            executor.shutdown()
        return [[stream.queue.get_nowait() for _ in range(stream.queue.qsize())] for stream in streams]

    return asyncio.run(run())


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("page", PAGES)
def test_signing_out_in_another_tab_ends_the_tab_on_any_page(page, ana, password, notified):
    """Both tabs share the cookie: the other one signs out (allauth.headless's ``DELETE auth/session``)."""
    browser = sign_in(Client(), ana.email, password)
    stream = tab(browser, ana, page)

    assert browser.delete(f"{BROWSER}/auth/session", HTTP_HOST=HOST).status_code == 401
    assert [(scope.key, names) for scope, names in notified] == [(str(ana.pk), [events.SESSION_CLOSED])]

    assert deliver(notified, stream) == [[BYE_FRAME]]
    assert stream.closed


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("page", PAGES)
def test_a_tab_whose_session_lives_stays_and_reruns_nothing(page, ana, password, notified, monkeypatch):
    """«Close the other sessions» in the laptop ends the phone's session: the phone's tab leaves, the laptop's stays,
    and none of their queries re-runs for the event."""
    laptop = sign_in(Client(), ana.email, password)
    phone = sign_in(Client(), ana.email, password)
    laptop_tab, phone_tab = tab(laptop, ana, page), tab(phone, ana, page)
    runs = []
    monkeypatch.setattr(Executor, "_run_one", lambda self, stream, sub: runs.append(sub.id))

    response = laptop.post("/api/accounts/sessions/close_others", content_type="application/json", HTTP_HOST=HOST)

    assert response.status_code == 200, response.content
    assert deliver(notified, laptop_tab, phone_tab) == [[], [BYE_FRAME]]
    assert (laptop_tab.closed, phone_tab.closed, runs) == (False, True, [])
