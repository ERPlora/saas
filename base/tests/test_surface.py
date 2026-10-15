"""The account surface (PLAN-SAAS §3.6 point 6): ``?surface=account``, sticky in the session.

The app opens the account in the system browser with ``?surface=account``: there the panel paints
nothing that sells. The query does not survive the sign-in's redirects, so the server keeps the
mark in the session and hands it to the SPA in ``spa-config.surface``, which ``frontend/main.ts``
passes to ``createShell({ surface })``. Any other ``?surface=`` leaves it, and signing out ends it
with the session. ``live/spa.html`` takes no attributes for ``<html>``, hence ``spa-config``.
"""

import json
import re

import pytest

from accounts.tests.conftest import prove_address, sign_in

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("spa_manifest")]

HOST = "localhost:8001"
SESSION = "/_allauth/browser/v1/auth/session"


@pytest.fixture
def ana(ana):
    """Ana once she proved her address, as every account does before its first session."""
    prove_address(ana.email)
    return ana


def spa_config(response) -> dict:
    assert response.status_code == 200
    match = re.search(
        r'<script id="spa-config" type="application/json"[^>]*>(.*?)</script>',
        response.content.decode(),
        re.S,
    )
    assert match, "no spa-config block"
    return json.loads(match.group(1))


def surface_of(client, path: str):
    return spa_config(client.get(path, HTTP_HOST=HOST)).get("surface", "absent")


def test_the_web_has_no_surface_and_writes_no_session(client, settings):
    response = client.get("/businesses", HTTP_HOST=HOST)

    assert "surface" not in spa_config(response)
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_the_query_marks_the_account_surface(client):
    assert surface_of(client, "/businesses?surface=account") == "account"


def test_the_mark_sticks_to_the_session(client):
    surface_of(client, "/account?surface=account")

    assert surface_of(client, "/businesses") == "account"
    assert surface_of(client, "/billing") == "account"


def test_the_mark_survives_signing_in(client, ana, password):
    """The app's link lands on the sign-in of the launcher (the query is lost on the way), then on the panel:
    the password and the mailed code (``sign_in``) keep the session's mark."""
    surface_of(client, "/launch?next=/account%3Fsurface%3Daccount&surface=account")

    sign_in(client, ana.email, password)

    assert surface_of(client, "/account") == "account"


@pytest.mark.parametrize("other", ["web", "desktop", "nonsense", ""])
def test_any_other_surface_leaves_it(client, other):
    surface_of(client, "/account?surface=account")

    assert surface_of(client, f"/account?surface={other}") == "absent"
    assert surface_of(client, "/account") == "absent"


def test_signing_out_ends_it(client, ana, password):
    sign_in(client, ana.email, password)
    surface_of(client, "/account?surface=account")

    signed_out = client.delete(SESSION, HTTP_HOST=HOST)

    assert signed_out.status_code == 401  # allauth.headless answers the anonymous state
    assert surface_of(client, "/account") == "absent"


def test_only_the_account_surface_is_kept(client):
    """The other surfaces are the shell's to detect (the Tauri bridge, the user agent, the query)."""
    assert surface_of(client, "/account?surface=mobile") == "absent"
