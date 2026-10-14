"""What every template of saas-next knows about the shell's colour mode.

``theme`` is the mode of ``@erplora/ui`` (``packages/ui/src/shell/theme.ts``): ``system``, ``light`` or
``dark``, and ``system`` when nothing says otherwise. It comes from the ``theme`` cookie, as ERPlora/saas
did (``apps/core/context_processors.py``); its legacy ``orange-*`` values, and anything else, fall back
to ``system``. The templates add ``ion-palette-dark`` for ``dark`` on the server and follow
``prefers-color-scheme`` for ``system``.

The account's own mode (Account → Preferences, ``accounts.UserPreferences.theme_mode``) returns here
once that model and ``accounts.queries.preferences_of`` land on main (panel batch, 2026-10-14): this
module must not import them before, because TEMPLATES loads it on every render.
"""

from django.http import HttpRequest

THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"
THEME_COOKIE = "theme"


def theme(request: HttpRequest) -> dict[str, str]:
    chosen = request.COOKIES.get(THEME_COOKIE)
    return {"theme": chosen if chosen in THEMES else DEFAULT_THEME}
