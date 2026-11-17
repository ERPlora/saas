"""The account surface: the account the app opens in the system browser.

The app opens erplora.com with ``?surface=account``; there the panel paints nothing that sells
(``useSurface()`` of packages/ui). The query does not survive the sign-in's redirects, so the mark
is kept in the session and the SPA gets it in ``spa-config.surface``.
Any other ``?surface=`` leaves it (the other surfaces are the shell's to detect: the Tauri bridge,
the app's user agent, the query), and signing out ends it with the session. Nothing is written to
the session unless the query asks.
"""

from django.http import HttpRequest

PARAM = "surface"
ACCOUNT = "account"
SESSION_KEY = "base.surface"


def account_surface(request: HttpRequest) -> str | None:
    """``"account"`` when the request or its session asks for the account surface, else ``None``."""
    asked = request.GET.get(PARAM)
    if asked == ACCOUNT:
        request.session[SESSION_KEY] = ACCOUNT
    elif asked is not None:
        request.session.pop(SESSION_KEY, None)
    return ACCOUNT if request.session.get(SESSION_KEY) == ACCOUNT else None


def sells_nothing(request: HttpRequest | None) -> bool:
    """Whether ``request`` comes from where nothing is sold: the account surface. Not a call without a session (the
    signed doors of the Hub, a context with no request)."""
    return request is not None and hasattr(request, "session") and account_surface(request) == ACCOUNT
