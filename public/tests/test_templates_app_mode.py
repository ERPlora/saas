"""A public page opened from the installed app: its sign-in opens the legal texts, which then show in app mode
(``?surface=``: «Back» instead of the navbar, no footer, cookie notice nor analytics)."""

import re

import pytest
from django.conf import settings
from django.core.management import call_command
from django.urls import reverse

pytestmark = pytest.mark.urls("public.tests.urls")


# --- A public page opened from the installed app ------------------------------------------------------
#
# The app's sign-in (`/shell/`, hubs/frontend/pages/LaunchPage.vue) links the terms and the privacy policy with
# `?surface=<desktop|mobile|account>`; the page then opens like an app's in-app viewer (Shopify POS, Square POS:
# the text alone and a way back), with nothing of the web around it, and stays so for that session.

TERMS = "/legal/terms/"
PRIVACY = "/legal/privacy/"


def body_of(response) -> str:
    html = response.content.decode()
    return html[html.index("<body") :]


@pytest.mark.django_db
@pytest.mark.parametrize("surface", ["desktop", "mobile", "account"])
def test_a_page_opened_from_the_app_has_a_way_back_and_nothing_of_the_web(client, cookie_groups, surface):
    """Even with a tracker configured (`cookie_groups`), no notice and no measurement inside the app."""
    response = client.get(f"{TERMS}?surface={surface}")
    body = body_of(response)

    assert response.status_code == 200
    assert '<nav class="ep-navbar"' not in body
    assert '<footer class="ep-footer"' not in body
    assert 'id="cookie-consent-banner"' not in body
    assert 'href="/launch"' not in body
    assert ">Back<" in body
    assert f'data-surface="{surface}"' in response.content.decode()


@pytest.mark.django_db
def test_the_same_page_on_the_web_asks_for_cookies(client, cookie_groups):
    """The control of the test above: with a tracker configured, the web does show the notice."""
    assert 'id="cookie-consent-banner"' in body_of(client.get(TERMS))


@pytest.mark.django_db
@pytest.mark.parametrize("surface", ["desktop", "mobile", "account"])
def test_back_is_a_real_link_to_the_app_that_works_before_the_page_script(client, surface):
    """«Back» is an <a href> in the HTML, not an ion-button: an ion-button is no link until the page's script has
    defined it, so on a slow device «Back» pressed before that would do nothing. The link keeps the app's surface, as
    the app's own links to these texts do."""
    body = body_of(client.get(f"{TERMS}?surface={surface}"))

    back = re.search(r"<(\w[\w-]*)\b[^>]*\bdata-app-back\b[^>]*>", body)
    assert back is not None
    assert back.group(1) == "a"
    assert f'href="/shell/?surface={surface}"' in back.group(0)


@pytest.mark.django_db
def test_back_keeps_the_surface_the_session_remembers(client):
    """The app mode lasts in the session while the app moves between texts: so does «Back»'s surface."""
    client.get(f"{TERMS}?surface=mobile")

    back = re.search(r"<a\b[^>]*\bdata-app-back\b[^>]*>", body_of(client.get(PRIVACY)))

    assert back is not None
    assert 'href="/shell/?surface=mobile"' in back.group(0)


@pytest.mark.django_db
def test_the_app_mode_lasts_while_the_app_navigates_between_texts(client):
    client.get(f"{TERMS}?surface=mobile")

    assert '<nav class="ep-navbar"' not in body_of(client.get(PRIVACY))
    assert '<nav class="ep-navbar"' in body_of(client.get(f"{PRIVACY}?surface=web"))
    assert '<nav class="ep-navbar"' in body_of(client.get(TERMS))


@pytest.mark.django_db
@pytest.mark.parametrize("surface", ["", "evil", "<script>", "web"])
def test_any_other_surface_is_the_web(client, surface):
    body = body_of(client.get(f"{TERMS}?surface={surface}"))

    assert '<nav class="ep-navbar"' in body
    assert "data-app-back" not in body


@pytest.mark.django_db
def test_the_way_back_in_spanish(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    assert ">Volver<" in body_of(client.get(f"{TERMS}?surface=desktop"))



@pytest.mark.django_db
def test_inside_the_app_no_measurement_loads_even_with_every_cookie_accepted(client, settings):
    """The same visitor, with every group accepted, is measured on the web and never inside the app."""
    settings.GA_MEASUREMENT_ID = "G-TEST123"
    settings.CLARITY_PROJECT_ID = "xhn93kfr5b"
    call_command("init_cookie_groups")
    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    on_the_web = client.get(TERMS).content.decode()
    in_the_app = client.get(f"{TERMS}?surface=desktop").content.decode()

    assert "googletagmanager.com/gtag/js" in on_the_web and "clarity.ms" in on_the_web
    assert "googletagmanager.com/gtag/js" not in in_the_app
    assert "clarity.ms" not in in_the_app
