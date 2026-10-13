"""``/documentation/`` («coming soon», not indexed) and ``/support/`` (the support routes).

Port of ``apps/public/resources/views.py`` (origin/develop c5ca8ca). The help center (``/help/``)
lives in ``public/help.py`` with the guides it renders. The support page reads ``SUPPORT_EMAIL``
from the context processor of the public web (one source for the footer, the help and here).
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def documentation(request: HttpRequest) -> HttpResponse:
    return render(request, "public/resources/documentation.html")


@require_safe
def support(request: HttpRequest) -> HttpResponse:
    """The routes to help: the guides, the contact form and the support address."""
    return render(request, "public/resources/support.html")
