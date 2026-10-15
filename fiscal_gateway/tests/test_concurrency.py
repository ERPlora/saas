"""The gateway under ASGI, as Daphne serves it: presentations run side by side, not one after another.

The views are plain synchronous Django views. Django's ``ASGIHandler`` opens a ``ThreadSensitiveContext``
per request, so each request runs its synchronous code in a thread of its own: eight presentations
wait on the AEAT at once, and a slow one holds nobody else up. These tests go through the project's
real ASGI ``application`` (``config.asgi``), not through Django's ``AsyncClient``, whose handler opens
no such context and would run every request in one shared thread.

The AEAT is ``respx``'s, and it holds each presentation until the test lets it go: nothing depends on
how fast the machine is, and a gateway that served one request at a time would fail on the answers,
not only on the clock.
"""

import asyncio
import json
import threading
import time

import httpx
import pytest

from accounts.signing import sign
from config.asgi import application
from fiscal_gateway.tests.conftest import PASSWORD, b64, fixture, make_p12

SECRET = "test-internal-secret"
PRE_HOLDER = (
    "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
)
SENT = fixture("rotation_a_sent_2026-09-22.xml")
ANSWER = fixture("rotation_a_2026-09-22.xml")
HUB = "0199e8a0-0000-7000-8000-000000000001"
ISSUER = "B27593136"
#: The longest a held presentation waits for the test: a gateway that serialised would hit it.
WAIT = 5.0


@pytest.fixture(autouse=True)
def _secrets(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""


@pytest.fixture
def submission():
    """A signed ``submit`` body with the customer's own certificate, towards the AEAT's tests."""
    p12 = make_p12(org_id=f"VATES-{ISSUER}", serial="IDCES-12345678Z")
    return json.dumps(
        {
            "hub": HUB,
            "nif": ISSUER,
            "environment": "testing",
            "route": "own",
            "envelope": SENT,
            "certificate": {"p12_base64": b64(p12), "password": PASSWORD},
        }
    ).encode()


async def request(method, path, body=b"", *, signed=False, on_status=None):
    """``method path`` through the ASGI application; its status and its body."""
    headers = [
        (b"host", b"testserver"),
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    if signed:
        timestamp = int(time.time())
        headers += [
            (b"x-erplora-timestamp", str(timestamp).encode()),
            (b"x-erplora-signature", sign(body, timestamp, SECRET).encode()),
        ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    delivered = False
    connected = asyncio.Event()

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await connected.wait()  # The client never hangs up.

    status = None
    chunks = []

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
            if on_status:
                on_status(status)
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await application(scope, receive, send)
    return status, b"".join(chunks)


def test_presentations_run_side_by_side_up_to_the_cap_and_one_more_is_busy(
    settings, respx_mock, submission
):
    cap = settings.VERIFACTU_GATEWAY_CONCURRENCY
    lock = threading.Lock()
    inside = most = 0
    all_in = threading.Event()
    released = threading.Event()

    def held_aeat(_request):
        nonlocal inside, most
        with lock:
            inside += 1
            most = max(most, inside)
            if inside == cap:
                all_in.set()
        try:
            # Held until every slot is at the AEAT at once and the one too many has been answered.
            all_in.wait(WAIT)
            released.wait(WAIT)
        finally:
            with lock:
                inside -= 1
        return httpx.Response(200, text=ANSWER)

    route = respx_mock.post(PRE_HOLDER).mock(side_effect=held_aeat)

    def release_on_busy(status):
        if status == 503:
            released.set()

    async def all_at_once():
        return await asyncio.gather(
            *(
                request(
                    "POST",
                    "/internal/verifactu/submit",
                    submission,
                    signed=True,
                    on_status=release_on_busy,
                )
                for _ in range(cap + 1)
            )
        )

    started = time.monotonic()
    answers = asyncio.run(all_at_once())
    elapsed = time.monotonic() - started

    statuses = sorted(status for status, _ in answers)
    assert statuses == [200] * cap + [503]
    busy = next(json.loads(body) for status, body in answers if status == 503)
    assert busy["error"]["code"] == "gateway_busy"
    assert most == cap
    assert route.call_count == cap
    # One at a time, each held presentation would wait out WAIT: far beyond half a second each.
    assert elapsed < cap * 0.5


def test_a_slow_presentation_does_not_hold_up_another_request(respx_mock, submission):
    at_the_aeat = threading.Event()
    released = threading.Event()

    def slow_aeat(_request):
        at_the_aeat.set()
        released.wait(1.0)
        return httpx.Response(200, text=ANSWER)

    respx_mock.post(PRE_HOLDER).mock(side_effect=slow_aeat)

    async def health_during_a_presentation():
        slow = asyncio.create_task(
            request("POST", "/internal/verifactu/submit", submission, signed=True)
        )
        assert await asyncio.to_thread(at_the_aeat.wait, WAIT)
        started = time.monotonic()
        health = await request("GET", "/healthz")
        took = time.monotonic() - started
        released.set()
        return await slow, health, took

    (slow_status, _), (health_status, _), took = asyncio.run(
        health_during_a_presentation()
    )

    assert health_status == 200
    assert took < 0.5
    assert slow_status == 200
