"""What every template knows about «Continue with Google».

Ported from ERPlora/saas: ``GOOGLE_OAUTH_ENABLED`` (``config/context_processors.py``) hides the
button without credentials, and ``google_next`` (``SubdomainLoginView._google_next``,
``apps/auth/users/views.py``, saas#945) is the ``next`` the button posts. The password form posts to
``action=""`` and keeps the ``?next=`` of the address bar; the Google one posts elsewhere, so it has
to carry it, or ``/hub-login/?hub=…`` would be lost on the way back from Google.
"""

from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest


def _own_path(value: str) -> str:
    """``value`` if it is a path of this site (``/…``, not ``//host`` nor ``/\\host``), else ``""``."""
    value = value.strip()
    parts = urlsplit(value)
    if not value.startswith("/") or value.startswith(("//", "/\\")) or parts.scheme or parts.netloc:
        return ""
    return value


def google_login(request: HttpRequest) -> dict:
    return {
        "GOOGLE_OAUTH_ENABLED": settings.GOOGLE_OAUTH_ENABLED,
        "google_next": _own_path(request.GET.get("next", "")),
    }
