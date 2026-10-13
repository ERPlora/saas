"""``/features/``, ``/security/`` and ``/updates/``: the product's pages, without data.

Port of ``apps/public/product/views.py`` (origin/develop c5ca8ca), same three templates under
``public/templates/public/product/``. Only safe methods: a page that is only read answers 405 to the
rest.
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def features(request: HttpRequest) -> HttpResponse:
    return render(request, "public/product/features.html")


@require_safe
def security(request: HttpRequest) -> HttpResponse:
    return render(request, "public/product/security.html")


@require_safe
def updates(request: HttpRequest) -> HttpResponse:
    """The plain-language half of the update policy (ADR-0269); clause 7 of the terms binds."""
    return render(request, "public/product/updates.html")
