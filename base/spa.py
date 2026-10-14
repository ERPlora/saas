"""The SPA's HTML for every path without a URL of its own in Django (last route of the URLconf).

Next to ``spa-config`` it embeds the result of ``base.session.me`` (``session-me``), so the shell
decides on the login without a first round trip. ``spa-config.googleEnabled`` tells the login page
whether «Continue with Google» is configured (the same switch as the template login's button), and
``spa-config.hubOrigin`` is a hub's origin with ``{slug}`` to fill in: the error page of a refused
jump names the hub's host and links back to it from the slug alone. ``spa-config.surface`` is
``"account"`` on the account surface (``base/surface.py``) and absent otherwise: ``live/spa.html``
takes no attributes for ``<html>``, so ``frontend/main.ts`` reads it here and hands it to
``createShell({ surface })``.

Its Content Security Policy admits Stripe for the Store's Embedded Checkout (``base/csp.py``), except on
the account surface, which sells nothing.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_safe
from live.ninja import run_operation_sync
from live.spa import render_spa

from accounts.queries import hub_origin
from base import queries
from base.csp import spa_policy
from base.surface import account_surface

SESSION_ME_ID = "session-me"


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    me = run_operation_sync(request, queries.session_me)
    config = {"googleEnabled": settings.GOOGLE_OAUTH_ENABLED, "hubOrigin": hub_origin("{slug}")}
    surface = account_surface(request)
    if surface is not None:
        config["surface"] = surface
    response = render_spa(
        request,
        extra_json={SESSION_ME_ID: me.model_dump(mode="json")},
        extra_config=config,
    )
    # What Django's `csp_override` sets: the middleware builds the header from it, with the nonce.
    response._csp_config = spa_policy(settings.SECURE_CSP, sells=surface is None)
    return response
