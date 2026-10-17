"""``/sitemap.xml`` of the public web (spec §8.2).

Ported from ERPlora/saas ``apps/public/landing/sitemaps.py`` (origin/develop c5ca8ca). Only pages
that exist: each batch of the port adds its own to ``StaticPagesSitemap.pages`` and the store adds
its sitemaps to ``SITEMAPS`` (``public/tests/test_sitemaps.py`` fails on an entry that does not
answer 200). IndexNow (``public/indexnow.py``) reads the same registry.

The URLs are absolute on the request's host (``PUBLIC_HOST`` outside a request), not on the
``Site`` row (allauth's, ``example.com``), and always ``https``.
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from live.context import OperationContext, Scope
from live.operations import get as get_operation

from base.operations import ANONYMOUS_KEY
from public import industries, store


class PublicSitemap(Sitemap):
    """A sitemap whose URLs live on ``host`` (the request's), else on ``settings.PUBLIC_HOST``."""

    protocol = "https"

    def __init__(self, host: str | None = None):
        self.host = host

    def get_domain(self, site=None) -> str:
        return self.host or settings.PUBLIC_HOST


class StaticPagesSitemap(PublicSitemap):
    """The public web's pages with content of their own."""

    changefreq = "monthly"
    #: ``(URL name, priority)`` of every page that exists; each batch of the port adds its own.
    pages: tuple[tuple[str, float], ...] = (
        # Product, company and the app (L3a), with the old priorities. `/app/` replaced `/bridge/`
        # (ADR-0196); the «coming soon» pages, the help and the support page are not indexed.
        ("public:features", 0.8),
        ("public:security", 0.7),
        ("public:updates", 0.5),
        ("public:app", 0.7),
        ("public:about", 0.6),
        # Legal (L3b): the old sitemap had privacy (and terms, L7) at 0.4; the declaración
        # responsable joins it (looked up by name, art. 13.2 RRSIF), the other two below.
        ("public:privacy", 0.4),
        ("public:declaracion_responsable", 0.4),
        ("public:legal_notice", 0.3),
        ("public:cookies", 0.3),
        # Industries (L4): the index; each business type's page is in IndustryDetailSitemap.
        ("public:industries_index", 0.7),
        # The pages that read Plan (L7), with the old priorities. /collaborate/ was not in the old
        # sitemap although it is indexed and in the footer: it joins at the level of /updates/.
        ("public:home", 1.0),
        ("public:pricing", 0.9),
        ("public:contact", 0.6),
        ("public:terms", 0.4),
        ("public:collaborate", 0.5),
        # The demo's door (round 2026-10-17): its GET never creates a demo, so a crawler only reads it.
        ("public:demo", 0.6),
    )

    def items(self):
        return list(self.pages)

    def location(self, item) -> str:
        return reverse(item[0])

    def priority(self, item) -> float:
        return item[1]


class StoreSitemap(PublicSitemap):
    """The store, ``/apps/`` (L6; the old ``MarketplaceSitemap``). Only with a listed app: without
    one the page is ``noindex`` (spec §5.3), and a sitemap never lists a page it hides. Its old
    addresses (``/marketplace/``, ``/solutions/``, ``/modules/``) are 301s and never listed."""

    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return ["public:store"] if store.listed_apps() else []

    def location(self, item) -> str:
        return reverse(item)


class AppDetailSitemap(PublicSitemap):
    """Each listed app's page and, when it has one, its documentation (spec §8.2), both dated by
    the ``updated_at`` of the app's Spanish ``app_doc``; an app without one goes in undated.

    One read for every app (``apps.app.sitemap``). The sitemap is also read outside a request
    (``indexnow_submit``), so the operation runs for an anonymous visitor in the default language.
    """

    changefreq = "weekly"
    priority = 0.6

    def items(self):
        visitor = OperationContext(
            scope=Scope("user", ANONYMOUS_KEY),
            actor=None,
            language=settings.LANGUAGE_CODE,
        )
        operation = get_operation("apps.app.sitemap")
        pages = []
        for app in operation(visitor, operation.input()).apps:
            pages.append(("public:store_detail", app.id, app.updated_at))
            if app.has_docs:
                pages.append(("public:store_docs", app.id, app.updated_at))
        return pages

    def location(self, item) -> str:
        name, app_id, _updated_at = item
        return reverse(name, args=[app_id])

    def lastmod(self, item) -> datetime | None:
        return item[2]


class IndustryDetailSitemap(PublicSitemap):
    """One entry per active business type: exactly what ``/industries/<slug>/`` serves (ADR-0410).

    The detail pages were published and unannounced for months. Only the active ones go in: any
    other answers 404, and announcing a 404 spends crawl budget. No ``lastmod``: the taxonomy's
    public read (``hubs.business_type.list``) does not carry the rows' dates.
    """

    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return industries.business_type_codes()

    def location(self, item) -> str:
        return reverse("public:industries_detail", kwargs={"slug": item})


#: Every sitemap of the public web, by section.
SITEMAPS: dict[str, type[PublicSitemap]] = {
    "static": StaticPagesSitemap,
    "store": StoreSitemap,
    "apps": AppDetailSitemap,
    "industries": IndustryDetailSitemap,
}


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    host = request.get_host()
    return sitemap(
        request,
        sitemaps={
            name: sitemap_class(host) for name, sitemap_class in SITEMAPS.items()
        },
    )
