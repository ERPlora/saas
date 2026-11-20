"""``/demo/start/``: asking the Hub for a demo of this browser (public/demo.py)."""

import json
import re

import pytest
from django.conf import settings
from django.test import Client

from public.tests.demo_pages import DOOR, START, STATUS, demo_calls, page, start, state_of

pytestmark = pytest.mark.usefixtures("demo_settings")


# --- /demo/start/ -----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_starting_asks_the_hub_for_a_demo_and_waits_on_the_door_while_it_is_prepared(client, hub_double):
    """The Hub answers 202 «requested» and prepares the demo afterwards: the browser waits on the door, never on the
    demo's host (which answers 503 until it is ready), and the session knows which demo it waits for."""
    response = client.post(START)

    (call,) = demo_calls(hub_double)
    ((slug, demo),) = hub_double.demos.items()
    assert response.status_code == 302
    assert response["Location"] == DOOR
    assert call.signed_v2
    assert set(call.body) == {"session_key", "vertical", "language"}
    assert (call.body["vertical"], call.body["language"]) == (None, "en")
    assert client.session["demo"] == {
        "id": demo["id"],
        "slug": slug,
        "expires_at": demo["expires_at"].isoformat(),
        "ready": False,
    }


@pytest.mark.django_db
def test_the_door_of_a_demo_being_prepared_says_so_and_asks_the_hub_nothing(client, hub_double):
    start(client, hub_double, ready=False)
    hub_double.calls.clear()

    html = page(client.get(DOOR))

    assert state_of(html) == "preparing"
    assert "Preparing your demo…" in html
    assert 'role="status"' in html
    assert f'data-demo-status-url="{STATUS}"' in html
    assert f'data-demo-timeout-url="{DOOR}?state=not_ready"' in html
    assert 'data-testid="demo-start"' not in html
    assert "Back to my demo" not in html
    assert hub_double.calls == []


@pytest.mark.django_db
def test_an_older_hub_that_answers_a_ready_demo_jumps_into_it_at_once(client, hub_double):
    """The Hub before the asynchronous demo answers 201 without ``status``: its demo is ready as it answers."""
    hub_double.answer(
        "POST", r"^/internal/demos$", 201,
        {"id": "0193a0c4-0000-7000-8000-000000000001", "slug": "demo-0123abcd", "expires_at": "2099-01-01T00:00:00+00:00", "created": True},
    )

    response = client.post(START)

    assert response["Location"] == "http://demo-0123abcd.localhost:8000/auth/login?next=/"
    assert client.session["demo"]["ready"] is True


@pytest.mark.django_db
def test_the_live_demo_the_hub_gives_back_ready_jumps_into_it_at_once(client, hub_double):
    slug = start(client, hub_double)

    response = client.post(START)

    assert response["Location"] == f"http://{slug}.localhost:8000/auth/login?next=/"
    assert len(demo_calls(hub_double)) == 2


@pytest.mark.django_db
def test_the_live_demo_the_hub_gives_back_still_being_prepared_waits_again(client, hub_double):
    slug = start(client, hub_double, ready=False)

    response = client.post(START)

    assert response["Location"] == DOOR
    assert client.session["demo"]["slug"] == slug
    assert client.session["demo"]["ready"] is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {"slug": "demo-0123abcd", "status": "requested", "expires_at": "2099-01-01T00:00:00+00:00"},
        {"id": "not-a-uuid", "slug": "demo-0123abcd", "status": "requested", "expires_at": "2099-01-01T00:00:00+00:00"},
        {"id": "0193a0c4-0000-7000-8000-000000000001", "slug": "demo-0123abcd", "status": "purged", "expires_at": "2099-01-01T00:00:00+00:00"},
    ],
)
def test_a_demo_that_cannot_be_waited_for_is_not_available(client, hub_double, body, caplog):
    """A demo being prepared without its id cannot be asked about, and an ended one is no demo to wait for."""
    hub_double.answer("POST", r"^/internal/demos$", 202, body)

    response = client.post(START)

    assert response["Location"] == f"{DOOR}?state=unavailable"
    assert "demo" not in client.session
    assert "demo.start.bad_answer" in caplog.text


