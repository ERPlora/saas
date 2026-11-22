"""``/demo/status/``: how the browser's demo is going, for the door's page (public/demo.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client

from public.tests.demo_pages import DOOR, STATUS, page, start, state_of, status

pytestmark = pytest.mark.usefixtures("demo_settings")


# --- /demo/status/: how the browser's demo is going, for the door's page --------------------------------------


@pytest.mark.django_db
def test_the_status_of_a_demo_the_hub_finished_jumps_into_it_and_is_remembered(client, hub_double):
    slug = start(client, hub_double, ready=False)
    hub_double.demos[slug]["status"] = "ready"

    first = status(client)
    hub_double.calls.clear()
    second = status(client)

    assert first == second == {"state": "ready", "url": f"http://{slug}.localhost:8000/auth/login?next=/"}
    assert client.session["demo"]["ready"] is True
    assert hub_double.calls == []  # once ready, the Hub is not asked again


@pytest.mark.django_db
def test_the_status_asks_the_hub_about_the_browsers_demo_signed(client, hub_double):
    slug = start(client, hub_double, ready=False)

    status(client)

    (call,) = [c for c in hub_double.calls if c.method == "GET"]
    assert call.path == f"/internal/hubs/{hub_double.demos[slug]['id']}"
    assert call.signed_v2


@pytest.mark.django_db
@pytest.mark.parametrize("step", ["requested", "creating", "migrating", "seeding"])
def test_the_status_of_a_demo_still_being_prepared_says_so(client, hub_double, step):
    slug = start(client, hub_double, ready=False)
    hub_double.demos[slug]["status"] = step

    assert status(client) == {"state": "preparing"}
    assert client.session["demo"]["ready"] is False


@pytest.mark.django_db
def test_the_status_during_maintenance_says_so_and_recovers_without_losing_the_demo(client, hub_double):
    """A freeze is not a failed preparation; the next poll recovers the real state."""
    slug = start(client, hub_double, ready=False)
    hub_double.demos[slug]["maintenance"] = {
        "frozen": True,
        "reason": "Aurora upgrade",
        "since": "2026-11-09T20:00:00+00:00",
    }

    assert status(client) == {"state": "maintenance"}
    assert client.session["demo"]["slug"] == slug

    hub_double.demos[slug]["maintenance"] = None
    assert status(client) == {"state": "preparing"}


@pytest.mark.django_db
def test_the_status_reads_the_hub_body_as_the_hub_writes_it_and_tolerates_an_older_hub(client, hub_double, monkeypatch):
    """Contract with the Hub's ``base.schemas.HubGetOut``: the whole body of the signed poll, and that of an older
    Hub without ``maintenance``, which is no pause."""
    from hubs import hub_client

    slug = start(client, hub_double, ready=False)
    hub_body = {
        "id": client.session["demo"]["id"],
        "slug": slug,
        "status": "requested",
        "is_demo": True,
        "expires_at": "2026-11-09T21:00:00Z",
        "ready_at": None,
        "state_version": 0,
        "maintenance": {"frozen": True, "reason": "Aurora upgrade", "since": "2026-11-09T20:00:00.123456Z"},
    }
    monkeypatch.setattr(hub_client, "get_hub", lambda hub_id: hub_client.HubAnswer(200, hub_body))
    assert status(client) == {"state": "maintenance"}

    older_hub = {key: value for key, value in hub_body.items() if key != "maintenance"}
    monkeypatch.setattr(hub_client, "get_hub", lambda hub_id: hub_client.HubAnswer(200, older_hub))
    assert status(client) == {"state": "preparing"}


@pytest.mark.django_db
def test_a_ready_demo_enters_even_when_another_freeze_is_active(client, hub_double):
    """A platform-wide pause never holds back a demo whose database is already ready."""
    slug = start(client, hub_double, ready=False)
    hub_double.demos[slug]["status"] = "ready"
    hub_double.demos[slug]["maintenance"] = {
        "frozen": True,
        "reason": "Aurora upgrade",
        "since": "2026-11-09T20:00:00+00:00",
    }

    assert status(client) == {"state": "ready", "url": f"http://{slug}.localhost:8000/auth/login?next=/"}
    assert client.session["demo"]["ready"] is True


@pytest.mark.django_db
def test_the_status_of_a_demo_the_hub_could_not_prepare_is_not_ready(client, hub_double, caplog):
    slug = start(client, hub_double, ready=False)
    hub_double.demos[slug]["status"] = "failed"

    assert status(client) == {"state": "not_ready", "url": f"{DOOR}?state=not_ready"}
    assert client.session["demo"]["slug"] == slug  # «Try again» waits for the same demo, which the Hub retries
    assert "demo.status.not_prepared" in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize("ended", ["expired", "cancelled", "archiving", "dropping", "purged"])
def test_the_status_of_a_demo_that_ended_forgets_it(client, hub_double, ended):
    """``archiving`` and ``dropping`` are the Hub dropping it: ended as ``expired`` is, never «not available»."""
    slug = start(client, hub_double, ready=False)
    hub_double.answer("GET", rf"^/internal/hubs/{hub_double.demos[slug]['id']}$", 200, {"status": ended})

    assert status(client) == {"state": "expired", "url": f"{DOOR}?state=expired"}
    assert "demo" not in client.session
    assert state_of(page(client.get(DOOR, {"state": "expired"}))) == "expired"


@pytest.mark.django_db
@pytest.mark.parametrize("refusal", [404, 410])
def test_the_status_of_a_demo_the_hub_no_longer_has_forgets_it(client, hub_double, refusal):
    start(client, hub_double, ready=False)
    hub_double.answer("GET", r"^/internal/hubs/[0-9a-f-]+$", refusal, {"error": {"code": "base.hub_gone"}})

    assert status(client) == {"state": "expired", "url": f"{DOOR}?state=expired"}
    assert "demo" not in client.session


@pytest.mark.django_db
def test_the_status_with_the_hub_away_keeps_waiting(client, hub_double, caplog):
    """A Hub away a moment is no answer: the page keeps asking until its 30 seconds are up."""
    start(client, hub_double, ready=False)
    hub_double.answer("GET", r"^/internal/hubs/[0-9a-f-]+$", 503, {})

    assert status(client) == {"state": "preparing"}
    assert client.session["demo"]["ready"] is False
    assert "demo.status.hub_unavailable" in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("answer_status", "body"),
    [(403, {"error": {"code": "forbidden"}}), (200, {"status": "dropped"}), (200, {}), (200, ["ready"])],
)
def test_the_status_with_an_answer_off_the_contract_is_unavailable(client, hub_double, answer_status, body, caplog):
    start(client, hub_double, ready=False)
    hub_double.answer("GET", r"^/internal/hubs/[0-9a-f-]+$", answer_status, body)

    assert status(client) == {"state": "unavailable", "url": f"{DOOR}?state=unavailable"}
    assert "demo.status.bad_answer" in caplog.text


@pytest.mark.django_db
def test_the_status_without_a_demo_sends_to_the_door(client, hub_double):
    assert status(client) == {"state": "idle", "url": DOOR}
    assert hub_double.calls == []


@pytest.mark.django_db
def test_the_status_of_a_demo_whose_hour_passed_sends_to_the_door(client, hub_double):
    start(client, hub_double, ready=False)
    session = client.session
    session["demo"] = {**session["demo"], "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    session.save()
    hub_double.calls.clear()

    assert status(client) == {"state": "idle", "url": DOOR}  # the door says it ended, once
    assert hub_double.calls == []


@pytest.mark.django_db
def test_the_status_with_the_demo_switched_off_sends_to_the_door(client, hub_double, settings):
    start(client, hub_double, ready=False)
    settings.DEMO_ENABLED = False
    hub_double.calls.clear()

    assert status(client) == {"state": "off", "url": DOOR}
    assert hub_double.calls == []


@pytest.mark.django_db
def test_the_status_is_never_stored_nor_indexed(client, hub_double):
    response = client.get(STATUS, HTTP_ACCEPT="application/json")

    assert "no-store" in response["Cache-Control"]
    assert response["X-Robots-Tag"] == "noindex, nofollow"


@pytest.mark.django_db
def test_the_status_is_limited_per_browser_and_past_it_asks_the_hub_nothing(client, hub_double, monkeypatch, caplog):
    """The page asks once a second; a browser asking faster than ``STATUS_RATE`` waits without
    reaching the Hub."""
    from public import demo

    monkeypatch.setattr(demo, "STATUS_RATE", "2/m")
    start(client, hub_double, ready=False)

    answers = [status(client) for _ in range(3)]

    assert answers == [{"state": "preparing"}] * 3
    assert len([c for c in hub_double.calls if c.method == "GET"]) == 2
    assert "demo.status.throttled" in caplog.text


@pytest.mark.django_db
def test_another_browser_has_its_own_limit(client, hub_double, monkeypatch):
    from public import demo

    monkeypatch.setattr(demo, "STATUS_RATE", "1/m")
    start(client, hub_double, ready=False)
    other = Client()
    start(other, hub_double, ready=False)

    status(client)
    status(other)

    assert len([c for c in hub_double.calls if c.method == "GET"]) == 2


@pytest.mark.django_db
def test_the_status_is_only_read(client, hub_double):
    assert client.post(STATUS).status_code == 405


@pytest.mark.django_db
def test_a_session_of_the_older_hub_without_the_ready_mark_is_a_ready_demo(client, hub_double):
    """A browser that started its demo before this release holds no ``id`` nor ``ready``: that demo was ready."""
    session = client.session
    session["demo"] = {"slug": "demo-0123abcd", "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat()}
    session.save()

    assert state_of(page(client.get(DOOR))) == "ready"
    assert status(client) == {"state": "ready", "url": "http://demo-0123abcd.localhost:8000/auth/login?next=/"}


@pytest.mark.django_db
def test_not_ready_tries_the_same_demo_again(client, hub_double):
    start(client, hub_double, ready=False)

    html = page(client.get(DOOR, {"state": "not_ready"}))

    assert state_of(html) == "not_ready"
    assert 'data-testid="demo-retry"' in html
    assert f'href="{DOOR}"' in html
    assert 'data-testid="demo-start"' not in html


@pytest.mark.django_db
def test_not_ready_without_a_demo_offers_to_start_one(client):
    html = page(client.get(DOOR, {"state": "not_ready"}))

    assert 'data-testid="demo-start"' in html
    assert 'data-testid="demo-retry"' not in html


@pytest.mark.django_db
def test_the_waiting_door_names_no_database(client, hub_double):
    start(client, hub_double, ready=False)

    waiting = page(client.get(DOOR)) + page(client.get(DOOR, {"state": "not_ready"}))

    main = [part.split("</main>", 1)[0] for part in waiting.lower().split("<main>")[1:]]
    assert len(main) == 2
    assert not [part for part in main if "database" in part or "base de datos" in part]
