"""``/demo/``, ``/demo/start/`` and ``/demo/enter/``: the door to a demo hub (public/demo.py).

PLAN-SAAS §3.5, round 2026-10-17 (plan ``docs/plans/2026-10-17-demo-hubs-fase-1.md`` §1.6, §1.8): the SaaS
keeps no row of a demo. ``/demo/`` only reads the browser's session and never creates one; ``/demo/start/``
(POST, limited per address) asks the Hub for a demo of this browser (``POST /internal/demos``) and jumps to
its ``/auth/login``, which comes back to ``/demo/enter/`` with its ``state``; there the SaaS checks that this
browser owns that demo, asks for a one-time code (``POST /internal/demos/{slug}/codes``) and posts it to the
demo's ``/auth/callback`` (``accounts/hub_login_form.html``). Against the Hub double of ``hubs/tests``.
"""

import gettext
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse

from accounts.queries import hub_start_url
from hubs.tests.conftest import hub_double, offline_hub  # noqa: F401 - the Hub's /internal, or none
from public.sitemaps import StaticPagesSitemap

DOOR = "/demo/"
START = "/demo/start/"
ENTER = "/demo/enter/"
TRY = "/try/"
DEMO_SLUG = re.compile(r"demo-[0-9a-f]{8}")


@pytest.fixture(autouse=True)
def demo_settings(settings):
    """A clean limiter (it lives in the cache) and the local shape of a hub's address."""
    cache.clear()
    settings.DEMO_ENABLED = True
    settings.DEMO_SPAWN_RATELIMIT = "3/h"
    settings.HUB_CALLBACK_TEMPLATE = "http://{slug}.localhost:8000/auth/callback"
    yield
    cache.clear()


def page(response) -> str:
    assert response.status_code == 200
    return response.content.decode()


def state_of(html: str) -> str:
    (state,) = re.findall(r'data-testid="demo-state-([a-z]+)"', html)
    return state


def start(client: Client) -> str:
    """Start a demo in this browser; its slug."""
    response = client.post(START)
    assert response.status_code == 302, response.content
    (slug,) = DEMO_SLUG.findall(response["Location"])
    return slug


def demo_calls(double):
    return double.calls_to("POST", "/internal/demos")


def code_calls(double):
    return double.calls_to("POST", "/codes")


def enter(client: Client, slug: str, **params):
    return client.get(ENTER, {"hub": slug, "next": "/", "state": "the-hubs-state", **params})


# --- Settings and routes ----------------------------------------------------------------------------


def test_the_demo_is_on_by_default_and_limits_new_ones_per_address():
    from config import settings as project

    assert project.DEMO_ENABLED is True
    assert project.DEMO_SPAWN_RATELIMIT == "3/h"


def test_the_three_routes():
    assert reverse("public:demo") == DOOR
    assert reverse("public:demo_start") == START
    assert reverse("public:demo_enter") == ENTER


def test_the_door_is_in_the_sitemap_and_the_entry_is_not():
    listed = {name for name, _ in StaticPagesSitemap.pages}

    assert "public:demo" in listed
    assert not {"public:demo_start", "public:demo_enter", "public:demo_try"} & listed


# --- /try/: the same door at the address handed out (PUBLIC-F27) ------------------------------------------
# erplora.com/demo/ answered a permanent redirect to the sign-up for a month in the old stack, which browsers keep;
# /try/ was the door at an address that never redirected, and the link handed out (saas#1164).


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
    slug = start(client)

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
    slug = start(client)

    html = page(client.get(DOOR))

    assert state_of(html) == "ready"
    assert f'href="{hub_start_url(slug)}"' in html
    assert "Back to my demo" in html
    assert "It ends in 60 minutes." in html
    assert 'data-testid="demo-start"' not in html
    assert len(demo_calls(hub_double)) == 1


@pytest.mark.django_db
def test_the_door_of_a_browser_whose_demo_ended_says_so_once(client, hub_double):
    start(client)
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
    ],
)
def test_each_outcome_of_a_try_is_said_on_the_door(client, state, says):
    html = page(client.get(DOOR, {"state": state}))

    assert state_of(html) == state
    assert says in html


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["idle", "expired", "full", "throttled", "unavailable", "failed"])
def test_every_state_of_the_door_has_a_way_to_start_free(client, state):
    """PUBLIC-F35: from any state, «Start free» leads to the same entrance as every other one (/launch)."""
    html = page(client.get(DOOR if state == "idle" else f"{DOOR}?state={state}"))

    card = html.split(f'data-testid="demo-state-{state}"', 1)[1].split("</ion-card>", 1)[0]
    assert card.count('href="/launch"') == 1


