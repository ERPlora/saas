"""The bots' check in front of allauth.headless's public doors (Ioan, 2026-10-22: «siempre que hay un form hay que
meter recaptcha», «límites en los registros de login para que no intenten sin parar»): reCAPTCHA on every one, and a
limit per address on the ones that take a code.

Every POST to one of ``RECAPTCHA_DOORS`` carries ``recaptcha_token`` in its JSON body, a token Google's
``enterprise.js`` made for that door's action (the SPA adds it, ``accounts/frontend/recaptcha.ts``), and Google is
asked before allauth sees the request (``live.recaptcha.verify_or_raise``). Refused, the answer is allauth's own
envelope, 400 ``recaptcha_failed`` with one message for the whole form (no ``param``), so the SPA's allauth client
paints it as any refusal of allauth's. Reads (GET) and every other door (the session, the account's own pages behind
a session) go through untouched.

The doors that take a code (the mailed ones and the authenticator app's) also count the refused codes of each
address: ``code_attempts`` of ``ACCOUNT_RATE_LIMITS`` (allauth's limiter, on the shared cache). Past it, 429 before
Google is asked; a code is counted once allauth refuses it (400, or 409 when no code waits), never a right one, so
the people of one office signing in again and again never use up a guesser's budget. allauth already gives each
mailed code 3 tries; this stops one address from starting sign-in after sign-in to try codes without end.

A ``process_view`` after ``CsrfViewMiddleware``: a request that fails the CSRF check never costs an assessment. The
2FA door answers 404 while ``ACCOUNTS_MFA_ENABLED`` is off (``accounts.mfa``) before this runs. «Continue with Google»
(``auth/provider/redirect``) is not here: Google's own sign-in checks who is there.
"""

from __future__ import annotations

import json

from allauth.core import ratelimit
from django.http import HttpRequest, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext
from live.recaptcha import RecaptchaFailed, verify_or_raise

BROWSER = "/_allauth/browser/v1"

#: allauth.headless's public doors and the reCAPTCHA action each one's token must be made for (the same names in
#: ``accounts/frontend/recaptcha.ts``).
RECAPTCHA_DOORS: dict[str, str] = {
    f"{BROWSER}/auth/login": "login",
    f"{BROWSER}/auth/signup": "signup",
    f"{BROWSER}/auth/password/request": "password_reset",
    f"{BROWSER}/auth/password/reset": "password_reset_confirm",
    f"{BROWSER}/auth/email/verify": "verify_email",
    f"{BROWSER}/auth/email/verify/resend": "verify_email_resend",
    f"{BROWSER}/auth/code/confirm": "login_code",
    f"{BROWSER}/auth/2fa/authenticate": "mfa_authenticate",
}

#: The doors that take a code: their tries count per address (``code_attempts``).
CODE_DOORS = frozenset(
    {f"{BROWSER}/auth/code/confirm", f"{BROWSER}/auth/email/verify", f"{BROWSER}/auth/2fa/authenticate"}
)
#: The action of ``ACCOUNT_RATE_LIMITS`` that counts them.
CODE_ATTEMPTS = "code_attempts"
#: allauth's answers to a refused code: a wrong one (400) or none waiting (409).
REFUSED_CODE_STATUSES = frozenset({400, 409})
#: Set on a request to a code door, so its answer is counted (``process_response``).
_COUNT_CODE = "_bot_check_count_code"

#: Where the token travels in the JSON body.
TOKEN_FIELD = "recaptcha_token"


def _token(request: HttpRequest) -> object:
    """The body's ``recaptcha_token``; ``None`` when the body is not a JSON object."""
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return body.get(TOKEN_FIELD) if isinstance(body, dict) else None


def allauth_error(status: int, code: str, message: str) -> JsonResponse:
    """An answer in allauth.headless's shape, for the whole form, so its client reads it as one of its own."""
    return JsonResponse({"status": status, "errors": [{"code": code, "message": message}]}, status=status)


class BotCheckMiddleware(MiddlewareMixin):
    """After ``CsrfViewMiddleware``: the refused codes per address, then reCAPTCHA's verdict, before allauth.headless's
    public doors (POST)."""

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        action = RECAPTCHA_DOORS.get(request.path_info)
        if action is None or request.method != "POST":
            return None
        if request.path_info in CODE_DOORS:
            if not ratelimit.consume(request, action=CODE_ATTEMPTS, dry_run=True):
                return allauth_error(
                    429, "too_many_requests", gettext("Too many attempts. Please try again in a few minutes.")
                )
            setattr(request, _COUNT_CODE, True)
        try:
            verify_or_raise(request, _token(request), action)
        except RecaptchaFailed as refused:
            return allauth_error(refused.status, refused.code, refused.message)
        return None

    def process_response(self, request: HttpRequest, response):
        if getattr(request, _COUNT_CODE, False) and response.status_code in REFUSED_CODE_STATUSES:
            ratelimit.consume(request, action=CODE_ATTEMPTS)
        return response
