"""What the tests of the second factor share (``test_mfa`` and ``test_mfa_trusted_browsers``): allauth's endpoints of
the step after the mailed code, the authenticator app's codes and the sign-in up to that step."""

import re
import time
from html import unescape

from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.totp.internal import auth as totp_auth

from accounts.tests.conftest import BROWSER, CONFIRM_CODE, LOGIN, take_mailed_code

AUTHENTICATE = f"{BROWSER}/auth/2fa/authenticate"
#: The answer to «Trust this browser for 14 days» after the app's code (allauth's ``mfa_trust`` stage).
TRUST = f"{BROWSER}/auth/2fa/trust"
TRUST_COOKIE = "mfa_trusted"
FOURTEEN_DAYS = 14 * 24 * 3600
HUB_LOGIN = "/hub-login/"


def _code_at(secret: str, counter: int) -> str:
    return totp_auth.format_hotp_value(totp_auth.hotp_value(secret, counter))


def _counter() -> int:
    return int(time.time()) // mfa_settings.TOTP_PERIOD


def _live_code(secret: str) -> str:
    """What the person's phone shows now."""
    return _code_at(secret, _counter())


def _post(client, path, data):
    return client.post(
        path, data, content_type="application/json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value
    )


def _first_factors(client, email, password):
    """Email and password on the Vue sign-in (headless), then the code mailed to the account
    (``test_sign_in_code``): the answer of that code, signed in or waiting for the app's code."""
    response = _post(client, LOGIN, {"email": email, "password": password})
    assert (response.status_code, _pending_flows(response)) == (401, ["login_by_code"]), response.content
    return _post(client, CONFIRM_CODE, {"code": take_mailed_code(email)})


def _sign_in(client, email, password) -> None:
    """The password and the mailed code; a 2FA account stays at the app's code step."""
    response = _first_factors(client, email, password)
    assert response.status_code in (200, 401), response.content


def _second_step(client, code: str, *, trust: bool = False):
    """The app's (or a recovery) code at the login's second step, then the answer to «Trust this browser for 14
    days» that follows it (ACCOUNTS-F05): the answer that signs in."""
    response = _post(client, AUTHENTICATE, {"code": code})
    assert (response.status_code, _pending_flows(response)) == (401, ["mfa_trust"]), response.content
    return _post(client, TRUST, {"trust": trust})


def _hidden(html: str, name: str) -> str:
    match = re.search(rf'<input type="hidden" name="{name}" value="([^"]*)"', html)
    assert match, f"no hidden input {name!r} in the page"
    return unescape(match.group(1))


def _pending_flows(response) -> list[str]:
    """The flows of a 401 that wait for this session (a signed-in answer lists none)."""
    return [flow["id"] for flow in response.json()["data"].get("flows", []) if flow.get("is_pending")]


def _trust_cookie(user, *, age: int = 0) -> str:
    """The cookie «Trust this browser» leaves for ``user``'s present password and authenticators, given ``age``
    seconds ago (allauth's own encoding)."""
    from allauth.mfa.internal.flows.trust import IssuedTrust, create_config_fingerprint, encode_trust_cookie

    return encode_trust_cookie([IssuedTrust(fingerprint=create_config_fingerprint(user), at=int(time.time()) - age)])
