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
* the contact mail is rendered from ``public/templates/public/email/`` and sent to ``SUPPORT_EMAIL``
  (plan §3.o) with the visitor as «Reply-To»; its limit per address reads the address the load balancer saw;
  a refused or failed message comes back typed (PUBLIC-G39), and a page that links the form may name its
  topic (``?subject=``, PUBLIC-G40);
* the contact section states the real trial of the plans on sale, never a typed «15 days».
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
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
from live import recaptcha
from live.meta import Category
from live.ninja import run_operation_sync

from public import context_processors, pricing
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
    (gettext_lazy("Inventory"), "Zoho Inventory / Sortly", 89),
    (gettext_lazy("CRM"), "HubSpot / Pipedrive", 95),
    (gettext_lazy("E-commerce + POS"), "Shopify + Square", 112),
)

#: The topics another page may open the form on (``/contact/?subject=<key>``, PUBLIC-G40), and how the mail
#: to support names them (internal, in English like the rest of the mail). Any other value is ignored.
CONTACT_TOPICS = {
    "collaborate": "Collaborator program",
    "security": "Security",
}
#: What the visitor typed, kept in the session when the message is refused or fails (PUBLIC-G39) and shown once.
CONTACT_DRAFT_KEY = "public.contact_draft"
#: The field of reCAPTCHA's token and the action it is made for (frontend/recaptcha.ts, ``data-recaptcha-action``).
RECAPTCHA_FIELD = "recaptcha_token"
RECAPTCHA_ACTION = "contact"
#: The fields of the form, in order.
CONTACT_FIELDS = ("first_name", "last_name", "email", "phone", "message")

#: The answers of the contact form, by outcome (``messages``, after the redirect); the «sent» one states the
#: reply time (:func:`sent_message`).
FORM_MESSAGES = {
    "limited": gettext_lazy(
        "Too many messages from your network. Please try again in a little while."
    ),
    "required": gettext_lazy("All fields are required except the phone number."),
    "email": gettext_lazy("Enter a valid email address."),
    "failed": gettext_lazy(
        "Sorry, something went wrong sending your message. Please try again."
    ),
}


def sent_message() -> str:
    """The answer to a sent message, with the reply time the web states everywhere (PUBLIC-G41)."""
    hours = context_processors.SUPPORT_REPLY_HOURS
    return ngettext(
        "Thanks! We received your message and will reply within %(hours)d business hour.",
        "Thanks! We received your message and will reply within %(hours)d business hours.",
        hours,
    ) % {"hours": hours}


def contact_form_context(request: HttpRequest) -> dict[str, Any]:
    """What the form shows: the draft of a refused message (once) and the topic it was opened on."""
    draft = request.session.pop(CONTACT_DRAFT_KEY, None) or {}
    topic = request.GET.get("subject") or draft.get("subject")
    return {
        "contact_draft": draft,
        "contact_topic": topic if topic in CONTACT_TOPICS else None,
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
            **contact_form_context(request),
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
    return render(request, "public/landing/contact.html", contact_form_context(request))


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
    """The limit per address of the contact form, before reCAPTCHA (``contact_submit``)."""
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

    Bot protection: the form is limited per address (``CONTACT_FORM_RATELIMIT``), and a complete message is
    mailed only when reCAPTCHA Enterprise says a person sent it (``recaptcha_token``, action ``contact``;
    ``live.recaptcha``; Ioan, 2026-10-22, over ADR-0154, which had retired it). A throttled, invalid or
    unverified message is never mailed; a throttled or incomplete one never asks Google.
    """
    fields = {name: request.POST.get(name, "").strip() for name in CONTACT_FIELDS}
    subject = request.POST.get("subject", "")
    topic = subject if subject in CONTACT_TOPICS else None
    if getattr(request, "limited", False):
        return _refused(request, fields, topic, FORM_MESSAGES["limited"])
    if not all(
        fields[name] for name in ("first_name", "last_name", "email", "message")
    ):
        return _refused(request, fields, topic, FORM_MESSAGES["required"])
    try:
        validate_email(fields["email"])
    except ValidationError:
        return _refused(request, fields, topic, FORM_MESSAGES["email"])
    try:
        recaptcha.verify_or_raise(request, request.POST.get(RECAPTCHA_FIELD), RECAPTCHA_ACTION)
    except recaptcha.RecaptchaFailed as refused:
        return _refused(request, fields, topic, refused.message)

    context = {
        **fields,
        # A header carries one line: a name with a line break must not add one to the subject.
        "first_name": _one_line(fields["first_name"]),
        "last_name": _one_line(fields["last_name"]),
        "topic": CONTACT_TOPICS.get(topic or ""),
    }
    try:
        EmailMessage(
            subject=_one_line(
                render_to_string("public/email/contact_subject.txt", context)
            ),
            body=render_to_string("public/email/contact_body.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.SUPPORT_EMAIL],
            # Support answers with «Reply»: to the visitor, never to our sender.
            reply_to=[fields["email"]],
        ).send(fail_silently=False)
    except Exception:
        # Any backend (SMTP, SES) may fail: the visitor is told, the cause goes to the log.
        logger.exception("Contact form message could not be sent")
        return _refused(request, fields, topic, FORM_MESSAGES["failed"])
    logger.info("Contact form message sent to support")
    messages.success(request, sent_message())
    return _back_to(request)


def _refused(
    request: HttpRequest, fields: dict[str, str], topic: str | None, message: str
) -> HttpResponseRedirect:
    """Back to the form with the reason and what was typed, so nothing has to be written twice."""
    request.session[CONTACT_DRAFT_KEY] = {**fields, "subject": topic or ""}
    messages.error(request, message)
    return _back_to(request)
