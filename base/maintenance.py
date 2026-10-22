"""erplora.com in maintenance mode (ACCOUNTS-G82; PLAN-SAAS §1.1, «Modo mantenimiento»).

The staff turns it on in the admin («Site settings», ``base.models.SiteSettings``), never by ssh nor by a variable of
the deploy (working rules §4). From then every visitor gets the maintenance page, 503 with ``Retry-After``, the answer
search engines read as «down on purpose, come back» (Google, Shopify, Stripe), and a program (``/api/``) the JSON
envelope with the code ``maintenance``. Ported from ERPlora/saas ``MaintenanceModeMiddleware``
(``apps/dashboard/core/middleware/maintenance_middleware.py``, origin/develop c5ca8cae8) with its two gaps closed: the
health checks stay out (the old one answered 503 there and the containers were marked sick), and so does every step of
the staff's sign-in on the way to the admin (the old one cut it at the second factor).

Who keeps using everything: an active staff account with its browser session. What stays out for everyone: the
health checks, the static files, the admin and the staff's sign-in (allauth's API, Google's return and the sign-in
pages whose ``next`` is the admin), the Hub's ``/internal`` calls, Stripe's and Meta's webhooks and the CSP reports.
An API key is no session: its requests get the 503 too.

Placed after ``AuthenticationMiddleware`` and ``base.language.AccountLanguageMiddleware`` (it reads the account and the
language), before anything that runs a view.
"""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.cache import add_never_cache_headers
from django.utils.translation import get_language, gettext

from base import queries

#: Seconds a visitor (or a search engine) is asked to wait before trying again.
RETRY_AFTER_SECONDS = 300

#: Paths answered as always, whoever asks.
EXEMPT_PREFIXES = (
    "/healthz",
    "/readyz",
    "/static/",
    "/admin/",
    "/internal/",
    "/webhooks/",
    "/csp-report/",
    "/_allauth/",
    "/auth/google/callback/",
)
#: The pages of the sign-in (accounts/frontend/routes.ts): served when they lead to the admin, the staff's way in.
SIGN_IN_PAGES = ("/launch", "/login/error", "/verify-email", "/2fa", "/2fa/authenticate", "/reauthenticate")
ADMIN_PREFIX = "/admin/"


def _exempt(request: HttpRequest) -> bool:
    if request.path.startswith(EXEMPT_PREFIXES):
        return True
    return request.path in SIGN_IN_PAGES and request.GET.get("next", "").startswith(ADMIN_PREFIX)


def _is_staff(request: HttpRequest) -> bool:
    user = getattr(request, "user", None)
    # An inactive account has no session any more: Django's backends refuse it (ModelBackend.get_user).
    return bool(user is not None and user.is_authenticated and user.is_staff)


def maintenance_response(request: HttpRequest, state: dict[str, str]) -> HttpResponse:
    """The 503 of the maintenance mode: the JSON envelope for the API, the page for everything else."""
    language = get_language() or "en"
    message = state["es"] if language == "es" and state["es"] else state["en"]
    if request.path.startswith("/api/"):
        response = JsonResponse(
            {
                "error": {
                    "code": "maintenance",
                    "message": message or gettext("ERPlora is under maintenance. Try again in a few minutes."),
                }
            },
            status=503,
        )
    else:
        response = render(request, "503.html", {"maintenance_message": message}, status=503)
    response["Retry-After"] = str(RETRY_AFTER_SECONDS)
    add_never_cache_headers(response)
    return response


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # The switch first: with it off (the usual case) the request's session is never touched.
        if not _exempt(request) and (state := queries.maintenance_state()) is not None and not _is_staff(request):
            return maintenance_response(request, state)
        return self.get_response(request)
