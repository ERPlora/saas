"""``hubs.hub_client``: the SaaS's signed calls to hub-next's ``/internal`` (PLAN-SAAS §2, §3.1, §3.4).

Against the Hub double: each call goes to its route with its method, signed with HMAC-SHA256 +
timestamp as ``accounts.signing`` signs (the scheme ``/internal/auth/redeem`` already verifies), and
each body names the hub of its path (the signature covers the body only). A 4xx is the Hub refusing
(``HubRefused``, with its code); a 5xx, a timeout or no answer is the Hub being away
(``HubUnavailable``): the caller keeps the work pending and ``reconcile_hub_states`` retries it.
"""

import time
import uuid

import pytest

from accounts.signing import verify, verify_signed
from hubs import hub_client
from hubs.hub_client import HubRefused, HubUnavailable
from hubs.tests.conftest import SECRET

HUB_ID = str(uuid.uuid7())
REGISTRY = {
    "id": HUB_ID,
    "slug": "bar-manolo",
    "name": "Bar Manolo",
    "country": "ES",
    "timezone": "Europe/Madrid",
    "language": "es",
    "vertical": "restaurant",
}
SNAPSHOT = {
    "hub_id": HUB_ID,
    "version": 3,
    "status": "active",
    "plan": {
        "slug": "free",
        "included_level": "free",
        "max_devices": 1,
        "max_users": 3,
        "max_db_connections": 1,
        "statement_timeout_seconds": 5,
        "max_apps": 20,
    },
    "modules": [],
    "members": [],
}


def test_the_hub_is_reached_on_its_private_address_by_default(settings):
    """Local development: hub-next's runserver; production sets HUB_INTERNAL_URL (aws-next, Cloud Map)."""
    assert settings.HUB_INTERNAL_URL == "http://localhost:8000"


def test_every_call_is_signed_as_the_hub_verifies_it(hub_double):
    hub_client.put_hub(REGISTRY)

    (call,) = hub_double.calls
    assert call.signed
    assert int(call.headers["X-Erplora-Timestamp"]) == pytest.approx(time.time(), abs=5)
    assert call.headers["Content-Type"] == "application/json"


def test_a_body_signed_with_another_secret_is_refused(hub_double, settings):
    settings.INTERNAL_SHARED_SECRET = "not-the-hubs"

    with pytest.raises(HubRefused) as refused:
        hub_client.put_hub(REGISTRY)

    assert (refused.value.status, refused.value.code) == (401, "unauthorized")
    assert not hub_double.calls[0].signed


def test_put_hub_registers_the_business_and_the_hub_answers_202(hub_double):
    answer = hub_client.put_hub(REGISTRY)

    assert answer.status == 202
    (call,) = hub_double.calls_to("PUT", HUB_ID)
    assert (call.path, call.body) == (f"/internal/hubs/{HUB_ID}", REGISTRY)


def test_put_hub_again_is_idempotent(hub_double):
    hub_client.put_hub(REGISTRY)

    assert hub_client.put_hub({**REGISTRY, "name": "Bar Manolo 2"}).status == 200


def test_put_state_sends_the_snapshot(hub_double):
    answer = hub_client.put_state(HUB_ID, SNAPSHOT)

    assert (answer.status, answer.body["applied"]) == (200, True)
    (call,) = hub_double.calls_to("PUT", "/state")
    assert (call.path, call.body) == (f"/internal/hubs/{HUB_ID}/state", SNAPSHOT)


def test_get_hub_reads_the_registry(hub_double):
    hub_client.put_hub(REGISTRY)

    assert hub_client.get_hub(HUB_ID).body == {"status": "requested"}
    assert hub_double.calls_to("GET")[0].path == f"/internal/hubs/{HUB_ID}"


def test_delete_and_restore_name_their_hub_in_the_body(hub_double):
    assert hub_client.delete_hub(HUB_ID).status == 202
    assert hub_client.restore_hub(HUB_ID).status == 200

    delete, restore = (
        hub_double.calls_to("DELETE")[0],
        hub_double.calls_to("POST", "/restore")[0],
    )
    assert (delete.path, delete.body) == (f"/internal/hubs/{HUB_ID}", {"id": HUB_ID})
    assert (restore.path, restore.body) == (
        f"/internal/hubs/{HUB_ID}/restore",
        {"id": HUB_ID},
    )


def test_revoke_sessions_of_one_account_in_one_hub_or_in_all(hub_double):
    user_id = str(uuid.uuid7())

    hub_client.revoke_sessions(user_id, HUB_ID)
    hub_client.revoke_sessions(user_id)

    first, second = hub_double.calls_to("POST", "/internal/sessions/revoke")
    assert first.body == {"user_id": user_id, "hub_id": HUB_ID}
    assert second.body == {"user_id": user_id}