@pytest.mark.django_db
def test_a_failed_entry_offers_the_live_demo_again(client, hub_double):
    slug = start(client)

    html = page(client.get(DOOR, {"state": "failed"}))

    assert state_of(html) == "failed"
    assert f'href="{hub_start_url(slug)}"' in html


@pytest.mark.django_db
def test_the_hubs_ended_page_clears_a_demo_the_browser_still_holds(client, hub_double):
    # The Hub's 410 page links here when a demo ended before its hour (``demo_expire``, «Expire now»): the session
    # still holds it as live, and only this address tells the door otherwise. The Hub is not asked.
    start(client)
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
    slug = start(client)
    page(client.get(DOOR, {"state": "expired"}))

    assert start(client) == slug
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


# --- /demo/start/ -----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_starting_asks_the_hub_for_a_demo_and_jumps_into_it(client, hub_double):
    response = client.post(START)

    (call,) = demo_calls(hub_double)
    (slug,) = hub_double.demos
    assert response.status_code == 302
    assert response["Location"] == f"http://{slug}.localhost:8000/auth/login?next=/"
    assert call.signed_v2
    assert set(call.body) == {"session_key", "vertical", "language"}
    assert (call.body["vertical"], call.body["language"]) == (None, "en")
    assert client.session["demo"]["slug"] == slug


@pytest.mark.django_db
def test_the_hub_gets_a_hash_of_the_browser_never_its_cookie(client, hub_double):
    start(client)

    (call,) = demo_calls(hub_double)
    cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
    assert re.fullmatch(r"[0-9a-f]{64}", call.body["session_key"])
    assert cookie not in json.dumps(call.body)


@pytest.mark.django_db
def test_another_browser_is_another_demo(client, hub_double):
    first = start(client)

    second = start(Client())

    assert first != second
    one, other = demo_calls(hub_double)
    assert one.body["session_key"] != other.body["session_key"]


@pytest.mark.django_db
def test_the_same_browser_gets_the_same_demo_and_spends_no_quota(client, hub_double, settings):
    """With room for two new demos an hour: the second press of the same browser is not one of them."""
    settings.DEMO_SPAWN_RATELIMIT = "2/h"

    first = start(client)
    again = start(client)
    other = start(Client())
    limited = Client().post(START)

    assert again == first
    assert other != first
    assert limited["Location"] == f"{DOOR}?state=throttled"


@pytest.mark.django_db
def test_a_fourth_new_demo_from_one_address_is_throttled(hub_double):
    for _ in range(3):
        start(Client())
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


# --- /demo/enter/ ----------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_entering_posts_a_one_time_code_to_the_demos_callback(client, hub_double):
    slug = start(client)
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
    slug = start(client)

    # In this order: ``?state=expired`` forgets the demo, and then there is nothing to enter.
    for response in (enter(client, slug), client.get(DOOR), client.get(DOOR, {"state": "expired"})):
        assert form_action(response) == ["'self'", settings.HUB_ORIGIN_PATTERN]
    assert form_action(client.get("/")) == ["'self'"]


@pytest.mark.django_db
def test_the_jump_into_a_demo_says_it_opens_the_demo(client, hub_double):
    slug = start(client)

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
    slug = start(client)

    html = page(enter(client, slug, next="//evil.example/"))

    assert 'name="next" value="/"' in html


@pytest.mark.django_db
def test_entering_without_the_hubs_state_starts_the_jump_at_the_hub(client, hub_double):
    slug = start(client)

    response = client.get(ENTER, {"hub": slug, "next": "/sales/"})

    assert (response.status_code, response["Location"]) == (302, hub_start_url(slug, "/sales/"))
    assert code_calls(hub_double) == []


@pytest.mark.django_db
def test_a_state_longer_than_the_hubs_is_refused(client, hub_double):
    slug = start(client)

    response = enter(client, slug, state="x" * 129)

    assert response["Location"] == f"{DOOR}?state=failed"
    assert code_calls(hub_double) == []


@pytest.mark.django_db
def test_entering_a_demo_this_browser_does_not_own_goes_back_to_the_door(client, hub_double):
    slug = start(client)
    stranger = Client()

    from_a_stranger = enter(stranger, slug)
    to_another_demo = enter(client, "demo-0123abcd")

    assert from_a_stranger["Location"] == DOOR
    assert to_another_demo["Location"] == DOOR
    assert code_calls(hub_double) == []


@pytest.mark.django_db
def test_a_demo_that_ended_at_the_hub_clears_the_browser_and_says_so(client, hub_double):
    slug = start(client)
    hub_double.demos[slug]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)

    response = enter(client, slug)

    assert response["Location"] == f"{DOOR}?state=expired"
    assert "demo" not in client.session
    assert state_of(page(client.get(response["Location"]))) == "expired"


