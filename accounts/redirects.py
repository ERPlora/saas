"""The old panel's addresses of the account, for good (301), to their tabs of Account (ACCOUNTS-F30).

PLAN-SAAS §1 («Redirecciones de URLs viejas … SE PORTAN (301): … ``/dashboard/*``»), the account's part: the profile,
its sessions and the preferences. The installed app (``ERPlora/app``, copied as it is) opens the account on its own at
``/dashboard/profile/?surface=account``, so the query is kept: it is what paints the account surface (``base.surface``).
The businesses' old addresses are ``hubs.redirects``'.
"""

from django.urls import path
from django.views.generic import RedirectView


def _for_good(url: str) -> RedirectView:
    return RedirectView.as_view(url=url, permanent=True, query_string=True)


urlpatterns = [
    path("dashboard/profile/", _for_good("/account/profile")),
    path("dashboard/profile/sessions/", _for_good("/account/security")),
    path("dashboard/settings/", _for_good("/account/preferences")),
]
