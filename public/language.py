"""``POST /set-language/``: the public web's language switcher (plan §3.a).

Ported from ERPlora/saas ``landing.views.set_language`` (origin/develop c5ca8ca). It keeps the
choice only in the language cookie (``settings.LANGUAGE_COOKIE_NAME``, ``_lang``), which
``LocaleMiddleware`` reads before ``Accept-Language``. It never writes the session (Django 4+ no
longer reads it for the language) nor ``User.language``, which the panel manages.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


def _safe_next(request: HttpRequest) -> str:
    """``next``, else the referer, if it is a URL of this site; else the home page."""
    for candidate in (request.POST.get("next"), request.META.get("HTTP_REFERER")):
        if candidate and url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return candidate
    return "/"


@require_POST
def set_language(request: HttpRequest) -> HttpResponseRedirect:
    """Keep a known language in the cookie and go back; an unknown one changes nothing."""
    response = HttpResponseRedirect(_safe_next(request))
    language = request.POST.get("language", "")
    if language in dict(settings.LANGUAGES):
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )
    return response
