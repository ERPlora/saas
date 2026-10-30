"""Read operations of apps: the public catalog of the Hub's apps (spec §5.1–§5.3).

No permission: the store is public and a visitor reads it before any account exists. The texts
are in the caller's language (``ctx.language``, which a live stream carries outside the request):
``es`` reads the ``_es`` columns, any other the ``_en`` ones. The panel's SPA calls them through
their ninja routes and the views of ``public/`` with ``run_operation_sync``; no ``live.py``, since
the catalog only changes with a release of the Hub, which notifies nobody (spec §12). No cache of
the list (tens of rows in the SaaS's own database); only the rendered documentation is cached.

``known_verticals()`` is no operation: it is what ``BusinessType.clean()`` (hubs) checks a vertical
against (spec §5.4).
"""

import logging
import unicodedata
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import OuterRef, Q, Subquery
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound
from live.markdown import render_markdown
from live.meta import Category
from live.operations import AI, INTERNAL, operation

from apps.icons import FALLBACK_ICON, FALLBACK_ICON_SVG, clean_icon_svg
from apps.models import App, AppDoc
from apps.schemas import (
    AppByIdIn,
    AppDocListIn,
    AppDocListOut,
    AppDocOut,
    AppListIn,
    AppListOut,
    AppOut,
    AppSitemapIn,
    AppSitemapOut,
)

logger = logging.getLogger(__name__)

#: The WORKBOOK's language, the one every app documents first (spec §7).
SOURCE_LANGUAGE = "es"
#: How long a rendered documentation is kept; a new document changes its hash, and so its key.
DOC_CACHE_SECONDS = 60 * 60 * 24
#: The version of what ``render_markdown`` produces, in the key: bumped when the renderer changes
#: what it lets through (2: live 387d04f, stricter image paths), so HTML rendered before a deploy
#: is never served after it.
DOC_RENDER_VERSION = 2
#: The sections of the store, in the order of live.meta's Category; an unknown one goes last.
CATEGORY_ORDER = {value: position for position, value in enumerate(Category.values)}


def _language(ctx: OperationContext) -> str:
    """``es`` for any Spanish (``es``, ``es-ES``), ``en`` for any other language."""
    return "es" if (ctx.language or "").split("-")[0].lower() == "es" else "en"


def _text(app: App, field: str, language: str) -> str:
    return getattr(app, f"{field}_{language}")


def _known_category(app: App) -> str | None:
    return app.category if app.category in CATEGORY_ORDER else None


def _warn_unknown_categories(apps: list[App]) -> None:
    """One warning per call: the Hub went ahead of this SaaS's live.meta (spec §5.3)."""
    unknown = sorted(
        f"{app.id} ({app.category})" for app in apps if _known_category(app) is None
    )
    if unknown:
        logger.warning(
            "Apps with a category this SaaS does not know yet, listed without a section: %s",
            ", ".join(unknown),
        )


def _icon_svg(app: App) -> str:
    cleaned = clean_icon_svg(app.icon_svg)
    if cleaned is None:
        logger.warning(
            "App %s: icon_svg is empty or not a usable SVG once cleaned; painting %s",
            app.id,
            FALLBACK_ICON,
        )
        return FALLBACK_ICON_SVG
    return cleaned


def _sort_name(name: str) -> str:
    """Case- and accent-insensitive: «órdenes» goes between «Facturas» and «Pagos»."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).casefold()


def _card(app: App, language: str) -> dict[str, Any]:
    return {
        "id": app.id,
        "name": _text(app, "name", language),
        "summary": _text(app, "summary", language),
        "icon_svg": _icon_svg(app),
        "category": _known_category(app),
        "premium": app.premium,
        "verticals": list(app.verticals),
    }


def _listed_app(app_id: str) -> App:
    app = App.objects.filter(pk=app_id, listed=True).first()
    if app is None:
        raise NotFound(
            gettext("There is no app “%(id)s” in the catalog.") % {"id": app_id},
            code="apps.app_not_found",
        )
    return app


def _served_doc(app: App, language: str) -> AppDoc | None:
    """The document to serve in ``language``: its own, else the Spanish one (spec §5.2). An empty
    markdown is a language that no longer exists (spec §4.2), never an empty page."""
    docs = {doc.lang: doc for doc in app.docs.exclude(markdown="")}
    return docs.get(language) or docs.get(SOURCE_LANGUAGE)


@operation(
    "apps.app.list",
    kind="query",
    permission=None,
    input=AppListIn,
    output=AppListOut,
    ai=AI(description="The apps of ERPlora's catalogue for businesses, by text, category, premium or sector."),
)
def app_list(ctx: OperationContext, data: AppListIn) -> dict[str, Any]:
    """The listed apps that match, by section (Category) and then by name in the language."""
    language = _language(ctx)
    apps = App.objects.filter(listed=True)
    if data.q:
        apps = apps.filter(
            Q(**{f"name_{language}__icontains": data.q})
            | Q(**{f"summary_{language}__icontains": data.q})
        )
    if data.category is not None:
        apps = apps.filter(category=data.category)
    if data.premium is not None:
        apps = apps.filter(premium=data.premium)
    if data.vertical:
        apps = apps.filter(verticals__contains=[data.vertical])
    rows = list(apps)
    _warn_unknown_categories(rows)
    rows.sort(
        key=lambda app: (
            CATEGORY_ORDER.get(app.category, len(CATEGORY_ORDER)),
            _sort_name(_text(app, "name", language)),
        )
    )
    return {"apps": [_card(app, language) for app in rows]}


@operation(
    "apps.app.get",
    kind="query",
    permission=None,
    input=AppByIdIn,
    output=AppOut,
    ai=AI(description="One app of the catalogue: what it does, the apps it requires and whether it has documentation."),
)
def app_get(ctx: OperationContext, data: AppByIdIn) -> dict[str, Any]:
    """A listed app's page: its card, description, required apps and whether it has documentation."""
    language = _language(ctx)
    app = _listed_app(data.id)
    _warn_unknown_categories([app])
    known = {
        required.id: required for required in App.objects.filter(pk__in=app.requires)
    }
    requires = [
        {
            "id": required_id,
            # An id the catalog does not know (the Hub checks its graph, so only a broken row) is
            # shown as it is and never linked.
            "name": _text(known[required_id], "name", language)
            if required_id in known
            else required_id,
            "listed": required_id in known and known[required_id].listed,
        }
        for required_id in app.requires
    ]
    return {
        **_card(app, language),
        "description": _text(app, "description", language),
        "requires": requires,
        "has_docs": _served_doc(app, language) is not None,
    }


