"""The app store of the public web: ``/apps/``, ``/apps/<id>/`` and ``/apps/<id>/docs/`` (spec §5,
§8.1 and decisions 17 and 19), and the 301s of the marketplace's old addresses.

Port of ``apps/public/modules`` (origin/develop c5ca8ca) reduced to what the catalog holds: the Hub
registers its apps in ``shared.app`` and these pages read them through the operations of apps
(``apps.app.list``, ``apps.app.get``, ``apps.app.doc``) with the request's context, the same ones
the ninja routes run. No view touches the ORM (``public/tests/test_store.py`` checks the imports).
Each tab is its own URL (the old page swapped htmx fragments): «Overview» at ``/apps/<id>/`` and
«Documentation» at ``/apps/<id>/docs/``. No reviews, changelog, tiers nor payment (spec §8.1).

Every plan includes all the apps (ronda 2026-10-24b, PLAN §32; before, decision 17 split them into
free and premium): every card and page says «Included in every plan», there is no «Premium» badge nor
access filter, and every app is offered at ``0``. The ``premium`` flag stays reserved, unused today,
for the panel's Store (PLAN-SAAS §9); the public web does not read it.

The sitemap's ``/apps/`` entry (``public/sitemaps.py``; the app pages read ``apps.app.sitemap``)
and ``llms.txt`` (``public/seo.py``) read the listed apps through :func:`listed_apps`, outside any
visitor's language.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponsePermanentRedirect,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from django.views.decorators.http import require_safe
from live.context import OperationContext, Scope
from live.errors import NotFound
from live.meta import Category
from live.ninja import run_operation_sync
from live.operations import get as get_operation

from accounts.handoff import LAUNCHER
from apps.schemas import AppByIdIn, AppListIn, AppOut, AppSummaryOut
from base.operations import ANONYMOUS_KEY
from hubs.schemas import BusinessTypeListIn
from public import structured_data

#: The operations' «not here» codes: an unknown or unlisted app, an app without documentation.
NOT_FOUND_CODES = frozenset({"apps.app_not_found", "apps.doc_not_found"})
#: The filters of the list, in the order their query string is written.
FILTERS = ("q", "category")


# --- Reading the catalog ------------------------------------------------------------------------


def _run(request: HttpRequest, name: str, data: Any) -> Any:
    """The operation for the visitor of ``request``; ``apps.*``'s 404s become the site's 404."""
    try:
        return run_operation_sync(request, name, data)
    except NotFound as missing:
        if missing.code in NOT_FOUND_CODES:
            raise Http404(missing.message) from missing
        raise


def listed_apps() -> list[AppSummaryOut]:
    """The listed apps, for the sitemap and ``llms.txt``: an anonymous reader in English.

    They run outside a visitor's request (IndexNow reads the sitemap from a command) and are
    machine-facing English files, so the context is built here instead of from a request.
    """
    return get_operation("apps.app.list")(_reader(), AppListIn()).apps


def _reader() -> OperationContext:
    return OperationContext(
        scope=Scope("user", ANONYMOUS_KEY), actor=None, language="en"
    )


def _category_label(category: str | None) -> str | None:
    """The section's name in the active language (live's catalog), or none for an unknown one."""
    return Category(category).label if category in Category.values else None


def _card(app: AppSummaryOut) -> dict[str, Any]:
    """What a card and the page header paint. ``icon_svg`` comes cleaned with nh3 by the operation
    (spec §8.4), so it is painted inline as it is."""
    return {
        "id": app.id,
        "name": app.name,
        "summary": app.summary,
        "icon_svg": mark_safe(app.icon_svg),  # noqa: S308 - cleaned by apps.queries (nh3)
        "category_label": _category_label(app.category),
        # Every plan includes all the apps (PLAN §32): no app is sold on its own (ADR-0474).
        "access_label": gettext("Included in every plan"),
        "href": reverse("public:store_detail", args=[app.id]),
    }


# --- /apps/ -------------------------------------------------------------------------------------


def _store_url(**params: Any) -> str:
    """``/apps/`` with the given filters, in a stable order, dropping the empty ones."""
    query = urlencode(
        [(name, params[name]) for name in FILTERS if params.get(name) not in (None, "")]
    )
    return f"{reverse('public:store')}?{query}" if query else reverse("public:store")


def _groups(apps: list[AppSummaryOut]) -> list[dict[str, Any]]:
    """The apps by section, in the order of ``live.meta.Category`` (the operation's order). Apps of
    a category this SaaS does not know yet go last, in a group without a title (spec §5.3)."""
    sections: dict[str, list[dict[str, Any]]] = {}
    unsorted: list[dict[str, Any]] = []
    for app in apps:
        if app.category in Category.values:
            sections.setdefault(app.category, []).append(_card(app))
        else:
            unsorted.append(_card(app))
    groups = [
        {"id": category, "label": _category_label(category), "apps": cards}
        for category, cards in sections.items()
    ]
    if unsorted:
        groups.append({"id": None, "label": None, "apps": unsorted})
    return groups


@require_safe
def store(request: HttpRequest) -> HttpResponse:
    """``/apps/``: the listed apps by section, with ``?q=`` and ``?category=``.

    A filter it does not understand is ignored (``AppListIn``), and so is the old ``?premium=``: the
    store sells no tier of apps (PLAN §32). Three states (spec §5.3): the
    apps; no listed app at all (a new database), said so and kept out of the index; or filters
    that match nothing, with a way to clear them.
    """
    filters = AppListIn(q=request.GET.get("q"), category=request.GET.get("category"))
    q, category = filters.q, filters.category
    category = category.value if category is not None else None
    every_app = _run(request, "apps.app.list", AppListIn()).apps
    filtered = q is not None or category is not None
    apps = _run(request, "apps.app.list", filters).apps if filtered else every_app
    current = {"q": q, "category": category}

    counts: dict[str, int] = {}
    for app in every_app:
        if app.category in Category.values:
            counts[app.category] = counts.get(app.category, 0) + 1
    category_chips = [
        {
            "label": gettext("All"),
            "count": len(every_app),
            "href": _store_url(**{**current, "category": None}),
            "active": category is None,
        },
        *(
            {
                "label": choice.label,
                "count": counts[choice.value],
                "href": _store_url(**{**current, "category": choice.value}),
                "active": category == choice.value,
            }
            for choice in Category
            if choice.value in counts
        ),
    ]
    return render(
        request,
        "public/store/list.html",
        {
            "groups": _groups(apps),
            "total": len(every_app),
            "catalog_empty": not every_app,
            "filtered": filtered,
            "q": q or "",
            "category": category,
            "category_chips": category_chips,
        },
    )


# --- /apps/<id>/ and /apps/<id>/docs/ -------------------------------------------------------------


def _business_types_for(request: HttpRequest, verticals: list[str]) -> list[str]:
    """The names of the business types an app is built for: those whose ``vertical`` it declares.

    A vertical is an id (``hair_salon``), not a name a visitor reads; the taxonomy of hubs names it
    in both languages. A vertical no business type carries yet has nothing to show.
    """
    if not verticals:
        return []
    business_types = _run(
        request, "hubs.business_type.list", BusinessTypeListIn()
    ).business_types
    names: list[str] = []
    for business_type in business_types:
        if business_type.vertical in verticals and business_type.name not in names:
            names.append(business_type.name)
    return names


def _required(request: HttpRequest, app: AppOut) -> list[dict[str, Any]]:
    """The apps ``app`` requires: a listed one links its page with its icon and access."""
    if not app.requires:
        return []
    cards = {}
    if any(required.listed for required in app.requires):
        cards = {
            card.id: card for card in _run(request, "apps.app.list", AppListIn()).apps
        }
    rows = []
    for required in app.requires:
        card = cards.get(required.id) if required.listed else None
        rows.append(
            {
                "name": required.name,
                **({"card": _card(card)} if card is not None else {}),
            }
        )
    return rows


def _app_context(app: AppOut, tab: str) -> dict[str, Any]:
    """What both tabs share: the app's header and the tabs."""
    return {
        "app": {**_card(app), "description": app.description},
        "has_docs": app.has_docs,
        "tab": tab,
        "launcher": LAUNCHER,
    }


@require_safe
def store_detail(request: HttpRequest, app_id: str) -> HttpResponse:
    """``/apps/<id>/``, the «Overview» tab: the app, what it needs and how to get it."""
    app = _run(request, "apps.app.get", AppByIdIn(id=app_id))
    base = f"https://{request.get_host()}"
    url = f"{base}{reverse('public:store_detail', args=[app.id])}"
    json_ld = structured_data.app_software_application(
        name=app.name, description=app.description or app.summary, url=url
    )
    return render(
        request,
        "public/store/detail.html",
        {
            **_app_context(app, "overview"),
            "built_for": _business_types_for(request, app.verticals),
            "required": _required(request, app),
            "json_ld": structured_data.json_ld(json_ld),
        },
    )


@require_safe
def store_docs(request: HttpRequest, app_id: str) -> HttpResponse:
    """``/apps/<id>/docs/``, the «Documentation» tab: the WORKBOOK's user part (spec §5.2).

    In English without an English document, the Spanish one is served with a notice and
    ``lang="es"`` on its container (spec §5.3). An app without documentation is a 404.
    """
    app = _run(request, "apps.app.get", AppByIdIn(id=app_id))
    doc = _run(request, "apps.app.doc", AppByIdIn(id=app_id))
    return render(
        request,
        "public/store/docs.html",
        {
            **_app_context(app, "docs"),
            # Rendered and cleaned with nh3 by live.markdown (apps.app.doc).
            "doc_html": mark_safe(doc.html),  # noqa: S308
            "doc_lang": doc.lang,
            "doc_fallback": doc.fallback,
        },
    )


# --- The old addresses (decision 19) ------------------------------------------------------------


def _with_query(request: HttpRequest, path: str) -> str:
    query = request.META.get("QUERY_STRING", "")
    return f"{path}?{query}" if query else path


@require_safe
def marketplace(request: HttpRequest, app_id: str | None = None) -> HttpResponse:
    """``/marketplace/`` and ``/marketplace/<id>/``, already indexed: 301 to the store, keeping the
    query (its filters still mean the same). An old slug that is no app's id ends in the 404."""
    path = (
        reverse("public:store")
        if app_id is None
        else reverse("public:store_detail", args=[app_id])
    )
    return HttpResponsePermanentRedirect(_with_query(request, path))


@require_safe
def to_store(request: HttpRequest, slug: str | None = None) -> HttpResponse:
    """``/solutions/``, ``/solutions/<slug>/`` and ``/modules/`` are gone (spec §8.3): 301 to the
    store, without their query (``?unit=`` filtered functional units, which no longer exist)."""
    return HttpResponsePermanentRedirect(reverse("public:store"))
