"""The old panel's addresses of the businesses, for good (301), to their pages in the new panel.

PLAN-SAAS §1 («Redirecciones de URLs viejas … SE PORTAN (301): … ``/dashboard/*``»), the part of the businesses:
the old overview and lists (round 17, §3.6: the panel's home is Businesses, one list), «Create Terminal» (the
dialog of Businesses, ``?create=1``) and the QR page («On your devices», on the business's Summary). A query of the
old pages (their filters) means nothing here and is dropped. The other ``/dashboard/*`` addresses belong to their
apps.
"""

from django.urls import path
from django.views.generic import RedirectView


def _for_good(url: str) -> RedirectView:
    return RedirectView.as_view(url=url, permanent=True, query_string=False)


urlpatterns = [
    path("dashboard/", _for_good("/businesses")),
    path("dashboard/hubs/", _for_good("/businesses")),
    path("dashboard/hubs/active/", _for_good("/businesses")),
    path("dashboard/hubs/inactive/", _for_good("/businesses")),
    path("dashboard/hubs/create/", _for_good("/businesses?create=1")),
    path("dashboard/hubs/<uuid:hub_id>/qr/", _for_good("/businesses/%(hub_id)s/summary")),
]
