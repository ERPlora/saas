"""What every template of saas-next knows about the shell's colour mode.

``theme`` is the mode of ``@erplora/ui`` (``packages/ui/src/shell/theme.ts``): ``system``, ``light`` or
``dark``, and ``system`` when nothing says otherwise. A signed-in account gets the mode it chose in
Account → Preferences (``accounts.UserPreferences.theme_mode``, the one the panel paints), so the public
web and the sign-in pages look like the panel. Anyone else gets the ``theme`` cookie, as ERPlora/saas
did (``apps/core/context_processors.py``); its legacy ``orange-*`` values, and anything else, fall back
to ``system``. The templates add ``ion-palette-dark`` for ``dark`` on the server and follow
``prefers-color-scheme`` for ``system``.

TEMPLATES loads this module on every render, so ``accounts`` is reached lazily (``PREFERENCES_OF``,
inside the function): a top-level import of a symbol that was not on main took the whole site down in
CI (2026-10-14, hotfix cfc4adb). If it is missing, the account gets the cookie and the log says why.
"""

import logging

from django.http import HttpRequest
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"
THEME_COOKIE = "theme"
#: What the processor needs from ``accounts``: the account's preferences (``theme_mode``).
PREFERENCES_OF = "accounts.queries.preferences_of"


def _account(request: HttpRequest):
    """The signed-in account, if any. An error page may render a request that never reached
    ``AuthenticationMiddleware`` (a 404 raised before it): ``request.user`` is not guaranteed."""
    user = getattr(request, "user", None)
    return user if user is not None and user.is_authenticated else None


def _account_mode(account) -> str | None:
    """The mode ``account`` chose, or ``None`` when ``accounts`` cannot tell (missing function)."""
    try:
        preferences_of = import_string(PREFERENCES_OF)
    except ImportError:
        logger.warning("%s is missing: the account's theme falls back to the cookie", PREFERENCES_OF)
        return None
    return preferences_of(account)["theme_mode"]


def theme(request: HttpRequest) -> dict[str, str]:
    account = _account(request)
    if account is not None:
        mode = _account_mode(account)
        if mode is not None:
            return {"theme": mode}
    chosen = request.COOKIES.get(THEME_COOKIE)
    return {"theme": chosen if chosen in THEMES else DEFAULT_THEME}
