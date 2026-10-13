"""``theme`` for every template: the colour mode of the shell, as ``@erplora/ui`` resolves it.

The SPA's modes are ``system``, ``light`` and ``dark``, and ``system`` (follow the OS) when nothing
says otherwise (``packages/ui/src/shell/theme.ts``). The template pages (sign-in, errors) read the
same mode from the ``theme`` cookie (ERPlora/saas ``apps/core/context_processors.py``): ``dark`` adds
``ion-palette-dark`` to ``<html>`` on the server, and ``system`` lets a nonce'd script follow
``prefers-color-scheme``. Without the processor ``theme`` was empty, so ``system`` never applied.
"""

import pytest
from django.test import RequestFactory

from base.context_processors import DEFAULT_THEME, THEMES, theme

PROCESSOR = "base.context_processors.theme"


def _theme(cookie: str | None = None) -> str:
    request = RequestFactory().get("/accounts/login/")
    if cookie is not None:
        request.COOKIES["theme"] = cookie
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


@pytest.mark.django_db
@pytest.mark.usefixtures("with_processor")
def test_the_sign_in_follows_the_system_without_a_cookie(client):
    html = client.get("/accounts/login/").content.decode()

    assert '<html lang="en">' in html
    assert ': "system";' in html


@pytest.mark.django_db
@pytest.mark.usefixtures("with_processor")
def test_the_sign_in_is_dark_with_the_dark_cookie(client):
    client.cookies["theme"] = "dark"

    html = client.get("/accounts/login/").content.decode()

    assert '<html lang="en" class="ion-palette-dark">' in html
