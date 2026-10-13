"""URLconf of saas-next: Django's own prefixes first, then the SPA for every other path.

Django keeps sign-in (allauth's template pages and its headless API at ``/_allauth/``, Google at the
redirect URIs registered with it), the jump to a hub and its redeem, the API, the live stream, the
admin and the CSP reports. ``/healthz`` is answered by ``base.health.HealthCheckMiddleware`` before
the Host is validated, so it has no route here. Every other path is the Ionic Vue SPA (``base.spa``):
the sign-in (``/login``), its errors (``/login/error``) and the launcher (``/launch``) among them.
"""

from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from live.csp import csp_report
from live.live_view import live_stream
from live.spa import BASE_NON_SPA_PREFIXES, spa_path_pattern

from accounts import admin as accounts_admin
from accounts import google, handoff, internal
from base.spa import spa
from config.api import api

# Prefixes of saas-next on top of the shared ones: allauth (templates and headless API), Google's
# redirect URIs and the jump to a hub. Not `launch`: `/launch` is the SPA's launcher, and only the
# exact `/launch/` (its old address) is a Django route, matched before the SPA's catch-all.
NON_SPA_PREFIXES = (
    *BASE_NON_SPA_PREFIXES,
    "_allauth",
    "accounts",
    "auth",
    "hub-login",
)

# With ACCOUNTS_MFA_ENABLED on, the admin's login is allauth's (it asks for the second factor).
# Assigned before `admin.site.urls` is read below: `AdminSite.get_urls` binds `self.login` then.
admin.site.login = accounts_admin.admin_login

urlpatterns = [
    path("", RedirectView.as_view(url=handoff.LAUNCHER), name="home"),
    # allauth's «connections» page connected and disconnected Google with the open session alone
    # (saas#2552): Google links only by signing in with it. Same address and name as allauth's.
    path(
        "accounts/3rdparty/",
        RedirectView.as_view(url=handoff.LAUNCHER, permanent=False),
        name="socialaccount_connections",
    ),
    # allauth's «Login Cancelled» and «Third-Party Login Failure» pages are the Vue error page.
    # Same addresses and names as allauth's.
    path(
        "accounts/3rdparty/login/cancelled/",
        RedirectView.as_view(url=handoff.login_error_url("login_cancelled"), permanent=False),
        name="socialaccount_login_cancelled",
    ),
    path(
        "accounts/3rdparty/login/error/",
        RedirectView.as_view(url=handoff.login_error_url("authentication_error"), permanent=False),
        name="socialaccount_login_error",
    ),
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
    # «Continue with Google» at the redirect URIs registered with Google (/auth/google/callback/,
    # PLAN-SAAS §6). Registered AFTER allauth's include on purpose: same names as allauth's
    # provider routes, and `reverse()` returns the LAST pattern defined, so the redirect_uri allauth
    # builds for the authorization and for the token exchange is this path, not
    # /accounts/google/login/callback/.
    path("auth/google/login/", google.login, name="google_login"),
    path("auth/google/callback/", google.callback, name="google_callback"),
    path("launch/", handoff.launch, name="launch"),
    path("hub-login/", handoff.hub_login, name="hub_login"),
    path("internal/auth/redeem", internal.redeem, name="internal_auth_redeem"),
    # Before the API's prefix, which would otherwise answer it.
    path("api/live", live_stream, name="live-stream"),
    path("api/", api.urls),
    path("csp-report/", csp_report, name="csp-report"),
    # The admin's «Hubs» page (ronda 13): before the admin's own URLs, whose catch-all would take it.
    path("admin/accounts/hubs/", admin.site.admin_view(accounts_admin.hubs_view), name="accounts_hubs"),
    path("admin/", admin.site.urls),
    re_path(spa_path_pattern(NON_SPA_PREFIXES), spa, name="spa"),
]
