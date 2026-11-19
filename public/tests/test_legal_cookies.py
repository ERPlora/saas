"""The cookie policy, ``/legal/cookies/``: it names the cookies this site really sets (the language cookie is
``_lang``) and says when the cookie banner shows.
"""

import re

import pytest
from django.conf import settings
from django.urls import reverse
from live.spa import PALETTE_COOKIE

from public.tests.legal_pages import spanish


# --- Cookie policy -----------------------------------------------------------------------------


@pytest.mark.django_db
def test_cookies_returns_200(client):
    assert client.get("/legal/cookies/").status_code == 200


@pytest.mark.django_db
def test_cookies_contains_spanish_marker(client):
    assert "Política de cookies" in spanish(client, "/legal/cookies/")


@pytest.mark.django_db
def test_the_cookie_policy_names_the_cookies_this_site_really_sets(client):
    """The language cookie is ``_lang``, never ``django_language``."""
    html = client.get("/legal/cookies/").content.decode()

    for name in (
        settings.SESSION_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
        settings.COOKIE_CONSENT_NAME,
        settings.LANGUAGE_COOKIE_NAME,
        # The panel's palette (packages/ui shell/theme.ts), set to every visitor of the panel's pages.
        PALETTE_COOKIE,
    ):
        assert f"<strong>{name}</strong>" in html, name
    assert "django_language" not in html


@pytest.mark.django_db
def test_the_cookie_policy_links_the_privacy_policy_and_the_aepd_guide(client):
    html = client.get("/legal/cookies/").content.decode()

    assert f'href="{reverse("public:privacy")}"' in html
    assert "https://www.aepd.es" in html


# --- The banner the policy describes is the one the site shows ---------------------------------

COOKIE_POLICY = "/legal/cookies/"
TRACKERS = {"GA_MEASUREMENT_ID": "G-TEST123", "CLARITY_PROJECT_ID": "xhn93kfr5b"}
TRACKER_COOKIES = {"GA_MEASUREMENT_ID": "_ga, _ga_*", "CLARITY_PROJECT_ID": "_clck, _clsk"}


def policy_section(html: str, number: int) -> str:
    """Section ``number`` of the cookie policy as plain text, from its heading to the next one, so a
    sentence elsewhere on the page (the hero, the footer) cannot make a test pass."""
    parts = re.split(r"<h2[^>]*>", html)
    section = next(part for part in parts if re.match(rf"\s*{number}\.", part))
    return " ".join(re.sub(r"<[^>]+>", " ", section.split("</h2>", 1)[1]).split())


@pytest.fixture
def no_tracker(settings):
    for name in TRACKERS:
        setattr(settings, name, "")


@pytest.mark.django_db
def test_without_a_tracker_the_cookie_policy_promises_no_banner(client, no_tracker):
    """With no tracker configured (production today) no page shows the banner: the policy says so, instead of
    promising a banner on the first visit."""
    html = client.get(COOKIE_POLICY).content.decode()
    kinds, managing = policy_section(html, 2), policy_section(html, 3)

    assert "currently sets only technical cookies, which are exempt from consent" in managing
    assert "so we show no cookie banner: there is nothing to accept or reject" in managing
    assert "The first time you visit" not in managing
    assert "We currently do NOT use cookies of this type: erplora.com does not measure visits." in kinds
    assert not [cookies for cookies in TRACKER_COOKIES.values() if cookies in kinds]


@pytest.mark.django_db
@pytest.mark.parametrize("tracker", sorted(TRACKERS))
def test_with_a_tracker_the_cookie_policy_says_the_banner_asks_until_a_choice(
    client, settings, no_tracker, tracker
):
    """One tracker is enough to show the banner (public/partials/cookie_banner.html), and the policy then
    lists the cookies of that tracker only."""
    setattr(settings, tracker, TRACKERS[tracker])

    html = client.get(COOKIE_POLICY).content.decode()
    kinds, managing = policy_section(html, 2), policy_section(html, 3)

    assert "Until you choose, every public page of erplora.com shows a banner" in managing
    assert "none of them is set before you accept" in managing
    assert "we show no cookie banner" not in managing
    assert TRACKER_COOKIES[tracker] in kinds
    assert [c for name, c in TRACKER_COOKIES.items() if name != tracker and c in kinds] == []
    assert "erplora.com does not measure visits" not in kinds


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tracker", "sentence"),
    [
        (None, "por eso no mostramos ningún aviso de cookies: no hay nada que aceptar ni rechazar"),
        ("CLARITY_PROJECT_ID", "Hasta que elijas, cada página pública de erplora.com muestra un aviso"),
    ],
)
def test_the_cookie_policy_says_when_the_banner_shows_in_spanish(
    client, settings, no_tracker, tracker, sentence
):
    if tracker:
        setattr(settings, tracker, TRACKERS[tracker])

    managing = policy_section(spanish(client, COOKIE_POLICY), 3)

    assert sentence in managing
    assert "Al entrar por primera vez" not in managing
