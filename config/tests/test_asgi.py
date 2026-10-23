"""``config.asgi``: the client never decides the script prefix (ERPlora/saas#2).

Behind Daphne, a client's ``Daphne-Root-Path: /x`` header becomes ``scope["root_path"]`` (Daphne
always sends the full path, ``/x/admin/``). Django would then answer ``/x/admin/`` as ``/admin/`` and
send its redirects to ``/x/…``. ``application`` ignores that prefix: every request gets the answer of
its real path, the same with the header or without it.
"""

import asyncio
import json
from urllib.parse import urlsplit

import pytest
from asgiref.sync import async_to_sync
from daphne.utils import parse_x_forwarded_for
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from django.http import JsonResponse
from django.urls import path

from config.asgi import application

# The SPA reads the session through an operation (a transaction).
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("keep_the_test_connection"),
]

HOST = "localhost:8001"
SHELL_MARK = b'<div id="app"></div>'


@pytest.fixture
def keep_the_test_connection():
    """Django's real handler closes old connections when a request starts and ends, which would drop
    the test's own transaction; its test client unhooks them the same way."""
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    yield
    request_started.connect(close_old_connections)
    request_finished.connect(close_old_connections)


def http_scope(path: str, root_path: str) -> dict:
    """The scope Daphne builds for a browser's ``GET path`` (``root_path`` from ``Daphne-Root-Path``)."""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": root_path,
        "headers": [(b"host", HOST.encode()), (b"accept", b"text/html")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8001),
    }


async def _call(scope: dict) -> tuple[int, dict[str, str], bytes]:
    """Run ``application`` as Daphne would, in this context: Django's sync parts then run in the
    test's thread and transaction (``ApplicationCommunicator`` clears the context, which sends them to
    another thread with a connection of its own)."""
    inbox = asyncio.Queue()
    inbox.put_nowait({"type": "http.request", "body": b"", "more_body": False})
    sent = []

    async def send(message: dict) -> None:
        sent.append(message)

    # After the body, ``inbox.get`` waits like a client that stays connected until the response.
    await asyncio.wait_for(application(scope, inbox.get, send), timeout=10)
    start, *body = sent
    headers = {
        name.decode().lower(): value.decode() for name, value in start["headers"]
    }
    return (
        start["status"],
        headers,
        b"".join(message.get("body", b"") for message in body),
    )


def get(path: str, root_path: str = "") -> tuple[int, dict[str, str], bytes]:
    """``GET path`` through the ASGI application, in this thread (the test's) for the sync parts."""
    return async_to_sync(_call)(http_scope(path, root_path))


def outcome(response: tuple[int, dict[str, str], bytes]) -> tuple[int, str, str | None]:
    status, headers, _ = response
    return status, headers.get("content-type", ""), headers.get("location")


@pytest.mark.usefixtures("spa_manifest")
@pytest.mark.parametrize("path", ["/x/admin/", "/x/api/openapi.json"])
def test_a_client_root_path_changes_nothing(path):
    assert outcome(get(path, root_path="/x")) == outcome(get(path))


@pytest.mark.usefixtures("spa_manifest")
def test_a_client_root_path_does_not_reach_the_admin():
    status, headers, body = get("/x/admin/", root_path="/x")

    location = headers.get("location", "")
    assert not urlsplit(location).path.startswith("/x/")
    # /x/admin/ is no Django route: the SPA answers it, as it does without the header.
    assert (status, location) == (200, "")
    assert SHELL_MARK in body


# HTTPS behind the ALB (aws README, «Obligaciones de la app»): the ALB terminates TLS and reaches
# Daphne over plain HTTP on port 8000 with X-Forwarded-For, X-Forwarded-Port and X-Forwarded-Proto.
# Daphne runs with --proxy-headers (Dockerfile), which turns them into the scope's client and scheme,
# and Django's SECURE_PROXY_SSL_HEADER reads the same header: either way `request.is_secure()` holds
# (secure cookies, CSRF's origin check, absolute URLs).

ALB_HEADERS = [
    (b"x-forwarded-for", b"203.0.113.7"),
    (b"x-forwarded-port", b"443"),
    (b"x-forwarded-proto", b"https"),
]


def seen_by_django(request):
    return JsonResponse(
        {
            "secure": request.is_secure(),
            "scheme": request.scheme,
            "client": request.META["REMOTE_ADDR"],
        }
    )


# This module is the URLconf of the tests below (`as_seen_by_django`).
urlpatterns = [path("seen", seen_by_django)]


def daphne_scope(extra_headers: list, proxy_headers: bool) -> dict:
    """The scope Daphne builds for ``GET /seen`` that reached it over plain HTTP from the ALB's
    address, with ``--proxy-headers`` (as the Dockerfile runs it) or without."""
    headers = [(b"host", HOST.encode()), *extra_headers]
    client, scheme = ["10.0.1.20", 41000], "http"
    if proxy_headers:
        client, scheme = parse_x_forwarded_for(
            {name: [value] for name, value in headers},
            "X-Forwarded-For",
            "X-Forwarded-Port",
            "X-Forwarded-Proto",
            client,
            scheme,
        )
    return {
        **http_scope("/seen", root_path=""),
        "scheme": scheme,
        "headers": headers,
        "client": client,
    }


@pytest.fixture
def as_seen_by_django(settings):
    settings.ROOT_URLCONF = __name__

    def seen(scope: dict) -> dict:
        status, _headers, body = async_to_sync(_call)(scope)
        assert status == 200, body
        return json.loads(body)

    return seen


def test_a_request_through_the_alb_is_secure_with_daphne_proxy_headers(
    as_seen_by_django,
):
    scope = daphne_scope(ALB_HEADERS, proxy_headers=True)

    assert scope["scheme"] == "https"
    assert as_seen_by_django(scope) == {
        "secure": True,
        "scheme": "https",
        # The visitor's address, not the ALB's.
        "client": "203.0.113.7",
    }


def test_the_forwarded_proto_alone_makes_it_secure(as_seen_by_django):
    """Without --proxy-headers the scope says http: SECURE_PROXY_SSL_HEADER still reads the ALB's
    header."""
    seen = as_seen_by_django(daphne_scope(ALB_HEADERS, proxy_headers=False))

    assert (seen["secure"], seen["scheme"]) == (True, "https")


def test_plain_http_without_the_header_is_not_secure(as_seen_by_django):
    """hub-next calls /internal on the private name, straight to the task, over plain HTTP."""
    seen = as_seen_by_django(daphne_scope([], proxy_headers=True))

    assert (seen["secure"], seen["scheme"]) == (False, "http")


# ACCOUNTS-G72: erplora.com serves no WebSocket (no channels, PLAN-SAAS §1.1 point 2; the Hub's /ws/print is the
# Hub's). The old SaaS closed any unknown socket (`DenyConsumer`); Django's handler raises on a non-HTTP scope, which
# Daphne logs as an error on every attempt. The handshake is refused, nothing raises.


def websocket_scope(path: str) -> dict:
    return {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "scheme": "ws",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", HOST.encode())],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8001),
        "subprotocols": [],
    }


@pytest.mark.parametrize("path", ["/ws/", "/ws/assistant/", "/api/live", "/"])
def test_a_websocket_handshake_is_refused_without_an_error(path):
    inbox = asyncio.Queue()
    inbox.put_nowait({"type": "websocket.connect"})
    sent = []

    async def send(message: dict) -> None:
        sent.append(message)

    async_to_sync(asyncio.wait_for)(application(websocket_scope(path), inbox.get, send), timeout=5)

    assert sent == [{"type": "websocket.close", "code": 1008}]
