"""The SPA's HTML for every path without a URL of its own in Django (last route of the URLconf).

Next to ``spa-config`` it embeds the result of ``base.session.me`` (``session-me``), so the shell
decides on the login without a first round trip. ``spa-config.googleEnabled`` tells the login page
whether «Continue with Google» is configured (``GOOGLE_OAUTH_ENABLED``, the switch of its routes),
``spa-config.mfaEnabled`` whether two-step verification is switched on (``ACCOUNTS_MFA_ENABLED``: off, its
endpoints answer 404 and the Account page does not ask them), and
``spa-config.hubOrigin`` is a hub's origin with ``{slug}`` to fill in: the error page of a refused
jump names the hub's host and links back to it from the slug alone. ``spa-config.surface`` is
``"account"`` on the account surface (``base/surface.py``) and absent otherwise: ``live/spa.html``
takes no attributes for ``<html>``, so ``frontend/main.ts`` reads it here and hands it to
``createShell({ surface })``.

``spa-config.recaptchaSiteKey`` is reCAPTCHA Enterprise's public key, only while it is switched on
(``RECAPTCHA_ENABLED``; off by default since 2026-10-23): the sign-in's pages ask Google's enterprise.js for a token
with it (``accounts/frontend/recaptcha.ts``, ``accounts/bot_check.py``). Off, the page names nothing of reCAPTCHA.
Beside them, ``support-email`` is ``SUPPORT_EMAIL``, the address of the SPA's «Contact Support» (PUBLIC-F18).
Its Content Security Policy admits Stripe for the Store's Embedded Checkout (``base/csp.py``), except on
the account surface, which sells nothing.

A path that names a file (:data:`NOT_A_FILE`: ``/favicon.ico``, ``/apple-touch-icon.png``, ``/wp-login.php``) is no
route of the SPA (:func:`spa_route`): without a URL of its own it gets Django's plain 404, with no shell and no
``csrftoken``, with a session or without and whatever it accepts. The public web's files keep their own URLs
(``robots.txt``, ``llms.txt``, ``sitemap.xml``, IndexNow's key; ``public/urls.py``), matched before the SPA.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_safe
from live import recaptcha
from live.ninja import run_operation_sync
from live.spa import render_spa, spa_path_pattern

from accounts.queries import hub_origin
from base import queries
from base.csp import spa_policy
from base.surface import account_surface

SESSION_ME_ID = "session-me"
SUPPORT_EMAIL_ID = "support-email"
#: A path whose last segment has an extension names a file, and no page of the SPA looks like one (its parameters are
#: UUIDs and allauth's reset key, hex and base 36). It is the fallback rule of connect-history-api-fallback and of
#: ASP.NET Core's ``{*path:nonfile}``. With a trailing slash too: else ``APPEND_SLASH`` would send ``/favicon.ico`` to
#: ``/favicon.ico/``, and that to the shell.
NOT_A_FILE = r"(?!.*\.[^/]*/?$)"


def spa_route(prefixes: tuple[str, ...]) -> str:
    """The SPA's ``re_path``: every path ``live.spa.spa_path_pattern(prefixes)`` leaves it, save a file's."""
    return rf"^{NOT_A_FILE}{spa_path_pattern(prefixes)}"


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    me = run_operation_sync(request, queries.session_me)
    config = {
        "googleEnabled": settings.GOOGLE_OAUTH_ENABLED,
        "mfaEnabled": settings.ACCOUNTS_MFA_ENABLED,
        "hubOrigin": hub_origin("{slug}"),
    }
    if recaptcha.is_enabled():
        config["recaptchaSiteKey"] = recaptcha.site_key()
    surface = account_surface(request)
    if surface is not None:
        config["surface"] = surface
    response = render_spa(
        request,
        extra_json={
            SESSION_ME_ID: me.model_dump(mode="json"),
            # «Contact Support» of the SPA writes here: the public web's one support address (PUBLIC-F18).
            SUPPORT_EMAIL_ID: settings.SUPPORT_EMAIL,
        },
        extra_config=config,
    )
    # What Django's `csp_override` sets: the middleware builds the header from it, with the nonce.
    response._csp_config = spa_policy(settings.SECURE_CSP, sells=surface is None)
    return response