@pytest.mark.django_db
def test_a_demo_the_hub_does_not_know_has_ended_too(client, hub_double):
    slug = start(client)
    hub_double.answer("POST", r"/codes$", 404, {"error": {"code": "not_found", "message": "?"}})

    assert enter(client, slug)["Location"] == f"{DOOR}?state=expired"
    assert "demo" not in client.session


@pytest.mark.django_db
def test_a_demo_the_hub_says_is_not_this_browsers_is_forgotten(client, hub_double):
    slug = start(client)
    hub_double.answer("POST", r"/codes$", 403, {"error": {"code": "base.demo_not_owner", "message": "?"}})

    assert enter(client, slug)["Location"] == DOOR
    assert "demo" not in client.session


@pytest.mark.django_db
def test_the_hub_away_while_entering_keeps_the_demo(client, hub_double, settings, caplog):
    slug = start(client)
    settings.HUB_INTERNAL_URL = "http://127.0.0.1:9"

    response = enter(client, slug)

    assert response["Location"] == f"{DOOR}?state=unavailable"
    assert client.session["demo"]["slug"] == slug
    assert "demo.enter.hub_unavailable" in caplog.text


@pytest.mark.django_db
def test_an_answer_without_a_code_is_not_posted(client, hub_double, caplog):
    slug = start(client)
    hub_double.answer("POST", r"/codes$", 201, {"expires_at": "2099-01-01T00:00:00+00:00"})

    assert enter(client, slug)["Location"] == f"{DOOR}?state=unavailable"
    assert "demo.enter.bad_answer" in caplog.text


@pytest.mark.django_db
def test_the_demo_survives_signing_in_to_the_saas(client, hub_double, django_user_model):
    """Signing in rotates the session key (``cycle_key``): the browser still owns its demo."""
    slug = start(client)
    client.force_login(django_user_model.objects.create_user(email="ana@example.com", password=None))

    html = page(enter(client, slug))

    assert 'name="code"' in html
    (demo_call,) = demo_calls(hub_double)
    (code_call,) = code_calls(hub_double)
    assert code_call.body["session_key"] == demo_call.body["session_key"]


@pytest.mark.django_db
def test_an_expired_demo_in_the_browser_is_not_entered(client, hub_double):
    slug = start(client)
    session = client.session
    session["demo"] = {**session["demo"], "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    session.save()

    response = enter(client, slug)

    assert response["Location"] == DOOR
    assert code_calls(hub_double) == []


# --- Spanish ---------------------------------------------------------------------------------------------


SPANISH_CATALOG = Path(settings.BASE_DIR) / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"


def spanish(client: Client) -> Client:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "english", "spanish_text"),
    [
        ({}, "Try the demo", "Prueba la demo"),
        ({}, "The demo hub is yours for 60 minutes", "El hub de demostración es tuyo durante 60 minutos"),
        ({"state": "expired"}, "This demo has ended. Start another one.", "Esta demo ha terminado. Empieza otra."),
        ({"state": "full"}, "The demo is full right now.", "La demo está llena ahora mismo."),
        ({"state": "throttled"}, "Too many demos from your network.", "Demasiadas demos desde tu red."),
        ({"state": "unavailable"}, "The demo is not available right now.", "La demo no está disponible ahora mismo."),
        ({"state": "failed"}, "We could not open your demo.", "No hemos podido abrir tu demo."),
    ],
)
def test_the_door_speaks_spanish(client, query, english, spanish_text):
    html = page(spanish(client).get(DOOR, query))

    assert spanish_text in html
    assert english not in html


@pytest.mark.django_db
def test_the_switched_off_door_speaks_spanish(client, settings):
    settings.DEMO_ENABLED = False

    html = page(spanish(client).get(DOOR))

    assert "La demo está cerrada por ahora." in html


@pytest.mark.django_db
def test_a_live_demo_is_told_in_spanish(client, hub_double):
    spanish(client)
    start(client)

    html = page(client.get(DOOR))

    assert "Volver a mi demo" in html
    assert "Termina en 60 minutos." in html


@pytest.mark.django_db
def test_the_jump_into_a_demo_speaks_spanish(client, hub_double):
    spanish(client)
    slug = start(client)

    html = page(enter(client, slug))

    assert "<p>Abriendo tu demo…</p>" in html
    assert "Opening your demo…" not in html


@pytest.mark.django_db
def test_the_visitors_language_goes_to_the_hub(client, hub_double):
    spanish(client)
    slug = start(client)

    page(enter(client, slug))

    (demo_call,) = demo_calls(hub_double)
    (code_call,) = code_calls(hub_double)
    assert (demo_call.body["language"], code_call.body["language"]) == ("es", "es")


