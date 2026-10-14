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
