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
* the storage answer names the host: AWS (Ioan, 2026-10-13), Ireland region (Ioan, 2026-10-14);
* three plans on sale at sign-up (Ioan, 2026-10-15): the page lists only the plans a visitor can sign up for
  (an ``upgrade_only`` row — Pro, Enterprise and Max, kept for the Store's upgrades — stays off the page and
  answers 404 on its detail), and above them it offers **dedicated infrastructure**, from
  :data:`DEDICATED_FROM` a month, agreed by contact — a band, a row of the table and a FAQ entry, never
  a checkout;
* the assistant and WhatsApp messages a month each plan includes (PLAN-SAAS §3.6, 2026-10-15) are a line of
  every card and a column of the table, in plain words (:func:`messages_a_month`); a quota of 0 is none.
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

#: Dedicated infrastructure starts here, net, a month (Ioan, 2026-10-15). A quote, not a plan: there is no
#: row, no checkout and no Stripe price behind it, so this is the one place the figure lives.
DEDICATED_FROM = Decimal("400")


def dedicated_price_label() -> str:
    """``€400``, painted as the plan cards paint their monthly price."""
    return f"€{floatformat(DEDICATED_FROM, '-2')}"


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


def free_plan(plans):
    """The Free plan on sale (0 €), the one every business is born on (``hubs.queries.free_plan``), or ``None``."""
    return next((plan for plan in plans.plans if not plan.price_monthly), None)


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


def annual_months_free(plan) -> int:
    """The months a year paid at once saves against twelve monthly payments, rounded down (0 = none).

    Worked out from the two prices, never typed: edit the annual price and the saving follows
    (SAAS_PUBLIC-F56). Rounded down so the page never promises more than the checkout gives.
    """
    if not plan.price_monthly or not plan.price_annual:
        return 0
    return max(int(Decimal(12) - plan.price_annual / plan.price_monthly), 0)


def common_months_free(plans) -> int:
    """The saving every paid plan a visitor can sign up for gives when paid by the year, if they all give the
    same one; else 0, and the hero promises nothing it would have to qualify."""
    savings = {
        annual_months_free(plan)
        for plan in plans.plans
        if not plan.upgrade_only and plan.price_monthly > 0
    }
    return savings.pop() if len(savings) == 1 else 0


def _has_trial_line(plan) -> bool:
    """Whether the operation ended the plan's features with its trial (a signable plan with one)."""
    return bool(not plan.upgrade_only and plan.trial_period_days > 0 and plan.features)


def messages_a_month(count: int) -> str:
    """``300 messages a month``; ``""`` for 0, which is «none» (PLAN-SAAS §3.6), never «unlimited»."""
    if count <= 0:
        return ""
    return ngettext("%(count)d message a month", "%(count)d messages a month", count) % {"count": count}


def _message_lines(assistant: str, whatsapp: str) -> list[str]:
    """The card lines of the monthly messages the plan includes; none for a quota of 0."""
    lines = []
    if assistant:
        lines.append(_("AI assistant: %(messages)s") % {"messages": assistant})
    if whatsapp:
        lines.append(_("WhatsApp: %(messages)s") % {"messages": whatsapp})
    return lines


def plan_card(plan) -> dict[str, Any]:
    """A plan as the selling screens paint it: its own features, then the messages a month it includes, then its
    trial (the operation's last line, saas#2424)."""
    features = list(plan.features)
    trial = [features.pop()] if _has_trial_line(plan) else []
    assistant = messages_a_month(plan.assistant_messages_per_month)
    whatsapp = messages_a_month(plan.whatsapp_messages_per_month)
    own_features = [*features, *_message_lines(assistant, whatsapp)]
    return {
        **plan.model_dump(),
        "assistant_label": assistant,
        "whatsapp_label": whatsapp,
        "display_features": [*own_features, *trial],
        "own_features": own_features,
        "price_label": f"€{floatformat(plan.price_monthly, '-2')}",
        "months_free": annual_months_free(plan),
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
                "plan in one click — each plan up doubles your resources, and your service is never "
                "interrupted."
            ),
        },
        {
            "key": "dedicated",
            "question": _("What is dedicated infrastructure and who is it for?"),
            "answer": _(
                "A private environment reserved for your business alone, for companies with several "
                "locations, high volume or requirements of their own: its own capacity, a replicated "
                "database and priority support, from %(price)s a month. Contact us and we will size it "
                "with you."
            ) % {"price": dedicated_price_label()},
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
                "Within the European Union: on Amazon Web Services, in its Ireland region "
                "(eu-west-1), on GDPR-compliant infrastructure. The one exception is the AI "
                "assistant: if its European provider is unavailable, a backup provider may "
                "answer from outside the EU, under the safeguards our privacy policy describes."
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


def signable_cards(plans) -> list[dict[str, Any]]:
    """The plans a visitor can sign up for, as cards: an ``upgrade_only`` row is not on the public web."""
    return [plan_card(plan) for plan in plans.plans if not plan.upgrade_only]


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    """The plans a visitor can sign up for, as cards, and the dedicated offer by contact above them."""
    plans = plans_on_sale(request)
    days = trial_days(plans)
    faq = faq_items(days)
    entry = cheapest(plans)
    return render(
        request,
        "public/pricing/index.html",
        {
            "plans_main": signable_cards(plans),
            "dedicated_from": dedicated_price_label(),
            "cheapest_plan": plan_card(entry) if entry else None,
            "trial_note": trial_note(days),
            "months_free": common_months_free(plans),
            "faq_items": faq,
            "json_ld_faq": json_ld(faq_page(faq)),
        },
    )


@require_safe
def detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One plan a visitor can sign up for; an internal, retired, upgrade-only or unknown plan answers 404
    (saas#1950)."""
    cards = signable_cards(plans_on_sale(request))
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
