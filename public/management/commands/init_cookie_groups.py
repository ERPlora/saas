"""Seed the cookie groups of the consent banner and of ``/cookies/`` (django-cookie-consent).

Ported from ERPlora/saas ``apps/dashboard/core/management/commands/init_cookie_groups.py``
(origin/develop c5ca8ca). The cookie policy is rendered from these rows, nothing is auto-discovered:
a tracker gated by a group must declare its cookies here. Safe to run on every start (idempotent).

Names and descriptions are stored in English, the source (``gettext_noop`` puts them in the
catalogue), and the templates translate them when they render.
"""

from __future__ import annotations

from cookie_consent.models import Cookie, CookieGroup
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import gettext_noop
from live.spa import PALETTE_COOKIE

#: ``(varname, name, description, is_required, ordering)``.
GROUPS = (
    (
        "essential",
        gettext_noop("Essential cookies"),
        gettext_noop(
            "These cookies are necessary for the website to work and cannot be turned off."
        ),
        True,
        1,
    ),
    (
        "analytical",
        gettext_noop("Analytical cookies"),
        gettext_noop("These cookies help us understand how visitors use our website."),
        False,
        2,
    ),
    (
        "marketing",
        gettext_noop("Marketing cookies"),
        gettext_noop("These cookies are used to show personalised advertising."),
        False,
        3,
    ),
)


def _cookies() -> tuple[tuple[str, str, str], ...]:
    """``(group varname, cookie name, description)``; the essential names, as this site sets them."""
    return (
        (
            "essential",
            settings.SESSION_COOKIE_NAME,
            gettext_noop("Session cookie that keeps you signed in"),
        ),
        (
            "essential",
            settings.CSRF_COOKIE_NAME,
            gettext_noop("Protection against cross-site request forgery"),
        ),
        (
            "essential",
            settings.LANGUAGE_COOKIE_NAME,
            gettext_noop("The language you chose"),
        ),
        (
            "essential",
            settings.COOKIE_CONSENT_NAME,
            gettext_noop("The cookie choices you made"),
        ),
        ("essential", "messages", gettext_noop("Notices shown after an action")),
        ("essential", PALETTE_COOKIE, gettext_noop("The colour theme you chose")),
        ("analytical", "_ga", gettext_noop("Google Analytics client identifier")),
        ("analytical", "_ga_*", gettext_noop("Google Analytics session data")),
        (
            "analytical",
            "_clck",
            gettext_noop("Microsoft Clarity user identifier and preferences"),
        ),
        ("analytical", "_clsk", gettext_noop("Microsoft Clarity session identifier")),
        (
            "analytical",
            "CLID",
            gettext_noop("Microsoft Clarity first-seen user identifier"),
        ),
        (
            "analytical",
            "MUID",
            gettext_noop("Microsoft/Bing unique browser identifier (set by Clarity)"),
        ),
        (
            "analytical",
            "ANONCHK",
            gettext_noop("Microsoft/Bing MUID-to-ANID transfer flag (set by Clarity)"),
        ),
        (
            "analytical",
            "MR",
            gettext_noop("Microsoft/Bing MUID refresh flag (set by Clarity)"),
        ),
        (
            "analytical",
            "SM",
            gettext_noop("Microsoft/Bing MUID cross-domain sync (set by Clarity)"),
        ),
    )


class Command(BaseCommand):
    help = "Create the cookie consent groups and their cookies (idempotent)."

    def handle(self, *args, **options):
        groups = {}
        for varname, name, description, is_required, ordering in GROUPS:
            group, created = CookieGroup.objects.get_or_create(
                varname=varname,
                defaults={
                    "name": name,
                    "description": description,
                    "is_required": is_required,
                    # The essential group is never deletable: `CleanCookiesMiddleware` reads only
                    # `is_deletable`, and deleting the session cookie signs the person out (saas#975).
                    "is_deletable": not is_required,
                    "ordering": ordering,
                },
            )
            if is_required and group.is_deletable:
                group.is_deletable = False
                group.save(update_fields=["is_deletable"])
            groups[varname] = group
            self.stdout.write(f"{'Created' if created else 'Already there'}: {varname}")

        for varname, name, description in _cookies():
            _, created = Cookie.objects.get_or_create(
                cookiegroup=groups[varname],
                name=name,
                defaults={"description": description, "path": "/", "domain": ""},
            )
            if created:
                self.stdout.write(f"  Added cookie {name} to {varname}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Cookie consent: {CookieGroup.objects.count()} groups, {Cookie.objects.count()} cookies."
            )
        )
