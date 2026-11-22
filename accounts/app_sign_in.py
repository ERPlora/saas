"""«Continue with Google» in the installed app: Google in the device's browser, the session back in the app's window.

Google refuses to sign anybody in inside an embedded web view, which does not see the device's Google accounts
either. So the app signs in as native apps do (OAuth for native apps, RFC 8252, with PKCE, RFC 7636):

1. ``/auth/app/start/?challenge=<C>&next=<path>``, in the app's window: keeps ``C`` (the ``S256`` challenge of a
   secret only the app knows) and ``next`` in that window's session, and leads to the browser's leg. The app opens
   that address in the device's browser instead of its window.
2. ``/auth/app/google/?challenge=<C>``, in the browser: posts allauth's own provider redirect, which Google answers
   with its account chooser; it comes back to the next step.
3. ``/auth/app/done/?challenge=<C>``, in the browser and signed in: mints a one-time code bound to ``C`` and shows
   the button that opens ``erplora://signed-in?code=<code>``, the app's own link.
4. ``/auth/app/finish/?code=<code>&verifier=<secret>``, in the app's window: spends the code with the secret and
   opens the session there, then goes on to ``next`` (``LOGIN_REDIRECT_URL`` without one).

The code may be caught on its way back (any app may claim ``erplora://``): without the secret it opens nothing. A
link to step 4 with somebody else's code opens nothing either: the window must have started the sign-in itself
(login CSRF). Step 2 starts Google without a tap of its own, as an authorization endpoint of OAuth does: whoever
follows a link to it only ever signs in as themselves, and its code reaches nobody but the device that opened it.
Every refusal lands on the sign-in's error page (``/login/error?code=authentication_error``).

The window's session passed no sign-in of allauth (no password, code or second factor on record), as a pass from a
business: whatever asks for one asks again.
"""

import base64
import hashlib
import hmac
import logging
import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounts.handoff import login_error_url
from accounts.queries import hub_links
from accounts.services import app_sign_in

logger = logging.getLogger(__name__)

#: Where the code goes back to the app: its own scheme, never an address taken from the request.
APP_RETURN_URL = "erplora://signed-in"
#: What the window's session keeps between steps 1 and 4.
SESSION_KEY = "app_sign_in"
#: An ``S256`` challenge: BASE64URL without padding of a SHA-256, 43 characters.
_CHALLENGE = re.compile(r"[A-Za-z0-9_-]{43}")
#: The session the code opens names this backend: no password nor allauth's flows signed it in here.
_BACKEND = "django.contrib.auth.backends.ModelBackend"


def challenge_of(verifier: str) -> str:
    """The ``S256`` challenge of ``verifier`` (RFC 7636)."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _answer(location: str) -> HttpResponse:
    response = HttpResponseRedirect(location)
    response["Referrer-Policy"] = "no-referrer"
    return response


def _refused(reason: str) -> HttpResponse:
    logger.warning("app_sign_in.refused reason=%s", reason)
    return _answer(login_error_url("authentication_error"))


def _with_challenge(path: str, challenge: str) -> str:
    return f"{path}?{urlencode({'challenge': challenge})}"


def _challenge(request: HttpRequest) -> str | None:
    challenge = request.GET.get("challenge", "")
    return challenge if _CHALLENGE.fullmatch(challenge) else None


@require_GET
@never_cache
def start(request: HttpRequest) -> HttpResponse:
    challenge = _challenge(request)
    if challenge is None:
        return _refused("invalid_challenge")
    next_path = request.GET.get("next", "")
    request.session[SESSION_KEY] = {"challenge": challenge, "next": hub_links.local_path(next_path) if next_path else ""}
    return _answer(_with_challenge(reverse("app_sign_in_google"), challenge))


@require_GET
@never_cache
def google(request: HttpRequest) -> HttpResponse:
    if not settings.GOOGLE_OAUTH_ENABLED:
        raise Http404("Google sign-in is not configured.")
    challenge = _challenge(request)
    if challenge is None:
        return _refused("invalid_challenge")
    context = {
        "action": reverse("redirect_to_provider"),
        "callback_url": _with_challenge(reverse("app_sign_in_done"), challenge),
    }
    return render(request, "accounts/app_sign_in_google.html", context)


@require_GET
@never_cache
def done(request: HttpRequest) -> HttpResponse:
    challenge = _challenge(request)
    if challenge is None:
        return _refused("invalid_challenge")
    if "error" in request.GET:
        return _refused("sign_in_failed")
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    code = app_sign_in.issue_code(request.user, challenge)
    logger.info("app_sign_in.code user=%s", request.user.pk)
    response = render(request, "accounts/app_sign_in_done.html", {"app_url": f"{APP_RETURN_URL}?{urlencode({'code': code})}"})
    response["Referrer-Policy"] = "no-referrer"
    return response


@require_GET
@never_cache
def finish(request: HttpRequest) -> HttpResponse:
    pending = request.session.pop(SESSION_KEY, None) or {}
    challenge = pending.get("challenge", "")
    verifier = request.GET.get("verifier", "")
    if not challenge or not hmac.compare_digest(challenge_of(verifier), challenge):
        return _refused("not_this_window")
    try:
        user = app_sign_in.redeem_code(request.GET.get("code", ""), challenge)
    except app_sign_in.InvalidAppCode:
        return _refused("invalid_code")
    login(request, user, backend=_BACKEND)
    logger.info("app_sign_in.signed_in user=%s", user.pk)
    return _answer(pending.get("next") or settings.LOGIN_REDIRECT_URL)
