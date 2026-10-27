"""The old panel's addresses of the account, for good (301), to their tabs of Account (ACCOUNTS-F30).

PLAN-SAAS §1 («Redirecciones de URLs viejas … SE PORTAN (301): … ``/dashboard/*``»), the account's part: the profile,
its sessions and the preferences. The installed app (``ERPlora/app``, copied as it is) opens the account on its own at
``/dashboard/profile/?surface=account``, so the query is kept: it is what paints the account surface (``base.surface``).
The businesses' old addresses are ``hubs.redirects``'. Account lives under ``/dashboard/`` with the rest of the panel
(FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX): each lands there in one hop.
"""

from django.urls import path
from django.views.generic import RedirectView

from base.navigation import ACCOUNT


def _for_good(url: str) -> RedirectView:
    return RedirectView.as_view(url=url, permanent=True, query_string=True)


urlpatterns = [
    path("dashboard/profile/", _for_good(f"{ACCOUNT}/profile")),
    path("dashboard/profile/sessions/", _for_good(f"{ACCOUNT}/security")),
    path("dashboard/settings/", _for_good(f"{ACCOUNT}/preferences")),
]