def test_the_one_minute_left_is_singular_in_both_languages():
    with SPANISH_CATALOG.open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)

    assert catalog.ngettext("It ends in %(minutes)s minute.", "It ends in %(minutes)s minutes.", 1) == (
        "Termina en %(minutes)s minuto."
    )
    assert catalog.ngettext("It ends in %(minutes)s minute.", "It ends in %(minutes)s minutes.", 5) == (
        "Termina en %(minutes)s minutos."
    )


# --- reCAPTCHA (Ioan, 2026-10-22: every public form; live.recaptcha) ------------------------------------------------
# «Try the demo» is a form: its POST carries `recaptcha_token`, made by Google's enterprise.js for `demo_request`
# (frontend/recaptcha.ts), and Google is asked before the Hub. Refused, the door says so (`?state=unverified`) and the
# Hub is never called. Google is played by `FakeGoogleRecaptcha` (conftest.py).


@pytest.mark.django_db
def test_starting_a_demo_without_a_token_is_refused_before_the_hub(client, hub_double, recaptcha):
    response = client.post(START)

    assert (response.status_code, response["Location"]) == (302, f"{DOOR}?state=unverified")
    assert demo_calls(hub_double) == []
    assert recaptcha.asked == []


@pytest.mark.django_db
@pytest.mark.parametrize("token", ["bot:demo_request", "human:contact", "forged"], ids=["bot", "other-form", "forged"])
def test_a_bad_token_never_reaches_the_hub(client, hub_double, recaptcha, token):
    response = client.post(START, {"recaptcha_token": token})

    assert response["Location"] == f"{DOOR}?state=unverified"
    assert demo_calls(hub_double) == []


@pytest.mark.django_db
def test_a_persons_token_starts_the_demo(client, hub_double, recaptcha):
    response = client.post(START, {"recaptcha_token": "human:demo_request"})

    (slug,) = hub_double.demos
    assert response["Location"] == f"http://{slug}.localhost:8000/auth/login?next=/"
    assert recaptcha.asked == [("human:demo_request", "demo_request")]


@pytest.mark.django_db
def test_google_down_does_not_start_a_demo(client, hub_double, recaptcha):
    recaptcha.down = True

    response = client.post(START, {"recaptcha_token": "human:demo_request"})

    assert response["Location"] == f"{DOOR}?state=unverified"
    assert demo_calls(hub_double) == []


@pytest.mark.django_db
def test_a_throttled_address_never_asks_google(hub_double, recaptcha):
    browser = Client()
    for n in range(3):
        browser.cookies.clear()
        browser.post(START, {"recaptcha_token": "human:demo_request"})
    asked = len(recaptcha.asked)
    browser.cookies.clear()

    response = browser.post(START, {"recaptcha_token": "human:demo_request"})

    assert response["Location"] == f"{DOOR}?state=throttled"
    assert len(recaptcha.asked) == asked


@pytest.mark.django_db
def test_the_door_says_the_check_failed(client):
    html = page(client.get(DOOR, {"state": "unverified"}))

    assert state_of(html) == "unverified"
    assert "We could not check that you are a person. Try again." in html
    assert 'data-testid="demo-start"' in html


@pytest.mark.django_db
def test_the_failed_check_speaks_spanish(client):
    html = page(spanish(client).get(DOOR, {"state": "unverified"}))

    assert "No hemos podido comprobar que eres una persona. Vuelve a intentarlo." in html


@pytest.mark.django_db
def test_the_door_with_recaptcha_asks_google_for_its_token_and_says_so(client, recaptcha):
    html = page(client.get(DOOR))

    form = html.split('action="/demo/start/"', 1)[1].split("</form>", 1)[0]
    assert 'data-recaptcha-action="demo_request"' in html
    assert 'data-recaptcha-site-key="test-site-key"' in html
    assert 'name="recaptcha_token"' in form
    assert "This site is protected by reCAPTCHA" in html
    assert 'href="https://policies.google.com/privacy"' in html
    assert 'href="https://policies.google.com/terms"' in html


@pytest.mark.django_db
def test_the_door_without_recaptcha_loads_nothing_of_google(client):
    html = page(client.get(DOOR))

    assert "data-recaptcha" not in html
    assert "protected by reCAPTCHA" not in html


@pytest.mark.django_db
def test_the_door_without_recaptcha_names_nothing_of_google_in_its_own_policy(client, hub_double):
    policy = client.get(DOOR)["Content-Security-Policy"]

    assert "recaptcha" not in policy
    assert "gstatic.com" not in policy


@pytest.mark.django_db
def test_the_door_keeps_googles_sources_in_its_own_policy(client, hub_double, recaptcha):
    policy = client.get(DOOR)["Content-Security-Policy"]

    assert "https://www.google.com/recaptcha/" in policy
    assert "https://recaptcha.google.com/recaptcha/" in policy
