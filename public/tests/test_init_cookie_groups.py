"""``manage.py init_cookie_groups``: the cookie groups of the consent banner and of ``/cookies/``.

Ported from ERPlora/saas ``apps/dashboard/core/management/commands/init_cookie_groups.py`` and
``tests/unit/test_cookie_consent_seed.py`` (origin/develop c5ca8ca). The cookie policy is rendered
from these rows (nothing is auto-discovered), so every tracker gated by a group must declare its
cookies here. Adapted: the essential cookies are the ones saas-next really sets (Django's default
session and CSRF names, the ``_lang`` language cookie, the consent cookie and the shell's palette),
and names and descriptions are stored in English, the source, and translated when rendered.
"""

from io import StringIO

import pytest
from cookie_consent.models import Cookie, CookieGroup
from django.conf import settings
from django.core.management import call_command
from django.utils import translation
from live.spa import PALETTE_COOKIE

pytestmark = pytest.mark.django_db


def _seed():
    call_command("init_cookie_groups", stdout=StringIO())


def _names(varname):
    return set(
        Cookie.objects.filter(cookiegroup__varname=varname).values_list(
            "name", flat=True
        )
    )


def test_the_three_groups_in_order():
    _seed()

    assert list(
        CookieGroup.objects.order_by("ordering").values_list("varname", flat=True)
    ) == [
        "essential",
        "analytical",
        "marketing",
    ]


def test_the_essential_group_is_required_and_never_deleted():
    """``CleanCookiesMiddleware`` reads only ``is_deletable``: a deletable essential group made
    «Decline» delete the session cookie and sign the person out (saas#975)."""
    _seed()

    essential = CookieGroup.objects.get(varname="essential")
    assert essential.is_required is True
    assert essential.is_deletable is False


def test_a_deletable_essential_group_is_repaired():
    _seed()
    CookieGroup.objects.filter(varname="essential").update(is_deletable=True)

    _seed()

    assert CookieGroup.objects.get(varname="essential").is_deletable is False


def test_the_essential_cookies_are_the_ones_this_site_sets():
    _seed()

    assert _names("essential") == {
        settings.SESSION_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
        settings.LANGUAGE_COOKIE_NAME,
        settings.COOKIE_CONSENT_NAME,
        "messages",
        PALETTE_COOKIE,
    }


def test_google_analytics_and_clarity_cookies_are_declared_under_analytical():
    _seed()

    assert {
        "_ga",
        "_ga_*",
        "_clck",
        "_clsk",
        "CLID",
        "MUID",
        "ANONCHK",
        "MR",
        "SM",
    } <= _names("analytical")


def test_the_seed_is_idempotent():
    _seed()
    _seed()

    assert CookieGroup.objects.filter(varname="analytical").count() == 1
    assert (
        Cookie.objects.filter(cookiegroup__varname="analytical", name="_clck").count()
        == 1
    )


def test_names_and_descriptions_are_stored_in_english_and_translated_to_spanish():
    with translation.override("es"):
        _seed()

    essential = CookieGroup.objects.get(varname="essential")
    session = Cookie.objects.get(
        cookiegroup=essential, name=settings.SESSION_COOKIE_NAME
    )
    assert essential.name == "Essential cookies"
    for text in (essential.name, essential.description, session.description):
        with translation.override("es"):
            assert translation.gettext(text) != text, f"no Spanish for {text!r}"


def test_it_says_what_it_did():
    out = StringIO()

    call_command("init_cookie_groups", stdout=out)

    assert "3 groups" in out.getvalue()
