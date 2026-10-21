"""WHATSAPP-F01, WHATSAPP-F11 · ``GET /whatsapp/return``: the page Meta's window (Embedded Signup) is sent back to
with its one-time code, which hands it to the Hub's page that opened the window and closes itself.

The Hub opens Meta's window without Facebook's SDK (its WORKBOOK ``whatsapp_inbox``, «La ventana de Meta sin el SDK de
Facebook»): Meta ends it by sending the browser to door 10's ``redirect_uri`` with ``?code=…&state=<slug>.<32 hex>``
(or ``?error=…``). This page posts ``{"type": "erplora.whatsapp.signup", "state", "code" | "error",
"error_description"}`` to ``window.opener`` only at the origin of the hub the ``state`` names, never ``"*"``; a
``state`` that names no hub posts nothing. Its ``Cross-Origin-Opener-Policy`` is ``unsafe-none`` (Django's
``same-origin`` would cut the window from its opener, a page of another origin); every other page keeps Django's.
The data travel as ``json_script`` read by the one script, which carries the CSP's nonce.
"""

import json
import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

PATH = "/whatsapp/return"
NONCE = "0123456789abcdef0123456789abcdef"
STATE = f"bar-manolo.{NONCE}"
CODE = "AQBx-one-time-code_9"
DATA_ID = "whatsapp-signup-return"
CLOSE_EN = "This window can be closed now."
CLOSE_ES = "Esta ventana ya se puede cerrar."


@pytest.fixture
def hubs_in_production(settings):
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"
    return settings


def page(client, language="en", **query):
    return client.get(PATH, query, HTTP_ACCEPT_LANGUAGE=language)


def posted(response):
    """What the page posts to its opener (``{"message", "target"}``), or ``None`` when it posts nothing."""
    found = re.search(rf'<script id="{DATA_ID}" type="application/json">(.*?)</script>', response.content.decode(), re.S)
    return json.loads(found.group(1)) if found else None


def test_the_route_is_named():
    assert reverse("whatsapp_signup_return") == PATH


def test_the_code_goes_back_only_to_the_hub_the_state_names(client, hubs_in_production):
    response = page(client, code=CODE, state=STATE)

    assert response.status_code == 200
    assert posted(response) == {
        "message": {"type": "erplora.whatsapp.signup", "state": STATE, "code": CODE},
        "target": "https://bar-manolo.erplora.com",
    }


def test_the_hub_s_origin_follows_the_environment_s_hubs(client, settings):
    settings.HUB_CALLBACK_TEMPLATE = "http://{slug}.localhost:8600/auth/callback"

    assert posted(page(client, code=CODE, state=f"a.{NONCE}"))["target"] == "http://a.localhost:8600"


def test_meta_s_refusal_goes_back_with_its_reason(client, hubs_in_production):
    response = page(
        client, error="access_denied", error_code="200", error_reason="user_denied",
        error_description="Permissions error", state=STATE,
    )

    assert posted(response) == {
        "message": {
            "type": "erplora.whatsapp.signup", "state": STATE, "error": "access_denied",
            "error_description": "Permissions error",
        },
        "target": "https://bar-manolo.erplora.com",
    }


@pytest.mark.parametrize(
    "state",
    [
        "",
        "bar-manolo",  # no attempt
        f"bar-manolo.{NONCE[:-1]}",  # 31 hex
        f"bar-manolo.{NONCE}0",  # 33 hex
        f"bar-manolo.{NONCE.upper()}",  # the Hub writes lowercase hex
        f"bar-manolo.{'g' * 32}",  # not hex
        f"Bar-Manolo.{NONCE}",  # a hub's name is lowercase
        f"-bar.{NONCE}",
        f"www.{NONCE}",  # reserved
        f"hubs.{NONCE}",  # the Hub's admin, never a business
        f"demo-bar.{NONCE}",  # a demo connects no number
        f"evil.example/x.{NONCE}",
        f"evil.example.{NONCE}",  # never another domain
        f"bar-manolo.{NONCE}\n",
    ],
)
def test_a_state_that_names_no_hub_posts_nothing(client, hubs_in_production, state):
    response = page(client, code=CODE, state=state)

    assert response.status_code == 200
    assert posted(response) is None
    assert CLOSE_EN in response.content.decode()


@pytest.mark.parametrize(
    "query",
    [
        {},  # neither a code nor Meta's reason
        {"code": ""},
        {"code": "x" * 2049},  # longer than any code door 11 takes
    ],
)
def test_without_a_usable_code_or_reason_it_posts_nothing(client, hubs_in_production, query):
    response = page(client, state=STATE, **query)

    assert posted(response) is None
    assert CLOSE_EN in response.content.decode()


def test_the_longest_code_door_11_takes_still_goes_back(client, hubs_in_production):
    assert posted(page(client, code="x" * 2048, state=STATE))["message"]["code"] == "x" * 2048


def test_meta_s_reason_is_cut_to_a_readable_length(client, hubs_in_production):
    message = posted(page(client, error="e" * 600, error_description="d" * 600, state=STATE))["message"]

    assert (len(message["error"]), len(message["error_description"])) == (200, 500)


def test_only_this_page_keeps_its_opener_every_other_keeps_django_s_policy(client, hubs_in_production):
    assert page(client, code=CODE, state=STATE)["Cross-Origin-Opener-Policy"] == "unsafe-none"
    assert page(client, state="nobody")["Cross-Origin-Opener-Policy"] == "unsafe-none"
    assert client.get("/accounts/login/")["Cross-Origin-Opener-Policy"] == "same-origin"


def test_its_one_script_carries_the_csp_s_nonce(client, hubs_in_production):
    response = page(client, code=CODE, state=STATE)

    nonce = re.search(r"'nonce-([^']+)'", response["Content-Security-Policy"]).group(1)
    scripts = re.findall(r"<script\b([^>]*)>", response.content.decode())
    executable = [attributes for attributes in scripts if 'type="application/json"' not in attributes]
    assert executable == [f' nonce="{nonce}"']
    assert "unsafe-inline" not in re.search(r"script-src[^;]*", response["Content-Security-Policy"]).group(0)


def test_what_meta_sends_back_is_data_never_markup(client, hubs_in_production):
    hostile = '</script><script>alert(1)</script>'

    response = page(client, error=hostile, error_description=hostile, state=STATE)

    assert hostile not in response.content.decode()
    assert posted(response)["message"]["error_description"] == hostile


def test_it_needs_no_session_and_is_never_cached(client, hubs_in_production):
    response = page(client, code=CODE, state=STATE)

    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]


def test_only_get_is_answered(client, hubs_in_production):
    assert client.post(PATH, {"code": CODE, "state": STATE}).status_code == 405


@pytest.mark.parametrize(("language", "text"), [("en", CLOSE_EN), ("es", CLOSE_ES)])
def test_it_speaks_the_browser_s_language(client, hubs_in_production, language, text):
    html = page(client, language=language, code=CODE, state=STATE).content.decode()

    assert f'<html lang="{language}"' in html
    assert text in html