@operation(
    "apps.app.doc",
    kind="query",
    permission=None,
    input=AppByIdIn,
    output=AppDocOut,
    ai=AI(description="The user documentation of one app of the catalogue, in the person's language."),
)
def app_doc(ctx: OperationContext, data: AppByIdIn) -> dict[str, Any]:
    """A listed app's user documentation as safe HTML, in the language or else in Spanish."""
    language = _language(ctx)
    app = _listed_app(data.id)
    doc = _served_doc(app, language)
    if doc is None:
        raise NotFound(
            gettext("The app “%(id)s” has no documentation yet.") % {"id": app.id},
            code="apps.doc_not_found",
        )
    key = f"apps:doc:v{DOC_RENDER_VERSION}:{app.id}:{doc.lang}:{doc.source_hash}"
    html = cache.get(key)
    if html is None:
        html = render_markdown(
            doc.markdown,
            image_base=f"{settings.HUB_STATIC_BASE_URL}catalog/{app.id}/img/",
        )
        cache.set(key, html, DOC_CACHE_SECONDS)
    return {"html": html, "lang": doc.lang, "fallback": doc.lang != language}


@operation(
    "apps.doc.list",
    kind="query",
    permission=None,
    input=AppDocListIn,
    output=AppDocListOut,
    ai=INTERNAL,  # index
)
def doc_list(ctx: OperationContext, data: AppDocListIn) -> dict[str, Any]:
    """Every listed app's user documentation, as written, in each language it has (an empty one is a language
    that no longer exists, spec §4.2): what the panel's assistant indexes (``assistant.knowledge``). By app, then
    language; one read."""
    docs = (
        AppDoc.objects.filter(app__listed=True)
        .exclude(markdown="")
        .select_related("app")
        .order_by("app_id", "lang")
    )
    return {
        "docs": [
            {"app": doc.app_id, "name": _text(doc.app, "name", doc.lang), "lang": doc.lang, "markdown": doc.markdown}
            for doc in docs
        ]
    }


@operation(
    "apps.app.sitemap",
    kind="query",
    permission=None,
    input=AppSitemapIn,
    output=AppSitemapOut,
    ai=INTERNAL,  # sitemap
)
def app_sitemap(ctx: OperationContext, data: AppSitemapIn) -> dict[str, Any]:
    """Every listed app's page for ``/sitemap.xml`` (spec §8.2), by id, in one read.

    Only the Spanish document counts: it is the source every language falls back to, so only it
    makes ``docs/`` answer in every language, and its ``updated_at`` is the pages' ``lastmod``.
    """
    spanish_doc = AppDoc.objects.filter(
        app=OuterRef("pk"), lang=SOURCE_LANGUAGE
    ).exclude(markdown="")
    rows = (
        App.objects.filter(listed=True)
        .annotate(doc_updated_at=Subquery(spanish_doc.values("updated_at")[:1]))
        .order_by("id")
        .values_list("id", "doc_updated_at")
    )
    return {
        "apps": [
            {"id": app_id, "has_docs": updated_at is not None, "updated_at": updated_at}
            for app_id, updated_at in rows
        ]
    }


def cards_of(app_ids: list[str], language: str) -> dict[str, dict[str, Any]]:
    """The card of each app of ``app_ids`` the catalog knows, listed or retired, by id: for another app of the
    SaaS that must name an app it still sells or bills (billing's Store names a retired app's module a business
    still pays, saas#2589). ``language`` as a request's: ``es`` for any Spanish, ``en`` otherwise."""
    language = "es" if (language or "").split("-")[0].lower() == "es" else "en"
    return {app.id: _card(app, language) for app in App.objects.filter(pk__in=app_ids)}


def known_verticals() -> list[str]:
    """Every vertical an app of the catalog declares, sorted; retired apps too, since their rows
    still exist. ``BusinessType.clean()`` refuses a vertical outside it (spec §5.4)."""
    verticals: set[str] = set()
    for declared in App.objects.values_list("verticals", flat=True):
        verticals.update(declared)
    return sorted(verticals)
