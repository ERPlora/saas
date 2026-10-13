"""The legal pages of the public web: privacy policy, terms of use, cookie policy and legal notice
(spec §8.1).

Ported from ERPlora/saas ``apps/public/legal/views.py`` (origin/develop c5ca8ca); the declaración
responsable lives in ``public/declaracion.py``. Only the terms read data: the trial of the plans on
sale, through ``hubs.plan.list`` (``public.pricing``, plan §3.m); no page touches the ORM.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from public import pricing

#: The days a suspended hub waits before it is deleted, as §3 of the terms promises. The task that
#: deletes it lives in the Hub (its worker), not in this project: this is the number the contract
#: states, and the Hub's clock must match it (saas#1264). Never lowered without changing the terms.
SUSPENDED_HUB_DELETE_DAYS = 90


@require_safe
def privacy(request: HttpRequest) -> HttpResponse:
    return render(request, "public/legal/privacy.html")


@require_safe
def terms(request: HttpRequest) -> HttpResponse:
    """The terms of use, with every number read from where it is enforced, never typed.

    ``HUB_EXIT_PACKAGE_TTL_DAYS`` is what the exit package's link expires on (saas#1261, saas#1262);
    the trial of §4 is the trial of the plans a visitor can buy (saas#2409): an upgrade grants none
    (#809), and without any trial on sale §4 promises none. A term the customer accepted that the
    software does not honour is worse than no term at all.
    """
    shortest, longest = pricing.trial_days(pricing.plans_on_sale(request))
    return render(
        request,
        "public/legal/terms.html",
        {
            "exit_package_days": settings.HUB_EXIT_PACKAGE_TTL_DAYS,
            "suspended_hub_delete_days": SUSPENDED_HUB_DELETE_DAYS,
            "trial_days_min": shortest,
            "trial_days_max": longest,
        },
    )


@require_safe
def cookies(request: HttpRequest) -> HttpResponse:
    """The cookie policy, naming the essential cookies as the settings that set them call them.

    Read from the settings rather than typed into the page: the old policy named a
    ``django_language`` cookie that nothing set while the language cookie was ``_lang``, and a
    cookie policy that lists cookies the site does not set is not an informed consent.
    """
    return render(
        request,
        "public/legal/cookies.html",
        {
            "session_cookie_name": settings.SESSION_COOKIE_NAME,
            "csrf_cookie_name": settings.CSRF_COOKIE_NAME,
            "consent_cookie_name": settings.COOKIE_CONSENT_NAME,
            "language_cookie_name": settings.LANGUAGE_COOKIE_NAME,
        },
    )


@require_safe
def legal_notice(request: HttpRequest) -> HttpResponse:
    return render(request, "public/legal/legal_notice.html")
