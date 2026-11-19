"""The addresses of a hub seen from the SaaS: its origin, the jump into it that lands on a path of its own,
and its page in the Hub's admin."""

from urllib.parse import urlencode, urlsplit

from django.conf import settings


def hub_admin_path(slug: str) -> str:
    """The deep link of the hub ``slug`` in the Hub's admin at ``hubs.erplora.com``."""
    return f"/admin/hub/{slug}/"


def hub_origin(slug: str) -> str:
    """``scheme://host`` of the hub ``slug``, from the callback the jump posts to (``HUB_CALLBACK_TEMPLATE``)."""
    callback = urlsplit(settings.HUB_CALLBACK_TEMPLATE.format(slug=slug))
    return f"{callback.scheme}://{callback.netloc}"


#: Where a hub starts every jump into it: it binds the jump to the browser (the ``state`` cookie)
#: and only then sends it to the SaaS's ``/hub-login/`` (login CSRF; ``accounts.handoff``).
HUB_START_PATH = "/auth/login"


def local_path(value: str) -> str:
    """``value`` if it is a path on the hub (``/…``, not ``//host`` nor ``/\\host``), else ``/``."""
    parts = urlsplit(value)
    if not value.startswith("/") or value.startswith(("//", "/\\")) or parts.scheme or parts.netloc:
        return "/"
    return value


def hub_start_url(slug: str, next_path: str = "/") -> str:
    """The jump to the hub ``slug``, landing on ``next_path`` there (a non-local path lands on ``/``).

    It starts at the hub: ``http://a.localhost:8000/auth/login?next=/`` locally,
    ``https://a.erplora.com/auth/login?next=/`` in production (``hub_origin``). A link straight to
    ``/hub-login/`` would carry no ``state``, and the Hub refuses it. Also for ``hubs`` (one place).
    """
    return f"{hub_origin(slug)}{HUB_START_PATH}?{urlencode({'next': local_path(next_path)}, safe='/')}"
