"""What every template of saas-next knows about the shell's colour mode.

``theme`` is the mode of ``@erplora/ui`` (``packages/ui/src/shell/theme.ts``): ``system``, ``light`` or
``dark``, and ``system`` when nothing says otherwise. The template pages (sign-in, errors) read it
from the ``theme`` cookie, as ERPlora/saas did (``apps/core/context_processors.py``); its legacy
``orange-*`` values, and anything else, fall back to ``system``. ``base.html`` and
``errors/base.html`` add ``ion-palette-dark`` for ``dark`` and follow ``prefers-color-scheme`` for
``system``.
"""

from django.http import HttpRequest

THEMES = ("system", "light", "dark")
DEFAULT_THEME = "system"
THEME_COOKIE = "theme"


def theme(request: HttpRequest) -> dict[str, str]:
    chosen = request.COOKIES.get(THEME_COOKIE)
    return {"theme": chosen if chosen in THEMES else DEFAULT_THEME}
