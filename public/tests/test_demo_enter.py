"""``/demo/enter/``: the jump into a demo with a one-time code (public/demo.py)."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.test import Client

from accounts.queries.hub_links import hub_start_url
from public.tests.demo_pages import DOOR, ENTER, code_calls, demo_calls, enter, page, start, state_of

pytestmark = pytest.mark.usefixtures("demo_settings")


# --- /demo/enter/ ----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_entering_posts_a_one_time_code_to_the_demos_callback(client, hub_double):
    slug = start(client, hub_double)
    hub_double.answer("POST", r"/codes$", 201, {"code": "one-time-code", "expires_at": "2099-01-01T00:00:00+00:00"})

    response = enter(client, slug, next="/sales/")
    html = page(response)

    (code_call,) = code_calls(hub_double)
    (demo_call,) = demo_calls(hub_double)
    assert code_call.path == f"/internal/demos/{slug}/codes"
    assert code_call.body == {"session_key": demo_call.body["session_key"], "language": "en"}
    assert code_call.signed_v2
    assert f'action="http://{slug}.localhost:8000/auth/callback"' in html
    assert 'name="code" value="one-time-code"' in html
    assert 'name="next" value="/sales/"' in html
    assert 'name="state" value="the-hubs-state"' in html
    assert re.search(r'<script nonce="[^"]+">', html)
    assert '<meta name="robots" content="noindex, nofollow">' in html
    assert response["Referrer-Policy"] == "no-referrer"
    assert "no-store" in response["Cache-Control"]


def form_action(response) -> list[str]:
    return re.search(r"form-action ([^;]+)", response["Content-Security-Policy"]).group(1).split()


@pytest.mark.django_db
def test_the_door_and_the_entry_may_send_their_form_to_a_demos_host(client, hub_double):
    """The public CSP allows forms to this origin only, and Chrome holds the redirect a form answers to it too: the
    door's «Try the demo» posts here and is answered with a 302 to the demo's host, the entry posts to that host."""
    slug = start(client, hub_double)

    # In this order: ``?state=expired`` forgets the demo, and then there is nothing to enter.
    for response in (enter(client, slug), client.get(DOOR), client.get(DOOR, {"state": "expired"})):
        assert form_action(response) == ["'self'", settings.HUB_ORIGIN_PATTERN]
    assert form_action(client.get("/")) == ["'self'"]


@pytest.mark.django_db
def test_the_jump_into_a_demo_says_it_opens_the_demo(client, hub_double):
    slug = start(client, hub_double)

    html = page(enter(client, slug))

    assert "<title>Opening your demo… · ERPlora Cloud</title>" in html
    assert "<p>Opening your demo…</p>" in html
    assert "Opening your business…" not in html


def test_the_jump_into_a_business_still_says_it_opens_the_business():
    html = render_to_string(
        "accounts/hub_login_form.html", {"callback_url": "http://a.localhost:8000/auth/callback", "code": "c"}
    )

    assert "<p>Opening your business…</p>" in html
    assert "Opening your demo…" not in html


@pytest.mark.django_db
def test_a_next_off_the_hub_lands_on_its_home(client, hub_double):
    slug = start(client, hub_double)

    html = page(enter(client, slug, next="//evil.example/"))

    assert 'name="next" value="/"' in html


@pytest.mark.django_db
def test_a_demo_being_prepared_is_never_entered(client, hub_double):
    """The code is asked only for a demo the Hub has ready: until then the browser goes back to the door, which waits."""
    slug = start(client, hub_double, ready=False)

    response = enter(client, slug)

    assert response.status_code == 302
    assert response["Location"] == DOOR
    assert code_calls(hub_double) == []


@pytest.mark.django_db
def test_entering_without_the_hubs_state_starts_the_jump_at_the_hub(client, hub_double):
    slug = start(client, hub_double)

    response = client.get(ENTER, {"hub": slug, "next": "/sales/"})

    assert (response.status_code, response["Location"]) == (302, hub_start_url(slug, "/sales/"))
    assert code_calls(hub_double) == []


@pytest.mark.django_db
def test_a_state_longer_than_the_hubs_is_refused(client, hub_double):
    slug = start(client, hub_double)

    response = enter(client, slug, state="x" * 129)

    assert response["Location"] == f"{DOOR}?state=failed"
    assert code_calls(hub_double) == []


@pytest.mark.django_db
def test_entering_a_demo_this_browser_does_not_own_goes_back_to_the_door(client, hub_double):
    slug = start(client, hub_double)
    stranger = Client()

    from_a_stranger = enter(stranger, slug)
    to_another_demo = enter(client, "demo-0123abcd")

    assert from_a_stranger["Location"] == DOOR
    assert to_another_demo["Location"] == DOOR
    assert code_calls(hub_double) == []


@pytest.mark.django_db
def test_a_demo_that_ended_at_the_hub_clears_the_browser_and_says_so(client, hub_double):
    slug = start(client, hub_double)
    hub_double.demos[slug]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)

    response = enter(client, slug)

    assert response["Location"] == f"{DOOR}?state=expired"
    assert "demo" not in client.session
    assert state_of(page(client.get(response["Location"]))) == "expired"


@pytest.mark.django_db
def test_a_demo_the_hub_does_not_know_has_ended_too(client, hub_double):
    slug = start(client, hub_double)
    hub_double.answer("POST", r"/codes$", 404, {"error": {"code": "not_found", "message": "?"}})

    assert enter(client, slug)["Location"] == f"{DOOR}?state=expired"
    assert "demo" not in client.session


@pytest.mark.django_db
def test_a_demo_the_hub_says_is_not_this_browsers_is_forgotten(client, hub_double):
    slug = start(client, hub_double)
    hub_double.answer("POST", r"/codes$", 403, {"error": {"code": "base.demo_not_owner", "message": "?"}})

    assert enter(client, slug)["Location"] == DOOR
    assert "demo" not in client.session


@pytest.mark.django_db
def test_the_hub_away_while_entering_keeps_the_demo(client, hub_double, settings, caplog):
    slug = start(client, hub_double)
    settings.HUB_INTERNAL_URL = "http://127.0.0.1:9"

    response = enter(client, slug)

    assert response["Location"] == f"{DOOR}?state=unavailable"
    assert client.session["demo"]["slug"] == slug
    assert "demo.enter.hub_unavailable" in caplog.text


@pytest.mark.django_db
def test_an_answer_without_a_code_is_not_posted(client, hub_double, caplog):
    slug = start(client, hub_double)
    hub_double.answer("POST", r"/codes$", 201, {"expires_at": "2099-01-01T00:00:00+00:00"})

    assert enter(client, slug)["Location"] == f"{DOOR}?state=unavailable"
    assert "demo.enter.bad_answer" in caplog.text


@pytest.mark.django_db
def test_the_demo_survives_signing_in_to_the_saas(client, hub_double, django_user_model):
    """Signing in rotates the session key (``cycle_key``): the browser still owns its demo."""
    slug = start(client, hub_double)
    client.force_login(django_user_model.objects.create_user(email="ana@example.com", password=None))

    html = page(enter(client, slug))

    assert 'name="code"' in html
    (demo_call,) = demo_calls(hub_double)
    (code_call,) = code_calls(hub_double)
    assert code_call.body["session_key"] == demo_call.body["session_key"]


@pytest.mark.django_db
def test_an_expired_demo_in_the_browser_is_not_entered(client, hub_double):
    slug = start(client, hub_double)
    session = client.session
    session["demo"] = {**session["demo"], "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    session.save()

    response = enter(client, slug)

    assert response["Location"] == DOOR
    assert code_calls(hub_double) == []
