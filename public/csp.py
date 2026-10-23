"""The public web's Content Security Policy (spec §8.2).

Ported from ERPlora/saas ``apps/public/csp.py`` (origin/develop c5ca8ca). The account panel (the
SPA) and the sign-in pages keep the global policy of ``live.csp`` (``settings.SECURE_CSP``, with
``'strict-dynamic'`` and Trusted Types). The public web's pages are server templates that load one
Vite entry (``frontend/public.ts``) by nonce from this origin and swap no script in at runtime, so
they need neither: ``'strict-dynamic'`` disables host allowlisting (it blocked the script an edge
injects with no nonce, saas#1559) and Trusted Types blocks Ionic's ``ion-icon`` SVG sink (saas#1560).

``PublicCSPMiddleware`` sets ``response._csp_config``, the override Django's
``ContentSecurityPolicyMiddleware`` reads, so it sits after that one in ``MIDDLEWARE``. The policy
is always enforced: saas-next has no report-only toggle. A public view that set its own override keeps
it: ``/demo/`` and ``/demo/enter/`` (public/demo.py) widen ``form-action`` to the hubs' origin, where their
form (or the redirect that answers it) goes.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.csp import CSP
from live.recaptcha import with_recaptcha

#: Namespace of the public web's URLconf (``public/urls.py``).
PUBLIC_NAMESPACES = frozenset({"public"})

#: Public routes with no namespace: django-cookie-consent's (``/cookies/``) is a third-party
#: URLconf with no ``app_name``, and namespacing it would break the ``{% url
#: 'cookie_consent_accept' %}`` of the package's own templates. Its URL names are the only handle.
PUBLIC_URL_NAMES = frozenset(
    {
        "cookie_consent_cookie_group_list",
        "cookie_consent_accept",
        "cookie_consent_decline",
        "cookie_consent_status",
    }
)

#: Directives a running Vite dev server widens with DEBUG (the shape of ``live.csp.debug_policy``),
#: ``script-src`` included: without ``'strict-dynamic'`` the dev server's modules need their source.
_DEV_SERVER_DIRECTIVES = (
    "script-src",
    "connect-src",
    "style-src",
    "font-src",
    "img-src",
)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def public_policy() -> dict[str, list[str]]:
    """The public web's policy, a fresh dict on every call, read from the settings of the moment.

    No CDN (OutfitKit and Iconify's API are gone) and no Stripe (the public web no longer charges).
    Google Analytics and Clarity, which the templates load only after the analytical consent. The
    Hub's static origin (``HUB_STATIC_BASE_URL``) serves the apps' documentation images; locally it
    is ``http://``, which ``https:`` does not cover. ``ipc:`` keeps the Tauri app's hardware bridge.
    reCAPTCHA Enterprise's scripts, frames and connection (``live.recaptcha.with_recaptcha``): the contact
    form and the demo ask Google whether a person sent them.
    """
    policy = {
        "default-src": [CSP.SELF],
        "script-src": [CSP.SELF, CSP.NONCE, "www.googletagmanager.com", "*.clarity.ms"],
        "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
        "font-src": [CSP.SELF, "data:"],
        "img-src": [CSP.SELF, "data:", "https:", _origin(settings.HUB_STATIC_BASE_URL)],
        "connect-src": [
            CSP.SELF,
            "ipc:",
            "http://ipc.localhost",
            "*.google-analytics.com",
            "*.analytics.google.com",
            "*.clarity.ms",  # Clarity's beacon upload
            "c.bing.com",  # Clarity's beacon upload
        ],
        "frame-ancestors": [CSP.SELF],
        "base-uri": [CSP.SELF],
        "form-action": [CSP.SELF],
        "object-src": [CSP.NONE],
        "report-uri": ["/csp-report/"],
    }
    dev_server = settings.LIVE["spa"].get("dev_server")
    if settings.DEBUG and dev_server:
        for directive in _DEV_SERVER_DIRECTIVES:
            policy[directive].append(dev_server)
        policy["connect-src"].append("ws" + dev_server.removeprefix("http"))
    return with_recaptcha(policy)


def is_public(request: HttpRequest, response: HttpResponse | None = None) -> bool:
    """Whether ``response`` answers a page of the public web.

    By the ``public`` namespace, by the URL name of a namespace-less public route, or any 404 that
    matched no pattern at all (Django sets no ``resolver_match`` then, saas#1827): the 404 page is
    the public web's. A non-404 without ``resolver_match`` is an early middleware short-circuit and
    stays out.
    """
    match = getattr(request, "resolver_match", None)
    if match is not None:
        if match.namespace in PUBLIC_NAMESPACES or match.app_name in PUBLIC_NAMESPACES:
            return True
        return (
            not match.namespace
            and not match.app_name
            and match.url_name in PUBLIC_URL_NAMES
        )
    return response is not None and response.status_code == 404


class PublicCSPMiddleware:
    """Serve :func:`public_policy` on the public web's responses.

    After ``django.middleware.csp.ContentSecurityPolicyMiddleware`` in ``MIDDLEWARE``: its response
    hook runs first and leaves the override ready when Django's builds the header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if is_public(request, response) and getattr(response, "_csp_config", None) is None:
            response._csp_config = public_policy()
        return response
