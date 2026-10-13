"""What every template of the public web knows.

Ported from ERPlora/saas ``config/context_processors.py`` (``site_settings``, origin/develop
c5ca8ca), only its public part: the analytics ids, the support address and the two flags the
analytics partial reads.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

from public.crawlers import is_private

#: Pages that show passwords or one-time codes: allauth's template pages and headless API, and the
#: sign-in pages of the SPA (``accounts/frontend/routes.ts`` and the pages allauth's mails link).
CREDENTIALS_PREFIXES = ("/accounts/", "/_allauth/")
CREDENTIALS_SPA_PAGES = (
    "/login",
    "/signup",
    "/password",
    "/verify-email",
    "/2fa",
    "/reauthenticate",
)


def _is_authenticated(request: HttpRequest) -> bool:
    """An error page may render a request that never reached ``AuthenticationMiddleware`` (a 404
    raised before it): ``request.user`` is not guaranteed (saas#1631)."""
    user = getattr(request, "user", None)
    return bool(user is not None and user.is_authenticated)


def _is_credentials_page(path: str) -> bool:
    if path.startswith(CREDENTIALS_PREFIXES):
        return True
    return any(
        path == page or path.startswith(f"{page}/") for page in CREDENTIALS_SPA_PAGES
    )


def public_site(request: HttpRequest) -> dict:
    path = getattr(request, "path", "")
    return {
        "GA_MEASUREMENT_ID": settings.GA_MEASUREMENT_ID,
        "CLARITY_PROJECT_ID": settings.CLARITY_PROJECT_ID,
        # The visible support contact (footer, help, landing): one source.
        "SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        # Clarity records the screen: only an anonymous visitor on the public half. The boundary
        # is the session, not the URL, so a private page added later is covered (saas#958).
        "is_public_page": not _is_authenticated(request) and not is_private(request),
        # Passwords and one-time codes: no analytics there, whatever the consent (saas#958).
        "is_credentials_page": _is_credentials_page(path),
    }
