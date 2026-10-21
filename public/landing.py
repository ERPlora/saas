"""The home ``/`` and the contact page ``/contact/`` with its form ``/contact/submit/`` (spec §8.1).

Port of ERPlora/saas ``apps/public/landing/views.py`` (origin/develop c5ca8ca); ``robots.txt`` and
``llms.txt`` are ``public/seo.py``, ``/set-language/`` is ``public/language.py`` and ``/download/`` is
``public/appdist.py``. What changed:

* no model: the plans come from ``hubs.plan.list`` (``public.pricing``) and the apps from
  ``apps.app.list`` (plan §3.m, spec §5.1), with ``run_operation_sync`` as ``base/spa.py`` does;
* the six featured apps and the twelve chips are the first ``listed`` apps by section and name (the
  order of ``apps.app.list``; ``is_featured`` and the downloads do not exist any more), counted free
  or ``premium`` (decision 17: a premium app is included in the paid plans). Without a listed app
  the apps blocks are omitted (spec §5.3);
* the contact mail is rendered from ``public/templates/public/email/`` and sent with ``send_mail``
  to ``SUPPORT_EMAIL`` (plan §3.o); its limit per address reads the address the load balancer saw;
* the contact section states the real trial of the plans on sale, never a typed «15 days».
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST, require_safe
from django_ratelimit.decorators import ratelimit
from live.meta import Category
from live.ninja import run_operation_sync

from public import pricing
from public.structured_data import json_ld, organization, software_application

logger = logging.getLogger(__name__)

#: The featured cards and the chips of the home (spec §8.1).
FEATURED_COUNT = 6
CHIP_COUNT = 12
#: How many premium app names the ecosystem section quotes.
PREMIUM_EXAMPLES = 5
#: The anchor of the contact section, on the home and on /contact/.
CONTACT_ANCHOR = "#contacto"
#: What the limiter gets when no address can be read: never the source of a real connection.
UNKNOWN_ADDRESS = "0.0.0.0"

#: «One platform, one invoice» of the home: what each function costs in the tool a small business
#: typically pays for it (public vendor pricing, May 2026), in euros a month. Only functions the apps of
#: the Hub cover today (PUBLIC-F07: no accounting, payroll or support-ticket row); the total is their sum.
TYPICAL_STACK = (
    (gettext_lazy("Electronic invoicing"), "FacturaDirecta / Holded", 39),
    (gettext_lazy("Inventory"), "Cin7 / TradeGecko", 89),
    (gettext_lazy("CRM"), "HubSpot / Pipedrive", 95),
    (gettext_lazy("E-commerce + POS"), "Shopify + Square", 112),
)

#: The answers of the contact form, by outcome (``messages``, after the redirect).
FORM_MESSAGES = {
    "limited": gettext_lazy(
        "Too many messages from your network. Please try again in a little while."
    ),
    "required": gettext_lazy("All fields are required except the phone number."),
    "email": gettext_lazy("Enter a valid email address."),
    "sent": gettext_lazy(
        "Thanks! We received your message and will reply within 4 business hours."
    ),
    "failed": gettext_lazy(
        "Sorry, something went wrong sending your message. Please try again."
    ),
}


# --- The home -----------------------------------------------------------------------------------


def _app_card(app) -> dict[str, Any]:
    category = Category(app.category) if app.category else None
    return {
        "id": app.id,
        "name": app.name,
        "summary": app.summary,
        # Cleaned with nh3 by apps.app.list (spec §8.4): safe to paint inline.
        "icon_svg": mark_safe(app.icon_svg),
        "category": app.category or "",
        "category_label": category.label if category else "",
        "premium": app.premium,
        "url": reverse("public:store_detail", args=[app.id]),
        "store_url": (
            f"{reverse('public:store')}?category={app.category}"
            if app.category
            else reverse("public:store")
        ),
    }


def contact_trial_note(days: pricing.TrialDays) -> str:
    """The contact section's line on the trial, from the plans on sale (saas#2414)."""
    shortest, longest = days
    if not longest:
        return ""
    if shortest == longest:
        return ngettext(
            "Ready for more? A paid plan chosen when creating a Hub comes with a %(days)d-day "
            "free trial using your own data.",
            "Ready for more? A paid plan chosen when creating a Hub comes with a %(days)d-day "
            "free trial using your own data.",
            longest,
        ) % {"days": longest}
    return _(
        "Ready for more? A paid plan chosen when creating a Hub comes with a free trial of "
        "%(min_days)d to %(max_days)d days, depending on the plan, using your own data."
    ) % {"min_days": shortest, "max_days": longest}


