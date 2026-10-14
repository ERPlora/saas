"""``/pricing/`` and ``/pricing/<slug>/``: the plans on sale (spec §8.1), and the reading of the plans
the other public pages share (the home, the terms, ``/collaborate/``, the store's JSON-LD).

Port of ERPlora/saas ``apps/public/pricing/views.py`` (origin/develop c5ca8ca). What changed:

* no model: the plans are read through ``hubs.plan.list`` (plan §3.m) with ``run_operation_sync``,
  as ``base/spa.py`` does. The operation already lists only ``Plan.objects.public()``, drops the
  old visual separators and ends each signable plan's features with its real trial (saas#2424), so
  ``display_features`` is its ``features``;
* the trial range (saas#2414) is read from the trials of the plans on sale, the same reading as
  ``Plan.objects.signup_trial_days()``: an upgrade grants none (#809);
* the period label (``{% plan_period %}`` of the old ``money`` tags, saas#1836) is
  :func:`plan_period`, one definition for every selling screen;
* a premium app is included in the paid plans (decision 17): the FAQ no longer charges «per
  activated module»;
* the storage answer names the host: AWS (Ioan, 2026-10-13), Ireland region (Ioan, 2026-10-14).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.translation import get_language, ngettext
from django.utils.translation import gettext as _
from django.views.decorators.http import require_safe
from live.context import OperationContext, Scope
from live.ninja import run_operation_sync
from live.operations import get as get_operation

from accounts.handoff import LAUNCHER
from base.operations import ANONYMOUS_KEY
from public.structured_data import faq_page, json_ld

#: ``(shortest, longest)`` trial of the plans a visitor can sign up for; both ``None`` without one.
TrialDays = tuple[int | None, int | None]


# --- The plans on sale, for every public page ---------------------------------------------------


def plans_on_sale(request: HttpRequest | None = None):
    """``hubs.plan.list`` as the visitor of ``request`` reads it (language, session).

    Without a request (an entry point called on its own, a sitemap) the operation runs for an
    anonymous visitor in the active language.
    """
    if request is not None:
        return run_operation_sync(request, "hubs.plan.list")
    visitor = OperationContext(
        scope=Scope("user", ANONYMOUS_KEY),
        actor=None,
        language=get_language() or settings.LANGUAGE_CODE,
    )
    operation = get_operation("hubs.plan.list")
    return operation(visitor, operation.input())


def trial_days(plans) -> TrialDays:
    """The shortest and the longest trial a sign-up gets on a plan on sale (saas#2414)."""
    days = [
        plan.trial_period_days
        for plan in plans.plans
        if not plan.upgrade_only and plan.trial_period_days > 0
    ]
    return (min(days), max(days)) if days else (None, None)


def cheapest(plans):
    """The cheapest plan a visitor can sign up for (never upgrade-only nor internal), or ``None``."""
    return next(
        (plan for plan in plans.plans if plan.slug == plans.cheapest_slug), None
    )


def cheapest_paid_price(plans) -> Decimal | None:
    """The monthly price of the cheapest paid plan a visitor can sign up for, or ``None``.

    What a premium app costs (decision 17: it is included in the paid plans, never sold alone).
    """
    prices = [
        plan.price_monthly
        for plan in plans.plans
        if not plan.upgrade_only and plan.price_monthly > 0
    ]
    return min(prices) if prices else None


def plan_period(plan, interval: str = "month") -> str:
    """``/ month per hub``; the free plan, ``/ month``: one rule for every selling screen.

    The product is sold per hub (saas#1760), but «per hub» of a free plan informs of nothing, so
    what decides is having a price (saas#1836).
    """
    priced = bool(plan.price_annual if interval == "year" else plan.price_monthly)
    if interval == "year":
        return _("/ year per hub") if priced else _("/ year")
    return _("/ month per hub") if priced else _("/ month")


def _own_features(plan) -> list[str]:
    """The plan's features without the trial line the operation appends to a signable plan."""
    features = list(plan.features)
    if not plan.upgrade_only and plan.trial_period_days > 0 and features:
        features.pop()
    return features


def plan_card(plan) -> dict[str, Any]:
    """A plan as the selling screens paint it."""
    return {
        **plan.model_dump(),
        "display_features": list(plan.features),
        "own_features": _own_features(plan),
        "price_label": f"€{floatformat(plan.price_monthly, '-2')}",
        "period": plan_period(plan),
        "url": reverse("public:pricing_detail", args=[plan.slug]),
    }


# --- The copy that reads the trial --------------------------------------------------------------


def trial_note(days: TrialDays) -> str:
    """The line under the plans, with the trial the checkout grants (saas#2414)."""
    shortest, longest = days
    if not longest:
        return _("Free plan with no card required. Cancel anytime.")
    if shortest == longest:
        return ngettext(
            "Free plan with no card required; paid plans come with a %(days)d-day free trial when "
            "you create a Hub. Cancel anytime.",
            "Free plan with no card required; paid plans come with a %(days)d-day free trial when "
            "you create a Hub. Cancel anytime.",
            longest,
        ) % {"days": longest}
    return _(
        "Free plan with no card required; paid plans come with a free trial of %(min_days)d to "
        "%(max_days)d days, depending on the plan, when you create a Hub. Cancel anytime."
    ) % {"min_days": shortest, "max_days": longest}


def _trial_answer(days: TrialDays) -> str:
    """The FAQ answer on the trial, worded like the terms' §4 (saas#2409, saas#2414)."""
    shortest, longest = days
    if not longest:
        return _(
            "Not on paid plans right now, but you can start free with no card — the Free plan is "
            "free forever, so you can try it with your own data before you commit."
        )
    if shortest == longest:
        return ngettext(
            "Yes. Start free with no card — the Free plan is free forever. A paid plan chosen when "
            "creating a Hub comes with a %(days)d-day free trial using your own data, so you can "
            "be sure it fits before you commit. Moving a Hub that is already in service to a paid "
            "plan does not start a new trial.",
            "Yes. Start free with no card — the Free plan is free forever. A paid plan chosen when "
            "creating a Hub comes with a %(days)d-day free trial using your own data, so you can "
            "be sure it fits before you commit. Moving a Hub that is already in service to a paid "
            "plan does not start a new trial.",
            longest,
        ) % {"days": longest}
    return _(
        "Yes. Start free with no card — the Free plan is free forever. A paid plan chosen when "
        "creating a Hub comes with a free trial of %(min_days)d to %(max_days)d days, depending on "
        "the plan, using your own data, so you can be sure it fits before you commit. Moving a Hub "
        "that is already in service to a paid plan does not start a new trial."
    ) % {"min_days": shortest, "max_days": longest}


def faq_items(days: TrialDays | None = None) -> list[dict[str, str]]:
    """The questions on /pricing/, in ONE place.

    Both the accordion and the ``FAQPage`` JSON-LD render from this list: two copies of the same
    sentence drift, and Google treats FAQ markup that does not match the visible page as a
    violation. ``days`` is :func:`trial_days`, read here when the caller has not already done so.
    """
    if days is None:
        days = trial_days(plans_on_sale())
    return [
        {
            "key": "switch",
            "question": _("Can I switch plans at any time?"),
            "answer": _(
                "Yes. The change is immediate and the difference is prorated. There's no penalty "
                "or commitment period. Downgrading is also free — premium apps are turned off but "
                "their data is retained for 90 days."
            ),
        },
        {
            "key": "limits",
            "question": _("What happens when I reach my user or invoice limits?"),
            "answer": _(
                "There are no overage charges or surprise bills. We notify you as you "
                "approach your plan's limits, and you can track your usage anytime from "
                "your Hub control panel. When you reach a limit, just upgrade to the next "
                "plan in one click — your service is never interrupted."
            ),
        },
        {
            "key": "trial",
            "question": _("Is there a trial period?"),
            "answer": _trial_answer(days),
        },
        {
            "key": "migrate",
            "question": _("Do you migrate my data from another ERP?"),
            "answer": _(
                "Yes — our support team handles it for you. Just get in touch with your "
                "current ERP and we'll plan and run the migration together, so your data "
                "comes across without the hassle."
            ),
        },
        {
            "key": "storage",
            "question": _("Where is my data stored?"),
            "answer": _(
                "Entirely within the European Union: on Amazon Web Services, in its Ireland "
                "region (eu-west-1), on GDPR-compliant infrastructure. Your data never leaves "
                "the EU."
            ),
        },
        {
            "key": "pricing",
            "question": _("Do you charge per app or per usage?"),
            "answer": _(
                "Neither. You pay one fixed price per hub, the price of its plan. The free apps "
                "come with every plan and the premium apps are included in the paid plans, so "
                "turning an app on or off never changes your bill. We don't charge by usage — no "
                "per-transaction or metered fees — so your bill stays predictable every month."
            ),
        },
        {
            # The long detail goes here and not on the card (saas#1835).
            "key": "vat",
            "question": _("Is VAT included in these prices?"),
            "answer": _(
                "No — every price on this page is net. The VAT that applies to you is "
                "worked out at checkout from the tax ID you enter, and you see the exact "
                "amount before you pay. A Spanish NIF/CIF/NIE pays 21%. A company in "
                "another EU member state with a VAT number we validate against VIES pays "
                "0% under the reverse charge, and accounts for the tax itself. The Canary "
                "Islands, Ceuta and Melilla, and customers outside the EU are outside the "
                "scope of Spanish VAT, which is not the same as a 0% rate."
            ),
        },
    ]


# --- The pages ----------------------------------------------------------------------------------


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    """Every plan on sale: the signable ones as cards, the upgrade-only ones apart (saas#809)."""
    plans = plans_on_sale(request)
    days = trial_days(plans)
    faq = faq_items(days)
    cards = [plan_card(plan) for plan in plans.plans]
    plans_main = [card for card in cards if not card["upgrade_only"]]
    entry = cheapest(plans)
    return render(
        request,
        "public/pricing/index.html",
        {
            "plans_main": plans_main,
            "plans_pro": [card for card in cards if card["upgrade_only"]],
            "cheapest_plan": plan_card(entry) if entry else None,
            "trial_note": trial_note(days),
            "faq_items": faq,
            "json_ld_faq": json_ld(faq_page(faq)),
        },
    )


@require_safe
def detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One plan on sale; an internal, retired or unknown plan answers 404 (saas#1950)."""
    cards = [plan_card(plan) for plan in plans_on_sale(request).plans]
    plan = next((card for card in cards if card["slug"] == slug), None)
    if plan is None:
        raise Http404
    return render(
        request,
        "public/pricing/detail.html",
        {
            "plan": plan,
            "other_plans": [card for card in cards if card["slug"] != slug],
            "launcher": LAUNCHER,
        },
    )
