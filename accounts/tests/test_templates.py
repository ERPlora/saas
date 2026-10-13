"""The account screens are Vue pages (``accounts/frontend/pages``): the launcher and every error
of the sign-in. Only the auto-submitted form of the jump to a hub stays a Django template, because
it is not a screen: it POSTs the one-time code to the hub (``hub_login_form.html``)."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

ACCOUNTS_TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "accounts"
SOCIALACCOUNT_TEMPLATES = Path(settings.BASE_DIR) / "templates" / "socialaccount"


def test_only_the_jump_form_stays_a_template():
    assert sorted(path.name for path in ACCOUNTS_TEMPLATES.iterdir()) == ["hub_login_form.html"]
    assert get_template("accounts/hub_login_form.html")


def test_the_google_error_screens_are_vue_pages_too():
    """allauth's «Third-Party Login Failure» and «Login Cancelled» now redirect to /login/error."""
    assert not (SOCIALACCOUNT_TEMPLATES / "authentication_error.html").exists()
    assert not (SOCIALACCOUNT_TEMPLATES / "login_cancelled.html").exists()


# --- What the template pages still paint: Ionic and our own CSS, no OutfitKit (PLAN §16.11) ---

#: An OutfitKit trace in rendered HTML or CSS: an ``ok-*`` tag, class, attribute or ``--ok-*`` token.
#: Ionic's own ``ok-text`` attribute (``ion-select``) is not one of ours.
OK_TRACE = re.compile(r"(?<![\w])(?!ok-text\b)ok-[\w-]+")


def stylesheets(html: str) -> list[str]:
    """The static paths of every ``<link rel="stylesheet">`` of a page."""
    hrefs = re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)
    assert hrefs, "the page links no stylesheet"
    assert all(href.startswith(settings.STATIC_URL) for href in hrefs), hrefs
    return [href.removeprefix(settings.STATIC_URL) for href in hrefs]


def assert_no_outfitkit(html: str) -> None:
    """Nothing the page paints comes from OutfitKit: its HTML and the rules of every stylesheet it
    links (which must exist). A CSS comment may still cite its history."""
    assert "outfitkit" not in html.lower()
    assert OK_TRACE.findall(html) == []
    for path in stylesheets(html):
        found = finders.find(path)
        assert found, f"{path} is linked but no static finder has it"
        rules = re.sub(r"/\*.*?\*/", "", Path(found).read_text(encoding="utf-8"), flags=re.S)
        assert "outfitkit" not in rules.lower(), path
        assert OK_TRACE.findall(rules) == [], path


def assert_tokens_defined(html: str) -> None:
    """Every ``var(--ep-*)`` of the linked CSS is defined by one of the linked stylesheets."""
    css = "\n".join(Path(finders.find(path)).read_text(encoding="utf-8") for path in stylesheets(html))
    used = set(re.findall(r"var\((--ep-[\w-]+)", css))
    defined = set(re.findall(r"(--ep-[\w-]+)\s*:", css))
    assert used <= defined, sorted(used - defined)


@pytest.mark.django_db
def test_the_login_page_paints_without_outfitkit(client):
    html = client.get("/accounts/login/").content.decode()

    assert_no_outfitkit(html)
    assert_tokens_defined(html)


def test_the_outfitkit_copy_is_gone_from_static():
    assert finders.find("vendor/outfitkit/palettes.css") is None
    assert finders.find("vendor/outfitkit/layout.css") is None
    assert finders.find("css/outfitkit-theme.css") is None


@pytest.mark.parametrize(
    "name", ["account/_auth_shell_top.html", "account/_auth_shell_bottom.html", "account/_auth_code_field.html"]
)
def test_the_partials_of_the_retired_template_screens_are_gone(name):
    """The 2FA and launcher screens are Vue pages (``AuthShell.vue``, ``CodeField.vue``): nothing
    includes these partials any more."""
    with pytest.raises(TemplateDoesNotExist):
        get_template(name)