@require_safe
def home(request: HttpRequest) -> HttpResponse:
    """The landing: the product, its apps, its plans and a way to reach us, from live data."""
    base = f"https://{request.get_host()}"
    plans = pricing.plans_on_sale(request)
    entry = pricing.cheapest(plans)
    apps = [_app_card(app) for app in run_operation_sync(request, "apps.app.list").apps]
    premium = [app for app in apps if app["premium"]]
    return render(
        request,
        "public/landing/home.html",
        {
            "plans": [
                pricing.plan_card(plan) for plan in plans.plans if not plan.upgrade_only
            ],
            "cheapest_plan": pricing.plan_card(entry) if entry else None,
            "featured_apps": [
                {**app, "eyebrow": f"{n:02d} · {app['category_label'] or _('App')}"}
                for n, app in enumerate(apps[:FEATURED_COUNT], start=1)
            ],
            "chip_apps": apps[:CHIP_COUNT],
            "total_apps": len(apps),
            "free_apps": len(apps) - len(premium),
            "premium_apps": len(premium),
            "premium_app_examples": [app["name"] for app in premium[:PREMIUM_EXAMPLES]],
            "contact_trial_note": contact_trial_note(pricing.trial_days(plans)),
            "typical_stack": [
                {"function": function, "tool": tool, "cost": cost}
                for function, tool, cost in TYPICAL_STACK
            ],
            "typical_stack_total": sum(cost for _, _, cost in TYPICAL_STACK),
            # Built here so the price tracks Plan: a price typed into the template is the number
            # an answer engine quotes all year.
            "json_ld_organization": json_ld(
                organization(base, f"{base}{static('public/img/logo.png')}")
            ),
            "json_ld_application": json_ld(
                software_application(
                    base, entry.price_monthly if entry else None, len(apps)
                )
            ),
        },
    )


# --- The contact page and its form -------------------------------------------------------------


@require_safe
def contact(request: HttpRequest) -> HttpResponse:
    return render(request, "public/landing/contact.html")


def visitor_address(group, request: HttpRequest) -> str:
    """The visitor's address: ``REMOTE_ADDR``, where ``public.client_ip`` put it behind the ALB.

    Only a real address is returned: the limiter masks it with ``ipaddress`` and junk there would
    be a 500 on a public door.
    """
    try:
        return str(ipaddress.ip_address(request.META.get("REMOTE_ADDR", "")))
    except ValueError:
        return UNKNOWN_ADDRESS


def _contact_rate(group, request: HttpRequest) -> str:
    """The limit per address of the contact form (reCAPTCHA was retired, ADR-0154)."""
    return settings.CONTACT_FORM_RATELIMIT


def _back_to(request: HttpRequest) -> HttpResponseRedirect:
    """PRG: back to the page that sent the form, at its contact section; never another host."""
    target = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = "/"
    return HttpResponseRedirect(
        target if "#" in target else f"{target}{CONTACT_ANCHOR}"
    )


def _one_line(value: str) -> str:
    return " ".join(value.split())


@require_POST
@ratelimit(key=visitor_address, rate=_contact_rate, method="POST", block=False)
def contact_submit(request: HttpRequest) -> HttpResponse:
    """The contact form: a plain POST and a redirect back with a message (PRG).

    Bot protection: Cloudflare is gone and reCAPTCHA was retired (ADR-0154); the form is limited
    per address (``CONTACT_FORM_RATELIMIT``). A throttled or invalid message is never mailed.
    """
    fields = {
        name: request.POST.get(name, "").strip()
        for name in ("first_name", "last_name", "email", "phone", "message")
    }
    if getattr(request, "limited", False):
        messages.error(request, FORM_MESSAGES["limited"])
        return _back_to(request)
    if not all(
        fields[name] for name in ("first_name", "last_name", "email", "message")
    ):
        messages.error(request, FORM_MESSAGES["required"])
        return _back_to(request)
    try:
        validate_email(fields["email"])
    except ValidationError:
        messages.error(request, FORM_MESSAGES["email"])
        return _back_to(request)

    context = {
        **fields,
        # A header carries one line: a name with a line break must not add one to the subject.
        "first_name": _one_line(fields["first_name"]),
        "last_name": _one_line(fields["last_name"]),
    }
    try:
        send_mail(
            subject=_one_line(
                render_to_string("public/email/contact_subject.txt", context)
            ),
            message=render_to_string("public/email/contact_body.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.SUPPORT_EMAIL],
            fail_silently=False,
        )
    except Exception:
        # Any backend (SMTP, SES) may fail: the visitor is told, the cause goes to the log.
        logger.exception("Contact form message could not be sent")
        messages.error(request, FORM_MESSAGES["failed"])
        return _back_to(request)
    logger.info("Contact form message sent to support")
    messages.success(request, FORM_MESSAGES["sent"])
    return _back_to(request)
