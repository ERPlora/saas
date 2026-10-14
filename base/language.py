"""On the panel, a signed-in account speaks its own language: ``User.language`` wins over the ``_lang`` cookie.

``LocaleMiddleware`` reads the language cookie (the public web's switcher, ``public/language.py``), then
``Accept-Language``. The panel speaks the account's own language instead (Cuenta → Preferencias,
``accounts.preferences.update``), as Stripe's, Shopify's and Google's dashboards do: one choice, every
device. The panel is the SPA's pages (``base.spa``), ``/api/`` (the live stream included) and allauth's
headless API; without an account the cookie still decides, and the public web keeps its switcher's
cookie, signed in or not. A live stream re-reads the account before each run (``base.operations``).
"""

from django.conf import settings
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

from base.spa import spa

#: The panel's paths besides the SPA's pages: the API (and its live stream) and allauth's headless API.
PANEL_PREFIXES = ("/api/", "/_allauth/")


def account_language(request, view_func) -> str | None:
    """The language of the account behind ``request`` when it reaches the panel (``view_func``), else ``None``."""
    if view_func is not spa and not request.path.startswith(PANEL_PREFIXES):
        return None
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    language = getattr(user, "language", "")
    return language if language in dict(settings.LANGUAGES) else None


class AccountLanguageMiddleware(MiddlewareMixin):
    """After ``AuthenticationMiddleware``: once the view is known, the account's language replaces the one
    ``LocaleMiddleware`` chose (its response hook then names it in ``Content-Language``)."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        language = account_language(request, view_func)
        if language is not None:
            translation.activate(language)
            request.LANGUAGE_CODE = language
        return None
