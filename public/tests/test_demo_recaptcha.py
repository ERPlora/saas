"""reCAPTCHA on «Try the demo» (public/demo.py)."""


import pytest
from django.test import Client

from public.tests.demo_pages import DOOR, START, demo_calls, page, spanish, state_of

pytestmark = pytest.mark.usefixtures("demo_settings")


# --- reCAPTCHA (live.recaptcha) --------------------------------------------------------------------------------------
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

    assert len(hub_double.demos) == 1
    assert response["Location"] == DOOR  # the Hub prepares it; the door waits for it
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
