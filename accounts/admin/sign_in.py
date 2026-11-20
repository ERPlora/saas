"""``/admin/login/`` hands over to the SaaS's sign-in, ``LOGIN_URL`` (``admin_login``, installed by
``config/urls.py``), which asks for the mailed code; with ``ACCOUNTS_MFA_ENABLED`` on, the staff enter only with
an authenticator app (``admin_has_permission``; without one, ``/2fa`` to set it up) and the jump also
needs the authenticator app's code in the session.
"""

from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from accounts.queries import two_factor

#: The Vue page of the second factor's settings, where staff without an authenticator app set it up.
TWO_FACTOR_SETTINGS = "/2fa"


def _admin_next(request: HttpRequest) -> str:
    """Where the admin was going: a path of this host, never the login itself (it would loop)."""
    index = reverse("admin:index")
    next_url = request.GET.get("next") or index
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return index
    if urlsplit(next_url).path == reverse("admin:login"):
        return index
    return next_url


def admin_has_permission(request: HttpRequest) -> bool:
    """Who enters the admin (``admin.site.has_permission``, installed by ``config/urls.py``): an active staff account,
    as Django's rule, and with ``ACCOUNTS_MFA_ENABLED`` only one with an authenticator app. The account is checked:
    the sign-in asked the app's code (or a browser the account trusts skipped it). Recovery codes alone are no second
    factor."""
    user = request.user
    if not (user.is_active and user.is_staff):
        return False
    return not settings.ACCOUNTS_MFA_ENABLED or two_factor.has_totp(user)


def _owes_the_app(request: HttpRequest) -> bool:
    """Signed-in staff kept out of the admin only for lack of an authenticator app."""
    user = request.user
    return user.is_authenticated and user.is_active and user.is_staff and not admin.site.has_permission(request)


@never_cache
def admin_login(request: HttpRequest, extra_context=None) -> HttpResponse:
    """``/admin/login/``: the SaaS's sign-in, never Django's own.

    Django's admin login signs in through ``django.contrib.auth`` alone, without allauth's stages, so
    without the code mailed at every sign-in (``ACCOUNT_LOGIN_BY_CODE_REQUIRED``) and without the
    authenticator app (``ACCOUNTS_MFA_ENABLED``). It signs nobody in (not even by ``POST``): the visitor
    goes to ``LOGIN_URL?next=…`` (the launcher's sign-in, allauth.headless), whose code steps
    (``/verify-email``, ``/2fa/authenticate``) record both. Staff already signed in go where they were
    going; staff without the authenticator app the admin needs (``admin_has_permission``) go to set it up on
    ``/2fa``, which comes back to ``next`` (never a 403); any other signed-in account gets 403,
    never the login: the sign-in sends a signed-in account straight to ``next`` (the admin), which would send it back
    here.
    """
    next_url = _admin_next(request)
    if admin.site.has_permission(request):
        return HttpResponseRedirect(next_url)
    if _owes_the_app(request):
        return HttpResponseRedirect(f"{TWO_FACTOR_SETTINGS}?{urlencode({'next': next_url}, safe='/')}")
    if request.user.is_authenticated:
        raise PermissionDenied
    return HttpResponseRedirect(f"{settings.LOGIN_URL}?{urlencode({'next': next_url}, safe='/')}")
