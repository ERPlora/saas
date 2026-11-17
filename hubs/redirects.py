"""The old panel's addresses of the businesses, for good (301), to their pages in the new panel.

Of the old ``/dashboard/*`` addresses, the businesses' ones: the old overview and lists (the panel's home is
Businesses, one list), «Create Terminal» (the dialog of Businesses, ``?create=1``) and the QR page («On your
devices», on the business's Summary). A query of the old pages (their filters) means nothing here and is dropped.
The other ``/dashboard/*`` addresses belong to their apps. The new panel lives under ``/dashboard/`` too:
``/dashboard`` and ``/dashboard/`` are Businesses, and each old address lands on its page in one hop.
"""

from django.urls import path
from django.views.generic import RedirectView

from base.navigation import BUSINESSES


def _for_good(url: str) -> RedirectView:
    return RedirectView.as_view(url=url, permanent=True, query_string=False)


urlpatterns = [
    path("dashboard", _for_good(BUSINESSES)),
    path("dashboard/", _for_good(BUSINESSES)),
    path("dashboard/hubs/", _for_good(BUSINESSES)),
    path("dashboard/hubs/active/", _for_good(BUSINESSES)),
    path("dashboard/hubs/inactive/", _for_good(BUSINESSES)),
    path("dashboard/hubs/create/", _for_good(f"{BUSINESSES}?create=1")),
    path("dashboard/hubs/<uuid:hub_id>/qr/", _for_good(f"{BUSINESSES}/%(hub_id)s/summary")),
]