def test_a_4xx_is_the_hub_refusing_with_its_code(hub_double):
    hub_double.answer(
        "POST", "/restore$", 409, {"error": {"code": "hub_purged", "message": "Gone."}}
    )

    with pytest.raises(HubRefused) as refused:
        hub_client.restore_hub(HUB_ID)

    assert (refused.value.status, refused.value.code) == (409, "hub_purged")


def test_a_5xx_is_the_hub_being_away(hub_double):
    hub_double.answer("PUT", "/state$", 503, {"error": {"code": "unavailable"}})

    with pytest.raises(HubUnavailable):
        hub_client.put_state(HUB_ID, SNAPSHOT)


def test_no_answer_at_all_is_the_hub_being_away(offline_hub):
    with pytest.raises(HubUnavailable):
        hub_client.put_hub(REGISTRY)


def test_a_slow_hub_is_given_up_on(hub_double, monkeypatch):
    monkeypatch.setattr(hub_client, "TIMEOUT_SECONDS", 0.2)
    hub_double.delay = 1

    with pytest.raises(HubUnavailable):
        hub_client.put_hub(REGISTRY)


def test_a_signature_covers_its_own_body_and_no_other(settings):
    """The scheme the double and the Hub share: v1 signs the body and the timestamp, keyed by the secret."""
    settings.INTERNAL_SHARED_SECRET = SECRET
    body, now = b'{"id": "x"}', int(time.time())
    signed = hub_client.signed_headers("PUT", f"/internal/hubs/{HUB_ID}", body, now)

    timestamp, signature = signed["X-Erplora-Timestamp"], signed["X-Erplora-Signature"]
    assert verify(body, timestamp, signature, secret=SECRET, now=now)
    assert not verify(b'{"id": "y"}', timestamp, signature, secret=SECRET, now=now)


def test_every_call_also_signs_its_method_and_path(hub_double):
    """L1-A2 (PLAN-SAAS §2.1): ``X-Erplora-Signature-V2`` covers method, path, timestamp and body; the
    double, as the Hub will, judges a call that carries it by it alone."""
    hub_client.put_state(HUB_ID, SNAPSHOT)
    hub_client.revoke_sessions(str(uuid.uuid7()))

    state, revoke = hub_double.calls
    assert state.signed_v2 and revoke.signed_v2
    headers = dict(state.headers)
    raw = state.raw
    assert verify_signed("PUT", f"/internal/hubs/{HUB_ID}/state", raw, headers, secrets=[SECRET], now=int(time.time()))
    assert not verify_signed("PUT", f"/internal/hubs/{HUB_ID}", raw, headers, secrets=[SECRET], now=int(time.time()))


def test_the_client_signs_with_the_current_secret_only(hub_double, settings):
    """During a rotation the previous secret is only accepted, never used to sign."""
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = "the-secret-before-the-rotation"
    hub_client.put_hub(REGISTRY)

    (call,) = hub_double.calls
    assert verify_signed("PUT", call.path, call.raw, call.headers, secrets=[SECRET], now=int(time.time()))
    assert not verify_signed(
        "PUT", call.path, call.raw, call.headers, secrets=["the-secret-before-the-rotation"], now=int(time.time())
    )


def test_a_broken_answer_is_the_hub_being_away(monkeypatch, settings):
    """Review of L1-A: a connection cut mid-answer raises ``http.client.HTTPException``, not ``OSError``."""
    import http.client

    def broken(*args, **kwargs):
        raise http.client.BadStatusLine("garbage")

    monkeypatch.setattr(hub_client.urllib.request, "urlopen", broken)

    with pytest.raises(HubUnavailable):
        hub_client.put_hub(REGISTRY)


# --- GET /internal/usage: one day's usage of every business (L4-A, PLAN-SAAS §5) --------------------

from datetime import date  # noqa: E402

USAGE_ROW = {"id": HUB_ID, "s3_bytes": 1_000, "db_bytes": 2_000, "active_users_1d": 3, "active_users_30d": 4}


def test_get_usage_asks_for_one_day_signed_with_its_query(hub_double):
    hub_double.usage["2026-10-13"] = [USAGE_ROW]

    answer = hub_client.get_usage(date(2026, 10, 13))

    assert answer.status == 200
    assert answer.body == {"day": "2026-10-13", "hubs": [USAGE_ROW], "next_cursor": None}
    (call,) = hub_double.calls_to("GET")
    assert call.path == "/internal/usage?day=2026-10-13"
    # v2 covers the query too: the same signature does not open another day.
    assert call.signed_v2
    assert not verify_signed(
        "GET", "/internal/usage?day=2026-10-12", call.raw, call.headers, secrets=[SECRET], now=int(time.time())
    )


