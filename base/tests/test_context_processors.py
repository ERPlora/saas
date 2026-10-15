"""``theme`` for every template: the colour mode of the shell, as ``@erplora/ui`` resolves it.

The SPA's modes are ``system``, ``light`` and ``dark``, and ``system`` (follow the OS) when nothing
says otherwise (``packages/ui/src/shell/theme.ts``). The template pages (errors, the public web) read
the same mode from the ``theme`` cookie (ERPlora/saas ``apps/core/context_processors.py``):
``dark`` adds ``ion-palette-dark`` to ``<html>`` on the server, and ``system`` lets a nonce'd script
follow ``prefers-color-scheme``. Without the processor ``theme`` was empty, so ``system`` never applied.

A signed-in account's own mode (Account → Preferences, ``accounts.UserPreferences.theme_mode``, what
the panel paints) wins over the cookie: the public web and the error pages look like the panel.
TEMPLATES loads the processor on every render, so it reaches ``accounts`` lazily, inside the function,
and falls back to the cookie if ``accounts.queries.preferences_of`` is missing: a top-level import of a
symbol that was not on main took the whole site down in CI (2026-10-14, hotfix cfc4adb).
"""

import ast
import logging

import pytest
from django.apps import apps
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils.module_loading import import_string

import base.context_processors as processors_module
from accounts.models import UserPreferences
from base.context_processors import DEFAULT_THEME, PREFERENCES_OF, THEMES, theme

PROCESSOR = "base.context_processors.theme"


def _theme(cookie: str | None = None, user=None) -> str:
    request = RequestFactory().get("/")
    if cookie is not None:
        request.COOKIES["theme"] = cookie
    if user is not None:
        request.user = user
    return theme(request)["theme"]


def test_the_modes_are_the_shells():
    assert (THEMES, DEFAULT_THEME) == (("system", "light", "dark"), "system")


def test_without_a_cookie_the_page_follows_the_system():
    assert _theme() == "system"


@pytest.mark.parametrize("mode", ["system", "light", "dark"])
def test_the_cookie_chooses_the_mode(mode):
    assert _theme(mode) == mode


@pytest.mark.parametrize("cookie", ["", "DARK", "orange-dark", "dark; x", "</script>"])
def test_an_unknown_cookie_follows_the_system(cookie):
    """Only a known mode reaches the template (``orange-*`` were ERPlora/saas legacy palettes)."""
    assert _theme(cookie) == "system"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_a_signed_in_account_gets_the_mode_it_chose(ana, mode):
    UserPreferences.objects.create(user=ana, theme_mode=mode)

    assert _theme(user=ana) == mode


def test_the_account_wins_over_the_cookie(ana):
    """The panel paints the account's mode; a cookie left by another person on the device does not."""
    UserPreferences.objects.create(user=ana, theme_mode="light")

    assert _theme("dark", user=ana) == "light"


def test_an_account_that_never_chose_follows_the_system(ana):
    """No preferences row: the account's default, ``system``, whatever an old cookie says."""
    assert _theme("dark", user=ana) == "system"


def test_the_account_dependency_is_declared_and_present():
    """The processor names what it needs from ``accounts`` in one place, and it exists in the tree."""
    assert PREFERENCES_OF == "accounts.queries.preferences_of"
    assert apps.is_installed("accounts")
    assert callable(import_string(PREFERENCES_OF))


def test_the_processor_reaches_accounts_only_lazily():
    """No module-level import of ``accounts``: TEMPLATES loads this module on every render, and a
    top-level import of a symbol missing on main took the whole site down in CI (2026-10-14)."""
    with open(processors_module.__file__, encoding="utf-8") as source:
        tree = ast.parse(source.read())

    top_level = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            (getattr(node, "module", None) or alias.name).startswith("accounts")
            for alias in node.names
        )
    ]
    assert top_level == []
    assert not any(name.startswith("accounts") for name in vars(processors_module))


def test_without_preferences_of_an_account_falls_back_to_the_cookie(ana, monkeypatch, caplog):
    """If ``accounts`` lacks the function (a partial deploy), the page still renders with the cookie,
    and the log says why."""
    import accounts.queries

    UserPreferences.objects.create(user=ana, theme_mode="light")
    monkeypatch.delattr(accounts.queries, "preferences_of")

    with caplog.at_level(logging.WARNING, logger="base.context_processors"):
        assert _theme("dark", user=ana) == "dark"
    assert PREFERENCES_OF in caplog.text


@pytest.mark.django_db
def test_an_anonymous_visitor_costs_no_query(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert _theme("dark", user=AnonymousUser()) == "dark"


@pytest.fixture
def with_processor(settings):
    """The processor installed for every template (``settings.TEMPLATES``)."""
    template = settings.TEMPLATES[0]
    processors = template["OPTIONS"]["context_processors"]
    if PROCESSOR not in processors:
        settings.TEMPLATES = [
            {
                **template,
                "OPTIONS": {
                    **template["OPTIONS"],
                    "context_processors": [*processors, PROCESSOR],
                },
            },
            *settings.TEMPLATES[1:],
        ]


def _error_page(cookie: str | None = None) -> str:
    """An error page of Django's (``templates/errors/base.html``), rendered as a request renders it."""
    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    if cookie is not None:
        request.COOKIES["theme"] = cookie
    return render_to_string("400.html", request=request)


@pytest.mark.django_db
@pytest.mark.usefixtures("with_processor")
def test_an_error_page_follows_the_system_without_a_cookie():
    html = _error_page()

    assert '<html lang="en">' in html
    assert ': "system";' in html


@pytest.mark.django_db
@pytest.mark.usefixtures("with_processor")
def test_an_error_page_is_dark_with_the_dark_cookie():
    html = _error_page("dark")

    assert '<html lang="en" class="ion-palette-dark">' in html
