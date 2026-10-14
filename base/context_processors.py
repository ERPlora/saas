"""What every template of saas-next knows about the shell's colour mode.

``theme`` is the mode of ``@erplora/ui`` (``packages/ui/src/shell/theme.ts``): ``system``, ``light`` or
``dark``, and ``system`` when nothing says otherwise. A signed-in account gets the mode it chose in
Account → Preferences (``accounts.UserPreferences.theme_mode``, the one the panel paints), so the public
web and the sign-in pages look like the panel. Anyone else gets the ``theme`` cookie, as ERPlora/saas
did (``apps/core/context_processors.py``); its legacy ``orange-*`` values, and anything else, fall back
to ``system``. The templates add ``ion-palette-dark`` for ``dark`` on the server and follow
``prefers-color-scheme`` for ``system``.
"""

from django.http import HttpRequest

from accounts.queries import preferences_of

THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"
THEME_COOKIE = "theme"


def _account(request: HttpRequest):
    """The signed-in account, if any. An error page may render a request that never reached
    ``AuthenticationMiddleware`` (a 404 raised before it): ``request.user`` is not guaranteed."""
    user = getattr(request, "user", None)
    return user if user is not None and user.is_authenticated else None


def theme(request: HttpRequest) -> dict[str, str]:
    account = _account(request)
    if account is not None:
        return {"theme": preferences_of(account)["theme_mode"]}
    chosen = request.COOKIES.get(THEME_COOKIE)
    return {"theme": chosen if chosen in THEMES else DEFAULT_THEME}
