"""``/demo/``, ``/demo/start/`` and ``/demo/enter/``: the door to a demo hub (public/demo.py).

The SaaS keeps no row of a demo. ``/demo/`` only reads the browser's session and never creates one; ``/demo/start/``
(POST, limited per address) asks the Hub for a demo of this browser (``POST /internal/demos``) and jumps to its
``/auth/login``, which comes back to ``/demo/enter/`` with its ``state``; there the SaaS checks that this browser
owns that demo, asks for a one-time code (``POST /internal/demos/{slug}/codes``) and posts it to the demo's
``/auth/callback`` (``accounts/hub_login_form.html``). Against the Hub double of ``hubs/tests``.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse

from accounts.queries.hub_links import hub_start_url
from public.sitemaps import StaticPagesSitemap
from public.tests.demo_pages import DOOR, ENTER, START, STATUS, TRY, demo_calls, enter, page, start, state_of

pytestmark = pytest.mark.usefixtures("demo_settings")


# --- Settings and routes ----------------------------------------------------------------------------


def test_the_demo_is_on_by_default_and_limits_new_ones_per_address():
    from config import settings as project

    assert project.DEMO_ENABLED is True
    assert project.DEMO_SPAWN_RATELIMIT == "3/h"


def test_the_routes():
    assert reverse("public:demo") == DOOR
    assert reverse("public:demo_start") == START
    assert reverse("public:demo_enter") == ENTER
    assert reverse("public:demo_status") == STATUS


def test_the_door_is_in_the_sitemap_and_the_entry_is_not():
    listed = {name for name, _ in StaticPagesSitemap.pages}

    assert "public:demo" in listed
    assert not {"public:demo_start", "public:demo_enter", "public:demo_status", "public:demo_try"} & listed


# --- /try/: the same door at the address handed out -------------------------------------------------------
# Browsers keep a permanent redirect, and erplora.com/demo/ answered one to the sign-up in the old stack: the link
# handed out is /try/, an address that never redirected.


def test_the_door_has_a_second_address_to_hand_out():
    assert reverse("public:demo_try") == TRY


@pytest.mark.django_db
def test_the_second_address_is_the_same_door_and_names_the_first_as_canonical(client, hub_double):
    html = page(client.get(TRY))

    assert state_of(html) == "idle"
    assert 'data-testid="demo-start"' in html
    assert '<link rel="canonical" href="https://testserver/demo/">' in html
    assert hub_double.calls == []


@pytest.mark.django_db
def test_the_second_address_takes_a_live_demo_back_too(client, hub_double):
    slug = start(client, hub_double)

    html = page(client.get(TRY))

    assert state_of(html) == "ready"
    assert f'href="{hub_start_url(slug)}"' in html


@pytest.mark.django_db
def test_the_second_address_never_redirects(client):
    response = client.get(TRY)

    assert response.status_code == 200


# --- /demo/: never creates ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_door_offers_a_demo_and_never_starts_one(client, hub_double):
    html = page(client.get(DOOR))

    assert state_of(html) == "idle"
    assert 'data-testid="demo-start"' in html
    assert re.search(rf'<form[^>]+method="post"[^>]+action="{START}"', html)
    assert "csrfmiddlewaretoken" in html
    assert "The demo hub is yours for 60 minutes; no account, no card." in html
    assert hub_double.calls == []


@pytest.mark.django_db
def test_the_door_may_be_indexed(client):
    html = page(client.get(DOOR))

    assert 'name="robots"' not in html
    assert "noindex" not in client.get(DOOR).get("X-Robots-Tag", "")


@pytest.mark.django_db
def test_the_door_of_a_browser_with_a_live_demo_takes_it_back(client, hub_double):
    slug = start(client, hub_double)

    html = page(client.get(DOOR))

    assert state_of(html) == "ready"
    assert f'href="{hub_start_url(slug)}"' in html
    # The shape public-demo-hub.spec.ts presses (a.ep-button): that spec needs a real Hub and no run has one.
    assert re.search(rf'<a class="ep-button[^"]*" href="{re.escape(hub_start_url(slug))}">\s*Back to my demo', html)
    assert "It ends in 60 minutes." in html
    assert 'data-testid="demo-start"' not in html
    assert len(demo_calls(hub_double)) == 1


@pytest.mark.django_db
def test_the_door_of_a_browser_whose_demo_ended_says_so_once(client, hub_double):
    start(client, hub_double)
    session = client.session
    session["demo"] = {**session["demo"], "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    session.save()

    html = page(client.get(DOOR))

    assert state_of(html) == "expired"
    assert "This demo has ended. Start another one." in html
    assert 'data-testid="demo-start"' in html
    assert "demo" not in client.session
    assert state_of(page(client.get(DOOR))) == "idle"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("state", "says"),
    [
        ("expired", "This demo has ended. Start another one."),
        ("full", "The demo is full right now. Try again in a few minutes."),
        ("throttled", "Too many demos from your network. Please try again in a little while."),
        ("unavailable", "The demo is not available right now."),
        ("failed", "We could not open your demo. Try again."),
        ("not_ready", "Your demo is not ready yet. Try again in a moment."),
    ],
)
def test_each_outcome_of_a_try_is_said_on_the_door(client, state, says):
    html = page(client.get(DOOR, {"state": state}))

    assert state_of(html) == state
    assert says in html


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["idle", "expired", "full", "throttled", "unavailable", "failed", "not_ready"])
def test_every_state_of_the_door_has_a_way_to_start_free(client, state):
    """From any state, «Start free» leads to the same entrance as every other one (/launch)."""
    html = page(client.get(DOOR if state == "idle" else f"{DOOR}?state={state}"))

    card = html.split(f'data-testid="demo-state-{state}"', 1)[1].split("</ion-card>", 1)[0]
    assert card.count('href="/launch"') == 1


@pytest.mark.django_db
def test_a_failed_entry_offers_the_live_demo_again(client, hub_double):
    slug = start(client, hub_double)

    html = page(client.get(DOOR, {"state": "failed"}))

    assert state_of(html) == "failed"
    assert f'href="{hub_start_url(slug)}"' in html


@pytest.mark.django_db
def test_the_hubs_ended_page_clears_a_demo_the_browser_still_holds(client, hub_double):
    # The Hub's 410 page links here when a demo ended before its hour (``demo_expire``, «Expire now»): the session
    # still holds it as live, and only this address tells the door otherwise. The Hub is not asked.
    start(client, hub_double)
    calls = len(hub_double.calls)

    html = page(client.get(DOOR, {"state": "expired"}))

    assert state_of(html) == "expired"
    assert "This demo has ended. Start another one." in html
    assert 'data-testid="demo-start"' in html
    assert "Back to my demo" not in html
    assert "demo" not in client.session
    assert len(hub_double.calls) == calls
    assert state_of(page(client.get(DOOR))) == "idle"


@pytest.mark.django_db
def test_a_demo_said_ended_by_mistake_is_given_back_by_the_hub(client, hub_double):
    # ``?state=expired`` is only a link: the browser keeps the token that names it to the Hub, so «Try the demo»
    # gets its demo back if it was still on, and spends no new one.
    slug = start(client, hub_double)
    page(client.get(DOOR, {"state": "expired"}))

    assert start(client, hub_double) == slug
    first, again = demo_calls(hub_double)
    assert first.body["session_key"] == again.body["session_key"]


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["ready", "off", "<script>alert(1)</script>", ""])
def test_any_other_state_in_the_address_is_ignored(client, state):
    html = page(client.get(DOOR, {"state": state}))

    assert state_of(html) == "idle"
    assert "<script>alert(1)</script>" not in html


@pytest.mark.django_db
def test_with_the_demo_switched_off_nothing_reaches_the_hub(client, hub_double, settings):
    settings.DEMO_ENABLED = False

    html = page(client.get(DOOR))
    started = client.post(START)
    entered = enter(client, "demo-0123abcd")

    assert state_of(html) == "off"
    assert 'data-testid="demo-start"' not in html
    assert 'href="/launch"' in html
    assert (started.status_code, started["Location"]) == (302, DOOR)
    assert (entered.status_code, entered["Location"]) == (302, DOOR)
    assert hub_double.calls == []
