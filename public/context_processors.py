"""What every template of the public web knows.

Ported from ERPlora/saas ``config/context_processors.py`` (``site_settings``, origin/develop
c5ca8ca), only its public part: the analytics ids, the support address, chat and reply time, and the two
flags the analytics partial reads.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

from public.crawlers import is_private

#: Pages that carry passwords, one-time codes or keys: allauth's headless API and the SPA's sign-in
#: pages (``accounts/frontend/routes.ts``), each with the pages under it: ``/launch`` (the sign-in of the
#: entrance), ``/login`` (only a redirect to it now, and ``/login/error``), ``/password/reset`` (and its
#: mailed key page), ``/2fa`` (the settings, with the secret and recovery codes, and
#: ``/2fa/authenticate``). ``/accounts/`` only redirects since ``HEADLESS_ONLY`` and the sign-in also
#: signs up, so neither it nor a ``/signup`` is here.
CREDENTIALS_PREFIXES = ("/_allauth/",)
CREDENTIALS_SPA_PAGES = (
    "/launch",
    "/login",
    "/verify-email",
    "/password/reset",
    "/2fa",
    "/reauthenticate",
)


#: How soon support answers, in business hours: the contact form, the contact page and the home state this number
#: and no other (PUBLIC-G41). The address is ``SUPPORT_EMAIL`` (settings).
SUPPORT_REPLY_HOURS = 4
#: The support chat (WhatsApp), the only place the web writes it (PUBLIC-G41).
SUPPORT_WHATSAPP_URL = "https://wa.me/34643759040"


#: The surfaces of the installed app (``surface.ts`` of packages/ui): a public page opened from one of them, with
#: ``?surface=<surface>`` (the app's sign-in puts it on its links), is shown in app mode (PUBLIC-F26): the text and
#: a way back, nothing of the web around it. Kept in the session, so the texts it links stay so; ``web`` ends it.
APP_SURFACES = ("desktop", "mobile", "account")
SURFACE_PARAM = "surface"
SURFACE_SESSION_KEY = "public.surface"


def app_surface(request: HttpRequest) -> str | None:
    """The app's surface the request (or its session) opened the public web from, else ``None`` (the web)."""
    session = getattr(request, "session", None)
    if session is None:
        return None
    asked = request.GET.get(SURFACE_PARAM)
    if asked in APP_SURFACES:
        session[SURFACE_SESSION_KEY] = asked
    elif asked == "web":
        session.pop(SURFACE_SESSION_KEY, None)
    surface = session.get(SURFACE_SESSION_KEY)
    return surface if surface in APP_SURFACES else None


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
        # The visible support contact (footer, help, landing): one source each (PUBLIC-G41).
        "SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        "SUPPORT_REPLY_HOURS": SUPPORT_REPLY_HOURS,
        "SUPPORT_WHATSAPP_URL": SUPPORT_WHATSAPP_URL,
        # Opened from the installed app: no menu, footer, cookie notice nor measurement, and a way back (PUBLIC-F26).
        "app_surface": app_surface(request),
        # Clarity records the screen: only an anonymous visitor on the public half. The boundary
        # is the session, not the URL, so a private page added later is covered (saas#958).
        "is_public_page": not _is_authenticated(request) and not is_private(request),
        # Passwords and one-time codes: no analytics there, whatever the consent (saas#958).
        "is_credentials_page": _is_credentials_page(path),
    }
