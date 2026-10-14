"""The jump from the SaaS to a hub (PLAN-SAAS §3.1 steps 4-5).

``/hub-login/?hub=<slug>&next=<path>&state=<token>`` mints a one-time code and answers an
auto-submitted form that POSTs it (with ``next`` and ``state``) to the hub's callback (OIDC ``response_mode=form_post``: the code never sits in a
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

``state`` (login CSRF): the Hub starts every jump at its ``/auth/login``, keeps a
``secrets.token_urlsafe(32)`` in a cookie of that browser and sends it here as ``&state=…``; the form
hands it back verbatim next to ``code`` and the Hub's callback compares it with its cookie. Opaque to
the SaaS: never validated, logged nor stored with the code. Absent (or empty), the form carries no
``state`` field and the Hub refuses the jump. Longer than ``STATE_MAX_LENGTH`` it is no state of the
Hub's: the link is refused as broken (``/login/error?code=invalid_hub``: «open your hub and start the
sign-in from its own screen»), before the login and without a code. The login and the 2FA detour
come back to this same path and query (``next``), so the state survives both.

``audience=hub-admin`` is the staff's «Open in the Hub admin» (ronda 13, PLAN §18): the SaaS admin's
button opens ``hubs.erplora.com/auth/login?hub=<slug>&next=/admin/hub/<slug>/`` (``accounts.admin``),
whose ``state`` brings the browser back here. It mints a ``hub-admin`` code (a platform role, no
membership) and posts it to ``HUB_ADMIN_CALLBACK_URL``. Without that role: 403, never a login. With
``ACCOUNTS_MFA_ENABLED`` it always needs the second factor: without it, back to the memberships of
the admin with a message (no detour: an account without an authenticator app could not finish it).
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from accounts import mfa, queries, services
from accounts.models import AuthExchangeCode

logger = logging.getLogger(__name__)

#: The Vue launcher (``accounts/frontend/pages/LaunchPage.vue``).
LAUNCHER = "/launch"
#: The Vue page of every refused sign-in or jump (``LoginErrorPage.vue``), told which by ``code``.
LOGIN_ERROR = "/login/error"
#: The Vue page that asks a signed-in account for a code of its second factor, then loads ``next``.
REAUTHENTICATE = "/reauthenticate"
#: The longest ``state`` handed back to the Hub, which mints 43 characters (``token_urlsafe(32)``).
STATE_MAX_LENGTH = 128
#: ``?audience=`` of the jump; without it, a member enters their hub (``hub-session``).
AUDIENCES = (AuthExchangeCode.HUB_SESSION_AUDIENCE, AuthExchangeCode.HUB_ADMIN_AUDIENCE)
#: Why «Open in the Hub admin» did nothing: with the flag on, ``hub-admin`` needs the second factor.
REFUSED_WITHOUT_SECOND_FACTOR = _("Turn on two-factor authentication and sign in again before opening the Hub admin.")


def login_error_url(code: str, **params: str) -> str:
    """``/login/error?code=<code>&…``: the Vue page that says why the sign-in or the jump stopped."""
    return f"{LOGIN_ERROR}?{urlencode({'code': code, **params}, safe='/')}"


#: The only reauthentication that completes the second factor (``mfa.mfa_completed``).
REAUTHENTICATE_WITH_THE_CODE = {"method": "totp", "flows": "mfa_reauthenticate"}


def reauthenticate_url(next_path: str) -> str:
    """``/reauthenticate?method=totp&flows=mfa_reauthenticate&next=<next_path>``: a code, then back."""
    return f"{REAUTHENTICATE}?{urlencode({**REAUTHENTICATE_WITH_THE_CODE, 'next': next_path}, safe='/')}"


@require_GET
@never_cache
def hub_login(request: HttpRequest) -> HttpResponse:
    slug = request.GET.get("hub", "")
    audience = request.GET.get("audience", AuthExchangeCode.HUB_SESSION_AUDIENCE)
    state = request.GET.get("state", "")
    # The rule shared with hub-next: a reserved name (``hub``, ``www``…) is no hub either, nor the
    # platform host ``hubs`` (ronda 13).
    if not services.is_hub_slug(slug):
        # Nothing that came from outside is echoed back: it was no hub slug.
        logger.warning("hub_login.invalid_hub")
        return HttpResponseRedirect(login_error_url("invalid_hub"))
    if audience not in AUDIENCES or len(state) > STATE_MAX_LENGTH:
        # A link the Hub never builds: refused as a broken one, echoing neither value.
        logger.warning("hub_login.invalid_link hub=%s", slug)
        return HttpResponseRedirect(login_error_url("invalid_hub"))
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    staff_jump = audience == AuthExchangeCode.HUB_ADMIN_AUDIENCE
    try:
        code = services.issue_code(request.user, slug, audience=audience, second_factor=mfa.mfa_completed(request))
    except services.SecondFactorRequired:
        if staff_jump:
            logger.info("hub_login.hub_admin.second_factor_required user=%s hub=%s", request.user.pk, slug)
            messages.error(request, REFUSED_WITHOUT_SECOND_FACTOR)
            return redirect("admin:accounts_hubmembership_changelist")
        logger.info("hub_login.second_factor_required hub=%s", slug)
        return HttpResponseRedirect(reauthenticate_url(request.get_full_path()))
    except services.HubAccessDenied:
        if staff_jump:
            # Signed in without a platform role: 403, never a login (PLAN §17-§18).
            logger.warning("hub_login.hub_admin.denied user=%s", request.user.pk)
            raise PermissionDenied from None
        # The page names only the hub's HOST (the person came from it), never its business name.
        logger.info("hub_login.not_a_member hub=%s", slug)
        return HttpResponseRedirect(login_error_url("not_a_member", hub=slug))
    if staff_jump:
        logger.info("hub_login.hub_admin user=%s hub=%s", request.user.pk, slug)
    context = {
        "callback_url": settings.HUB_ADMIN_CALLBACK_URL
        if staff_jump
        else settings.HUB_CALLBACK_TEMPLATE.format(slug=slug),
        "code": code,
        "next": queries.local_path(request.GET.get("next", "")),
        "state": state,
        "staff_jump": staff_jump,
    }
    response = render(request, "accounts/hub_login_form.html", context)
    response["Referrer-Policy"] = "no-referrer"
    return response


@require_GET
def launch(request: HttpRequest) -> HttpResponse:
    """The old address of the launcher: the SPA's route (its auth gate sends a visitor to the login)."""
    return HttpResponseRedirect(LAUNCHER)
