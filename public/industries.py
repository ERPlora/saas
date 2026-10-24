"""``/industries/`` and ``/industries/<slug>/``: ERPlora for each business type (spec §8.1).

Ported from ERPlora/saas ``apps/public/industries/views.py`` (origin/develop c5ca8ca). What changed:

* no model: the taxonomy and the plans are read through the operations of ``hubs``
  (``hubs.sector.list``, ``hubs.business_type.list``, ``hubs.plan.list``) and the apps through
  ``apps.app.list``, with ``run_operation_sync`` as ``base/spa.py`` does (plan §3.m, spec §5.1);
* a page's apps are the listed apps of its business type's ``vertical``, in one list: what a business
  of that vertical comes with (decision 13). Without a vertical, no block (spec §5.3);
* the copy says «apps» and «catalogue» where it said «modules» and «marketplace», and every app is
  «included in every plan» (ronda 2026-10-24b, PLAN §32; before, decision 17 put the premium apps in
  the paid plans): there is no fee per app and no tier of apps;
* the taxonomy has no catch-all «Other» row any more, so every page names its business type;
* the taxonomy's icons are data: one that is not baked into the public icons paints the default.

The structure is the one the eight market references converge on (saas#1692): the buyer's literal
question as the ``<h1>``, the answer in the lead, the live price, an FAQ marked up from the same
list it renders, and links onward.

Pan-European by contract: these pages describe the sector, never one country's tax law.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_safe
from live.context import OperationContext, Scope
from live.meta import Category
from live.ninja import run_operation_sync
from live.operations import get as get_operation

from apps.schemas import AppListIn
from base.operations import ANONYMOUS_KEY
from hubs.retired_codes import current_business_type_code
from public.structured_data import faq_page, industry_software_application, json_ld
from public.templatetags import icons

logger = logging.getLogger(__name__)

#: What a sector or business type without a usable icon paints (the old page's default).
DEFAULT_ICON = "ion:business-outline"
#: How many sibling business types the detail offers.
RELATED_LIMIT = 8
#: How many app names an FAQ answer quotes.
EXAMPLES_LIMIT = 3
#: ``#rgb``, ``#rgba``, ``#rrggbb`` or ``#rrggbbaa``: the only colour that reaches a style attribute.
HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


# --- Taxonomy rows as the templates paint them ---------------------------------------------------


class _IconPicker:
    """The baked icon of a taxonomy row, or the default; one warning per page names the unbaked.

    ``{% icon %}`` refuses an unbaked icon with DEBUG, because in a template it is a mistake; a row
    of the taxonomy is data, typed in the admin, and must not take the page down.
    """

    def __init__(self) -> None:
        self.unbaked: set[str] = set()

    def __call__(self, name: str) -> str:
        if not name:
            return DEFAULT_ICON
        key = icons.icon_key(name)
        if key in icons.load_icons():
            return key
        self.unbaked.add(key)
        return DEFAULT_ICON

    def warn(self) -> None:
        if self.unbaked:
            logger.warning(
                "Taxonomy icons not baked into the public icons, painting %s: %s",
                DEFAULT_ICON,
                ", ".join(sorted(self.unbaked)),
            )


def _colour(value: str) -> str:
    return value if HEX_COLOUR.match(value or "") else ""


def _business_type_card(business_type, icon: _IconPicker) -> dict[str, Any]:
    return {
        "slug": business_type.code,
        "name": business_type.name,
        "icon": icon(business_type.icon),
        "color": _colour(business_type.color),
        "sector_name": business_type.sector.name if business_type.sector else "",
        "sector_code": business_type.sector.code if business_type.sector else "",
    }


# --- /industries/ -------------------------------------------------------------------------------


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    """Every active business type, with a filter by sector when there is more than one."""
    sectors = run_operation_sync(request, "hubs.sector.list").sectors
    business_types = run_operation_sync(
        request, "hubs.business_type.list"
    ).business_types
    type_counts = Counter(row.sector.code for row in business_types if row.sector)
    icon = _IconPicker()
    context = {
        "sectors": [
            {
                "code": sector.code,
                "name": sector.name,
                "icon": icon(sector.icon),
                "type_count": type_counts.get(sector.code, 0),
            }
            for sector in sectors
        ],
        "industries": [_business_type_card(row, icon) for row in business_types],
    }
    icon.warn()
    context["total_count"] = len(context["industries"])
    return render(request, "public/industries/list.html", context)


# --- /industries/<slug>/: the copy --------------------------------------------------------------


def _headline(subject: str) -> str:
    """H1 = the phrase the buyer types into a search box, not the taxonomy label (saas#1692)."""
    return _("POS and ERP software for your %(business)s") % {"business": subject}


def _price_sentence(plan) -> str:
    if plan.price_monthly:
        return _("Plans start at €%(price)s per month per hub, VAT excluded.") % {
            "price": f"{plan.price_monthly:.2f}"
        }
    return _("The %(plan)s plan is free and permanent, with no card.") % {
        "plan": plan.name
    }


def _lead(subject: str, app_count: int, plan) -> str:
    """The answer in the first two sentences, the part a model quotes verbatim.

    Every clause is a product fact or a live figure: the app count is dropped with an empty
    catalogue and the price with no plan on sale, since a lead that boasts «0 apps» or invents a
    price is worse than a shorter one.
    """
    lead = _(
        "ERPlora is one modular cloud app that runs your %(business)s: point of sale, "
        "catalogue and stock, customers and invoicing, from any device."
    ) % {"business": subject}
    if app_count:
        lead += " " + _(
            "You turn on only the apps you need — %(count)s in the catalogue — and they share "
            "one database, one interface and one login."
        ) % {"count": app_count}
    else:
        lead += " " + _(
            "You turn on only the apps you need, and they share one database, one interface and one login."
        )
    if plan is not None:
        lead += " " + _price_sentence(plan)
    return lead


def _examples(apps: list[dict[str, Any]]) -> str:
    return ", ".join(app["name"] for app in apps[:EXAMPLES_LIMIT])


def faq_items(subject: str, apps: list[dict[str, Any]], plan) -> list[dict[str, str]]:
    """The FAQ of one industry page, in ONE place.

    The visible accordion and the ``FAQPage`` JSON-LD both render from this list: two copies of the
    same sentence drift, and Google treats FAQ markup that does not match the page as a violation.
    Answers are built from what the catalogue publishes: app names are never invented, and the
    branch without apps says so rather than promising them.
    """
    business = {"business": subject}
    items = []

    if apps:
        fit_answer = ngettext(
            "Yes. A %(business)s comes with %(count)s app of our catalogue out of the box — "
            "%(examples)s — and it works on the same data as everything else.",
            "Yes. A %(business)s comes with %(count)s apps of our catalogue out of the box — "
            "among them %(examples)s — and they all work on the same data.",
            len(apps),
        ) % {**business, "count": len(apps), "examples": _examples(apps)}
    else:
        fit_answer = (
            _(
                "Yes. A %(business)s runs on the same core as every other business we serve — point "
                "of sale, catalogue, customers and invoicing — and you turn on the apps of the "
                "catalogue as you need them."
            )
            % business
        )
    items.append(
        {
            "key": "fit",
            "question": _("Is ERPlora a good fit for a %(business)s?") % business,
            "answer": fit_answer,
        }
    )

    if plan is not None:
        if plan.price_monthly:
            price_answer = _(
                "Plans start at €%(price)s per month per hub, VAT excluded. One subscription "
                "covers the whole business — every device and every user in it — and every plan "
                "includes all the apps; you never pay per transaction."
            ) % {"price": f"{plan.price_monthly:.2f}"}
        else:
            price_answer = _(
                "The %(plan)s plan is free and permanent, and needs no card. Paid plans raise the "
                "limits and add support; the full table is on the pricing page."
            ) % {"plan": plan.name}
        items.append(
            {
                "key": "price",
                "question": _("How much does ERPlora cost for a %(business)s?")
                % business,
                "answer": price_answer,
            }
        )

    if apps:
        start_answer = _(
            "Start with the apps a %(business)s comes with — %(examples)s — and turn on more "
            "from the catalogue when the business asks for them."
        ) % {**business, "examples": _examples(apps)}
    else:
        start_answer = _(
            "Start with the core: point of sale, catalogue, customers and invoicing come with "
            "every hub. You then turn on apps from the catalogue one at a time, so you never "
            "configure something you are not using yet."
        )
    items.append(
        {
            "key": "start",
            "question": _("Which apps do I need to start?"),
            "answer": start_answer,
        }
    )

    items.append(
        {
            "key": "devices",
            "question": _("Do I need to install anything?"),
            "answer": _(
                "No. ERPlora runs in the browser on the device you already have. There is also an "
                "installable app for the counter, which is what talks to receipt printers and the "
                "cash drawer; both see exactly the same data."
            ),
        }
    )
    items.append(
        {
            "key": "change",
            "question": _("Can I add or remove apps later?"),
            "answer": _(
                "Yes, at any time. Turning an app on takes one click and it starts working on your "
                "existing data; if you turn it off, your data stays where it is."
            ),
        }
    )
    return items


# --- /industries/<slug>/: the data --------------------------------------------------------------


def _entry_plan(request: HttpRequest):
    """The cheapest plan a visitor can sign up for (never an internal or upgrade-only one), or
    ``None``: that price is what ends up in ``Offer``, and what an answer engine repeats."""
    plans = run_operation_sync(request, "hubs.plan.list")
    return next(
        (plan for plan in plans.plans if plan.slug == plans.cheapest_slug), None
    )


def _app_card(app) -> dict[str, Any]:
    return {
        "id": app.id,
        "name": app.name,
        "summary": app.summary,
        # Cleaned with nh3 by apps.app.list (spec §8.4): safe to paint inline.
        "icon_svg": mark_safe(app.icon_svg),
        "category": Category(app.category).label if app.category else "",
        # Every plan includes all the apps (PLAN §32): the flag ``premium`` is reserved, unused today.
        "access_label": _("Included in every plan"),
    }


def _vertical_apps(request: HttpRequest, vertical: str) -> list[dict[str, Any]]:
    """The listed apps a business of ``vertical`` comes with; none without a vertical (§5.3)."""
    if not vertical:
        return []
    listed = run_operation_sync(
        request, "apps.app.list", AppListIn(vertical=vertical)
    ).apps
    return [_app_card(app) for app in listed]


@require_safe
def detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One business type: the buyer's question, its answer, the apps it comes with and an FAQ."""
    requested = slug.lower()
    # A folded code is an indexed URL: send it on for good instead of dropping it (saas#2099).
    if (current := current_business_type_code(requested)) != requested:
        return redirect("public:industries_detail", slug=current, permanent=True)

    business_types = run_operation_sync(
        request, "hubs.business_type.list"
    ).business_types
    business_type = next(
        (row for row in business_types if row.code.lower() == requested), None
    )
    if business_type is None:
        raise Http404
    if business_type.code != slug:
        return redirect(
            "public:industries_detail", slug=business_type.code, permanent=True
        )

    subject = (business_type.name or business_type.code).lower()
    apps = _vertical_apps(request, business_type.vertical)
    catalogue_size = len(run_operation_sync(request, "apps.app.list").apps)
    plan = _entry_plan(request)
    lead = _lead(subject, catalogue_size, plan)
    faq = faq_items(subject, apps, plan)

    icon = _IconPicker()
    sector = business_type.sector
    related = [
        _business_type_card(row, icon)
        for row in business_types
        if sector is not None
        and row.sector is not None
        and row.sector.code == sector.code
        and row.code != business_type.code
    ][:RELATED_LIMIT]
    icon.warn()

    base = f"https://{request.get_host()}"
    return render(
        request,
        "public/industries/detail.html",
        {
            "industry": {
                "slug": business_type.code,
                "name": business_type.name,
                "vertical": business_type.vertical,
                "subject": subject,
                "headline": _headline(subject),
                "lead": lead,
                "sector_name": sector.name if sector else "",
            },
            "apps": apps,
            "related": related,
            "faq_items": faq,
            # Serialised here, never interpolated into the template: a name carrying a quote
            # reached the old block HTML-escaped, and its offer was a hardcoded "0".
            "json_ld_application": json_ld(
                industry_software_application(
                    base,
                    name=f"ERPlora — {business_type.name}",
                    url=f"{base}{request.path}",
                    description=lead,
                    cheapest_price=plan.price_monthly if plan else None,
                )
            ),
            "json_ld_faq": json_ld(faq_page(faq)),
        },
    )


# --- The sitemap's read, outside any request ----------------------------------------------------


def business_type_codes() -> list[str]:
    """The code of every active business type: exactly what ``detail`` serves (any other is a 404).

    The sitemap is also read outside a request (``indexnow_submit``), so the operation runs for an
    anonymous visitor in the default language.
    """
    visitor = OperationContext(
        scope=Scope("user", ANONYMOUS_KEY), actor=None, language=settings.LANGUAGE_CODE
    )
    operation = get_operation("hubs.business_type.list")
    listed = operation(visitor, operation.input())
    return [row.code for row in listed.business_types]
