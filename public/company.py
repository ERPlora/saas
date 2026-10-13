"""``/about/``, ``/collaborate/`` and the «coming soon» pages ``/blog/``, ``/careers/`` and ``/press/``
(not indexed).

Port of ``apps/public/company/views.py`` (origin/develop c5ca8ca). ``/company/`` is a permanent
redirect to ``/about/`` in ``public/urls.py`` (external and cached links, issue #547);
``/developers/`` is gone with the third-party marketplace (spec §8.3). ``/collaborate/`` reads the
plans and the taxonomy through the operations of ``hubs`` (plan §3.m, L7).
"""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe
from live.ninja import run_operation_sync

from public import pricing


@require_safe
def about(request: HttpRequest) -> HttpResponse:
    return render(request, "public/company/about.html")


@require_safe
def blog(request: HttpRequest) -> HttpResponse:
    return render(request, "public/company/blog.html")


@require_safe
def careers(request: HttpRequest) -> HttpResponse:
    return render(request, "public/company/careers.html")


@require_safe
def press(request: HttpRequest) -> HttpResponse:
    return render(request, "public/company/press.html")


@require_safe
def collaborate(request: HttpRequest) -> HttpResponse:
    """The collaborator programme: a year free on a paid plan for the experts who shape the apps.

    The old view read ``Plan.objects.filter(slug="starter")``: a plan off sale or internal would
    still be offered (WORKFLOW F63). The year is now valued at the cheapest PAID plan a visitor can
    sign up for, from the plans on sale; the cheapest of all is the Free plan, and «valued at €0» says
    nothing. Without a paid plan on sale, no value is stated.
    """
    plans = pricing.plans_on_sale(request)
    price = pricing.cheapest_paid_price(plans)
    paid = next(
        (
            plan
            for plan in plans.plans
            if not plan.upgrade_only and price is not None and plan.price_monthly == price
        ),
        None,
    )
    return render(
        request,
        "public/company/collaborate.html",
        {
            "paid_plan": paid,
            "paid_plan_annual": paid.price_monthly * 12 if paid else None,
            "sector_count": len(run_operation_sync(request, "hubs.sector.list").sectors),
            "business_type_count": len(
                run_operation_sync(request, "hubs.business_type.list").business_types
            ),
        },
    )
