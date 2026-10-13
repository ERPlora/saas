"""The jump from the SaaS to a hub (PLAN-SAAS §3.1 steps 4-5).

``/hub-login/?hub=<slug>&next=<path>`` mints a one-time code and answers an auto-submitted form
that POSTs it to the hub's callback (OIDC ``response_mode=form_post``: the code never sits in a
URL, the history or a log). Ported from ERPlora/saas ``hub_oauth_bridge``
(``apps/auth/users/views.py``), where the callback was a query parameter checked by
``is_allowed_callback_url``; here it is built from the slug, so it can only ever be a hub's.

Every other answer is a Vue page of the SPA: a refused jump goes to ``/login/error?code=…`` and the
launcher (the entry of ``erplora.com``: one hub → straight to it, several → a selector, none
→ says so) is ``/launch``, which reads ``accounts.hub.list``. ``/launch/`` only leads there.

With ``ACCOUNTS_MFA_ENABLED`` on, an account with an authenticator app jumps only from a session
that passed its second factor (``mfa.mfa_completed``). One signed in without it (Django's
``/admin/login/`` before the flag, or an app turned on after signing in) goes to the Vue page
``/reauthenticate?method=totp&flows=mfa_reauthenticate&next=<this path and query>``, which asks for
a code through allauth's headless ``POST /_allauth/browser/v1/auth/2fa/reauthenticate`` and then loads
``next`` again. ``method=totp`` opens it on the code and ``flows`` (comma-separated) lists the only
ways it may offer: the password reauthentication records ``method == "password"``, never ``mfa``,
so offering it would send the account round in a loop. Not the login's ``…/auth/2fa/authenticate``:
that one only answers while a login waits for its code.
"""

import logging
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounts import mfa, services

logger = logging.getLogger(__name__)

#: The Vue launcher (``accounts/frontend/pages/LaunchPage.vue``).
LAUNCHER = "/launch"
#: The Vue page of every refused sign-in or jump (``LoginErrorPage.vue``), told which by ``code``.
LOGIN_ERROR = "/login/error"
#: The Vue page that asks a signed-in account for a code of its second factor, then loads ``next``.
REAUTHENTICATE = "/reauthenticate"


def login_error_url(code: str, **params: str) -> str:
    """``/login/error?code=<code>&…``: the Vue page that says why the sign-in or the jump stopped."""
    return f"{LOGIN_ERROR}?{urlencode({'code': code, **params}, safe='/')}"


#: The only reauthentication that completes the second factor (``mfa.mfa_completed``).
REAUTHENTICATE_WITH_THE_CODE = {"method": "totp", "flows": "mfa_reauthenticate"}


def reauthenticate_url(next_path: str) -> str:
    """``/reauthenticate?method=totp&flows=mfa_reauthenticate&next=<next_path>``: a code, then back."""
    return f"{REAUTHENTICATE}?{urlencode({**REAUTHENTICATE_WITH_THE_CODE, 'next': next_path}, safe='/')}"


def _local_path(value: str) -> str:
    """``value`` if it is a path on the hub (``/…``, not ``//host`` nor ``/\\host``), else ``/``."""
    parts = urlsplit(value)
    if not value.startswith("/") or value.startswith(("//", "/\\")) or parts.scheme or parts.netloc:
        return "/"
    return value


@require_GET
@never_cache
def hub_login(request: HttpRequest) -> HttpResponse:
    slug = request.GET.get("hub", "")
    # The rule shared with hub-next: a reserved name (``hub``, ``www``…) is no hub either, nor the
    # platform host ``hubs`` (ronda 13).
    if not services.is_hub_slug(slug):
        # Nothing that came from outside is echoed back: it was no hub slug.
        logger.warning("hub_login.invalid_hub")
        return HttpResponseRedirect(login_error_url("invalid_hub"))
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    try:
        code = services.issue_code(request.user, slug, second_factor=mfa.mfa_completed(request))
    except services.SecondFactorRequired:
        logger.info("hub_login.second_factor_required hub=%s", slug)
        return HttpResponseRedirect(reauthenticate_url(request.get_full_path()))
    except services.HubAccessDenied:
        # The page names only the hub's HOST (the person came from it), never its business name.
        logger.info("hub_login.not_a_member hub=%s", slug)
        return HttpResponseRedirect(login_error_url("not_a_member", hub=slug))
    context = {
        "callback_url": settings.HUB_CALLBACK_TEMPLATE.format(slug=slug),
        "code": code,
        "next": _local_path(request.GET.get("next", "")),
    }
    response = render(request, "accounts/hub_login_form.html", context)
    response["Referrer-Policy"] = "no-referrer"
    return response


@require_GET
def launch(request: HttpRequest) -> HttpResponse:
    """The old address of the launcher: the SPA's route (its auth gate sends a visitor to the login)."""
    return HttpResponseRedirect(LAUNCHER)
