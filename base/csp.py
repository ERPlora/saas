"""The SPA's Content Security Policy with Stripe (lot L2-D; PLAN-SAAS §3.6 point 17; plan §7 point 5).

Stripe.js is the ONE script the SaaS takes from another origin — PCI: it is never served by us — and the
Embedded Checkout runs in Stripe's frames, so the SPA's policy (``settings.SECURE_CSP``, ``live.csp``)
gains the origins Stripe's security guide lists for Checkout and Stripe.js, and nothing else: the nonce,
``'strict-dynamic'`` and Trusted Types stay. The SPA inserts the script itself (a nonced script's
insertion, which ``'strict-dynamic'`` trusts); Stripe.js's loader then sets its chunks' URLs as plain
strings, which the page's ``default`` Trusted Types policy admits for ``https://js.stripe.com`` only
(``createShell({ trustedScriptOrigins })``, frontend/main.ts): ``trusted-types`` is ``live.csp``'s, untouched.

Only a page that may sell gets it: the account surface (``?surface=account``) sells nothing (round 17
§2.6), and neither does any other response (the API, the public web, which has its own policy).
``base/spa.py`` sets it on the SPA's HTML as Django's ``csp_override`` does (``response._csp_config``).
"""

from django.conf import settings

#: Stripe's origins by directive (https://docs.stripe.com/security/guide, «Content Security Policy»:
#: Checkout and Stripe.js; without ``maps.googleapis.com``, which only Elements' address autocomplete in
#: OUR page uses).
STRIPE_SOURCES: dict[str, list[str]] = {
    "script-src": ["https://js.stripe.com", "https://*.js.stripe.com", "https://checkout.stripe.com"],
    "frame-src": [
        "https://js.stripe.com",
        "https://*.js.stripe.com",
        "https://hooks.stripe.com",
        "https://checkout.stripe.com",
    ],
    "connect-src": [
        "https://api.stripe.com",
        "https://checkout.stripe.com",
        "https://merchant-ui-api.stripe.com",
    ],
    "img-src": ["https://*.stripe.com"],
}

def spa_policy(policy: dict[str, list[str]], *, sells: bool) -> dict[str, list[str]]:
    """``policy`` (a fresh copy, never the settings' own lists) with Stripe's origins when the page may sell.

    A directive the policy did not have starts from its ``default-src``, so what it admitted before
    (``'self'``) it still admits.
    """
    result = {name: list(sources) for name, sources in policy.items()}
    if not sells:
        return result
    for name, sources in STRIPE_SOURCES.items():
        current = result.get(name, list(result.get("default-src", [])))
        result[name] = [*current, *(source for source in sources if source not in current)]
    return result


# --- The admin (ACCOUNTS-G10; the old SaaS's saas#1828) -------------------------------------------------------------

#: Trusted Types' directives: Django's admin creates no policy, and its jQuery assigns ``innerHTML`` while it loads.
TRUSTED_TYPES_DIRECTIVES = ("require-trusted-types-for", "trusted-types")


def admin_policy(policy: dict[str, list[str]]) -> dict[str, list[str]]:
    """``policy`` (a fresh copy) without Trusted Types: the nonce, ``'strict-dynamic'`` and the rest stay.

    Django 6.1's admin puts the request's nonce on its scripts, so ``'strict-dynamic'`` lets them in; Trusted Types
    would still stop jQuery at load (``div.innerHTML = "<textarea>…"``), and with it every widget of the admin.
    """
    return {name: list(sources) for name, sources in policy.items() if name not in TRUSTED_TYPES_DIRECTIVES}


class AdminCSPMiddleware:
    """Serve :func:`admin_policy` on the admin's responses (``/admin/``, the ``admin`` namespace).

    After ``django.middleware.csp.ContentSecurityPolicyMiddleware`` in ``MIDDLEWARE``, as ``public.csp``'s: its
    response hook runs first and leaves the override ready when Django's builds the header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        if match is not None and match.namespace == "admin" and getattr(response, "_csp_config", None) is None:
            response._csp_config = admin_policy(settings.SECURE_CSP)
        return response
