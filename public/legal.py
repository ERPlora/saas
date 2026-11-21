"""The legal pages of the public web: privacy policy, terms of use, cookie policy and legal notice.

The declaración responsable lives in ``public/declaracion.py``. Only the terms read data: the trial of
the plans on sale, through ``hubs.plan.list`` (``public.pricing``); no page touches the ORM.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.text import get_text_list
from django.utils.translation import pgettext
from django.views.decorators.http import require_safe
from live.spa import PALETTE_COOKIE

from hubs.services.suspensions import SUSPENDED_DELETE_DAYS
from public import pricing

#: The days after which the Hub erases a deleted business's database and files, all but its fiscal documents, as
#: section 5.1 of the terms promises: the days its owner can still recover it (``Hub.RETENTION``), which the tests pin.
DELETED_HUB_ERASE_DAYS = 90


@require_safe
def privacy(request: HttpRequest) -> HttpResponse:
    return render(request, "public/legal/privacy.html")


@require_safe
def terms(request: HttpRequest) -> HttpResponse:
    """The terms of use, with every number read from where it is enforced, never typed.

    ``HUB_EXIT_PACKAGE_TTL_DAYS`` is what the exit package's link expires on; ``SUSPENDED_DELETE_DAYS``
    is when the sweep of the suspended businesses deletes one; the trial of section 4
    is the trial of the plans a visitor can buy: an upgrade grants none, and without any trial on sale
    section 4 promises none; the custom domain of the opening clause is the one of the plans on sale
    whose ``includes_custom_domain`` is true, by name, and without any the clause names none. A term
    the customer accepted that the software does not honour is worse than no term at all.
    """
    plans = pricing.plans_on_sale(request)
    shortest, longest = pricing.trial_days(plans)
    custom_domain_plans = pricing.custom_domain_plans(plans)
    return render(
        request,
        "public/legal/terms.html",
        {
            "exit_package_days": settings.HUB_EXIT_PACKAGE_TTL_DAYS,
            "deleted_hub_days": DELETED_HUB_ERASE_DAYS,
            "suspended_hub_delete_days": SUSPENDED_DELETE_DAYS,
            "trial_days_min": shortest,
            "trial_days_max": longest,
            "custom_domain_plans": get_text_list(custom_domain_plans, pgettext("the last of a list", "and")),
            "custom_domain_plan_count": len(custom_domain_plans),
        },
    )


@require_safe
def cookies(request: HttpRequest) -> HttpResponse:
    """The cookie policy, naming the essential cookies as the settings that set them call them.

    Read from the settings rather than typed into the page, so the policy never names a cookie the
    site does not set (a ``django_language`` cookie while the language cookie is ``_lang``): that
    would not be an informed consent.
    """
    return render(
        request,
        "public/legal/cookies.html",
        {
            "session_cookie_name": settings.SESSION_COOKIE_NAME,
            "csrf_cookie_name": settings.CSRF_COOKIE_NAME,
            "consent_cookie_name": settings.COOKIE_CONSENT_NAME,
            "language_cookie_name": settings.LANGUAGE_COOKIE_NAME,
            "palette_cookie_name": PALETTE_COOKIE,
        },
    )


@require_safe
def legal_notice(request: HttpRequest) -> HttpResponse:
    return render(request, "public/legal/legal_notice.html")
