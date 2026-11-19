"""«Open in the Hub admin», on every member row and on the «Hubs» page (``hubs.admin``,
``/admin/accounts/hubs/``, routed in ``config/urls.py``): the staff jump from ``erplora.com/admin``
to the hub's deep link ``hubs.erplora.com/admin/hub/<slug>/``. The jump starts at the Hub
(``<HUB_ADMIN_ORIGIN>/auth/login?hub=<slug>&next=/admin/hub/<slug>/``), which binds it to the browser
with its ``state`` cookie and sends it to ``/hub-login/?audience=hub-admin`` (``accounts.handoff``):
there the one-time ``hub-admin`` code is minted and auto-posted to ``HUB_ADMIN_CALLBACK_URL``. The
staff never type ``hubs.erplora.com``.
"""

from urllib.parse import urlencode

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from accounts.queries import hub_links
from accounts.services import hub_jump

OPEN_IN_HUB_ADMIN = _("Open in the Hub admin")

#: Why the jump to the Hub admin failed, by the ``?error=`` the Hub sends back to «Hubs»:
#: the codes of the Hub's ``base/auth.py`` and ``auth_views.py``, and the 400s of ``/internal/auth/redeem``
#: (``accounts/internal.py``), which the Hub forwards as they are.
JUMP_FAILED = {
    "invalid_code": _("The access to the Hub admin expired or was already used. Open it again from this page."),
    "invalid_request": _(
        "The Hub sent ERPlora a request it could not read. Try again; if it keeps happening, tell the development team."
    ),
    "hub_unauthorized": _(
        "ERPlora rejected the Hub's signed request (wrong internal key or clock out of sync). Tell the development team."
    ),
    "saas_unavailable": _("The Hub could not reach ERPlora to check the access. Try again in a moment."),
    "unknown_role": _(
        "The Hub does not accept your account's role. Only ERPlora's administrators and support can open the Hub admin."
    ),
    "not_platform_staff": _("Your account is not part of ERPlora's staff, so it cannot open the Hub admin."),
    "user_inactive": _("Your account is deactivated in the Hub admin. Ask an ERPlora administrator to reactivate it."),
}
#: Any other code: the value comes from the URL, so it is never shown.
JUMP_FAILED_UNKNOWN = _("The Hub admin could not be opened. Try again from this page.")


def open_hub_admin_url(slug: str) -> str | None:
    """The admin's jump to ``slug`` in the Hub admin, or ``None`` if ``slug`` is no hub (rows saved unvalidated).

    ``http://hubs.localhost:8000/auth/login?hub=a&next=/admin/hub/a/`` locally,
    ``https://hubs.erplora.com/auth/login?hub=a&next=/admin/hub/a/`` in production (``HUB_ADMIN_ORIGIN``).
    """
    if not hub_jump.is_hub_slug(slug):
        return None
    query = urlencode({"hub": slug, "next": hub_links.hub_admin_path(slug)}, safe="/")
    return f"{settings.HUB_ADMIN_ORIGIN}{hub_links.HUB_START_PATH}?{query}"