@pytest.mark.django_db
def test_the_hub_gets_a_hash_of_the_browser_never_its_cookie(client, hub_double):
    start(client, hub_double)

    (call,) = demo_calls(hub_double)
    cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
    assert re.fullmatch(r"[0-9a-f]{64}", call.body["session_key"])
    assert cookie not in json.dumps(call.body)


@pytest.mark.django_db
def test_another_browser_is_another_demo(client, hub_double):
    first = start(client, hub_double)

    second = start(Client(), hub_double)

    assert first != second
    one, other = demo_calls(hub_double)
    assert one.body["session_key"] != other.body["session_key"]


@pytest.mark.django_db
def test_the_same_browser_gets_the_same_demo_and_spends_no_quota(client, hub_double, settings):
    """With room for two new demos an hour: the second press of the same browser is not one of them."""
    settings.DEMO_SPAWN_RATELIMIT = "2/h"

    first = start(client, hub_double)
    again = start(client, hub_double)
    other = start(Client(), hub_double)
    limited = Client().post(START)

    assert again == first
    assert other != first
    assert limited["Location"] == f"{DOOR}?state=throttled"


@pytest.mark.django_db
def test_a_fourth_new_demo_from_one_address_is_throttled(hub_double):
    for _ in range(3):
        start(Client(), hub_double)
    fourth = Client()

    response = fourth.post(START)

    assert response["Location"] == f"{DOOR}?state=throttled"
    assert len(demo_calls(hub_double)) == 3
    assert "demo" not in fourth.session
    assert state_of(page(fourth.get(response["Location"]))) == "throttled"


@pytest.mark.django_db
def test_a_full_hub_says_so(client, hub_double):
    hub_double.answer("POST", r"^/internal/demos$", 503, {"error": {"code": "base.demo_full", "message": "Full."}})

    response = client.post(START)

    assert response["Location"] == f"{DOOR}?state=full"
    assert "demo" not in client.session


@pytest.mark.django_db
def test_an_absent_hub_means_the_demo_is_not_available(client, offline_hub, caplog):
    response = client.post(START)

    assert response["Location"] == f"{DOOR}?state=unavailable"
    assert "demo" not in client.session
    assert "demo.start.hub_unavailable" in caplog.text


@pytest.mark.django_db
def test_any_other_refusal_means_the_demo_is_not_available(client, hub_double, caplog):
    hub_double.answer("POST", r"^/internal/demos$", 422, {"error": {"code": "invalid_payload", "message": "?"}})

    response = client.post(START)

    assert response["Location"] == f"{DOOR}?state=unavailable"
    assert "demo.start.hub_refused" in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {"slug": "bar-manolo", "expires_at": "2099-01-01T00:00:00+00:00"},
        {"slug": "demo-0123abcd"},
        {"slug": "demo-0123abcd", "expires_at": "tomorrow"},
        {"slug": "demo-0123abcd", "expires_at": "2099-01-01T00:00:00"},
        {},
    ],
)
def test_an_answer_that_is_not_a_demo_never_opens_a_hub(client, hub_double, body, caplog):
    """Never a jump into a business that is no demo, nor a demo without its end."""
    hub_double.answer("POST", r"^/internal/demos$", 201, body)

    response = client.post(START)

    assert response["Location"] == f"{DOOR}?state=unavailable"
    assert "demo" not in client.session
    assert "demo.start.bad_answer" in caplog.text


@pytest.mark.django_db
def test_start_is_a_post(client, hub_double):
    assert client.get(START).status_code == 405
    assert hub_double.calls == []


@pytest.mark.django_db
def test_start_checks_the_csrf_token(hub_double):
    assert Client(enforce_csrf_checks=True).post(START).status_code == 403
    assert hub_double.calls == []