def test_get_usage_sends_the_hubs_cursor_back_as_it_came(hub_double):
    hub_double.answer("GET", r"^/internal/usage", 200, {"day": "2026-10-13", "hubs": [], "next_cursor": None})

    hub_client.get_usage(date(2026, 10, 13), cursor="page/2=")

    (call,) = hub_double.calls_to("GET")
    assert call.path == "/internal/usage?day=2026-10-13&cursor=page%2F2%3D"


def test_get_usage_refused_or_away_as_every_call(hub_double):
    hub_double.answer("GET", r"^/internal/usage", 409, {"error": {"code": "usage_not_ready", "message": "Not yet."}})

    with pytest.raises(HubRefused) as refused:
        hub_client.get_usage(date(2026, 10, 13))

    assert (refused.value.status, refused.value.code) == (409, "usage_not_ready")


# --- POST /internal/demos and /internal/demos/{slug}/codes: the demo hubs (round 2026-10-17) --------

import re  # noqa: E402

#: What the SaaS sends for a browser: the sha256 hex of a token of its session, never the cookie.
BROWSER = "ab" * 32
OTHER_BROWSER = "cd" * 32


def test_create_demo_asks_the_hub_for_a_demo_of_this_browser(hub_double):
    answer = hub_client.create_demo(BROWSER, vertical=None, language="es")

    assert answer.status == 201
    assert re.fullmatch(r"demo-[0-9a-f]{8}", answer.body["slug"])
    assert answer.body["created"] is True
    (call,) = hub_double.calls_to("POST", "/internal/demos")
    assert call.path == "/internal/demos"
    assert call.body == {"session_key": BROWSER, "vertical": None, "language": "es"}
    assert call.signed_v2


def test_create_demo_again_from_the_same_browser_is_the_same_demo(hub_double):
    first = hub_client.create_demo(BROWSER, vertical=None, language="en")

    again = hub_client.create_demo(BROWSER, vertical=None, language="en")

    assert (again.status, again.body["created"], again.body["slug"]) == (200, False, first.body["slug"])


def test_a_full_demo_is_the_hub_refusing_not_the_hub_being_away(hub_double):
    """503 ``base.demo_full`` is a deliberate answer (the global cap of live demos): the page says «full»."""
    hub_double.answer(
        "POST", r"^/internal/demos$", 503, {"error": {"code": "base.demo_full", "message": "Full."}}
    )

    with pytest.raises(HubRefused) as refused:
        hub_client.create_demo(BROWSER, vertical=None, language="en")

    assert (refused.value.status, refused.value.code) == (503, "base.demo_full")


def test_any_other_5xx_of_a_demo_is_the_hub_being_away(hub_double):
    hub_double.answer("POST", r"^/internal/demos$", 503, {"error": {"code": "unavailable"}})

    with pytest.raises(HubUnavailable):
        hub_client.create_demo(BROWSER, vertical=None, language="en")


def test_only_the_demo_reads_a_full_cap_as_a_refusal(hub_double):
    """The other calls keep «5xx = away», whatever the code: their work stays pending and is retried."""
    hub_double.answer("PUT", "/state$", 503, {"error": {"code": "base.demo_full"}})

    with pytest.raises(HubUnavailable):
        hub_client.put_state(HUB_ID, SNAPSHOT)


def test_create_demo_code_asks_for_a_one_time_code_of_that_demo(hub_double):
    slug = hub_client.create_demo(BROWSER, vertical=None, language="en").body["slug"]

    answer = hub_client.create_demo_code(slug, BROWSER, language="es")

    assert answer.status == 201
    assert answer.body["code"]
    (call,) = hub_double.calls_to("POST", "/codes")
    assert call.path == f"/internal/demos/{slug}/codes"
    assert call.body == {"session_key": BROWSER, "language": "es"}
    assert call.signed_v2


@pytest.mark.parametrize(
    ("status", "code"),
    [(410, "base.hub_gone"), (404, "not_found"), (403, "base.demo_not_owner")],
)
def test_a_code_the_hub_will_not_mint_is_refused_with_its_code(hub_double, status, code):
    hub_double.answer("POST", r"/codes$", status, {"error": {"code": code, "message": "No."}})

    with pytest.raises(HubRefused) as refused:
        hub_client.create_demo_code("demo-0123abcd", OTHER_BROWSER, language="en")

    assert (refused.value.status, refused.value.code) == (status, code)


def test_an_error_that_is_not_an_object_is_still_a_refusal(hub_double):
    """``{"error": "…"}`` (not the envelope) must not turn a 4xx into an ``AttributeError`` of the client."""
    hub_double.answer("POST", r"/codes$", 403, {"error": "forbidden"})

    with pytest.raises(HubRefused) as refused:
        hub_client.create_demo_code("demo-0123abcd", BROWSER, language="en")

    assert (refused.value.status, refused.value.code) == (403, "refused")
