"""The account screens are Vue pages (``accounts/frontend/pages``): the sign-in and its every step, the
launcher and every error of the sign-in. allauth runs headless only, so no sign-in page is a template.
Templates stay only where no screen of the panel is painted: the auto-submitted form of the jump to a hub,
which POSTs the one-time code to the hub (``hub_login_form.html``), the API reference, ReDoc's own page over the
OpenAPI schema in place of ninja's (``api_docs.html``, ACCOUNTS-F34), and the text of the mails allauth sends
(``templates/account/email`` and ``templates/socialaccount/email``)."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

ACCOUNTS_TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "accounts"
PROJECT_TEMPLATES = Path(settings.BASE_DIR) / "templates"


def test_only_the_jump_form_and_the_api_reference_stay_templates():
    assert sorted(path.name for path in ACCOUNTS_TEMPLATES.iterdir()) == ["api_docs.html", "hub_login_form.html"]
    assert get_template("accounts/hub_login_form.html")
    assert get_template("accounts/api_docs.html")


def test_of_allauths_templates_only_the_mails_are_ours():
    """Headless only: allauth renders no page, so the project overrides none (the sign-in's, its layout
    ``base.html`` and Google's interstitial are gone); the mails it sends keep ERPlora's wording."""
    ours = sorted(
        str(path.relative_to(PROJECT_TEMPLATES))
        for folder in ("account", "socialaccount", "mfa", "usersessions")
        for path in (PROJECT_TEMPLATES / folder).rglob("*")
        if path.is_file()
    )

    assert ours == [
        "account/email/base_message.txt",
        "socialaccount/email/account_connected_message.txt",
        "socialaccount/email/account_connected_subject.txt",
    ]
    assert not (PROJECT_TEMPLATES / "base.html").exists()


@pytest.mark.parametrize(
    "name",
    [
        "account/email/base_message.txt",
        "socialaccount/email/account_connected_message.txt",
        "socialaccount/email/account_connected_subject.txt",
    ],
)
def test_the_mails_are_rendered_from_ours(name):
    assert Path(get_template(name).origin.name) == PROJECT_TEMPLATES / name


# --- What Django still paints: our own CSS, no OutfitKit (PLAN §16.11) ---

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
def test_the_error_pages_of_the_sign_in_paint_without_outfitkit():
    """What Django still paints around the sign-in: its error pages (``templates/errors/base.html``)."""
    html = get_template("429.html").render({})

    assert_no_outfitkit(html)
    assert_tokens_defined(html)


@pytest.mark.parametrize(
    "path",
    [
        # The stylesheets only the template sign-in linked (its `base.html`); the error pages keep theirs.
        "css/preflight.css",
        "css/erplora-theme.css",
        "css/native-controls.css",
        "css/erplora-logo.css",
        "css/cloud.css",
        "css/ionic-utilities.css",
        "css/ion-card-content-utilities.css",
        "vendor/ionic/css/padding.css",
        "vendor/ionic/css/text-alignment.css",
        "vendor/ionic/css/flex-utils.css",
        # Iconify and its offline bundle: the SPA bakes its icons (HubIcon), the public web too.
        "vendor/iconify/iconify.min.js",
        "vendor/iconify-icon/iconify-icon.min.js",
        "vendor/iconify-data/icons-offline.js",
    ],
)
def test_the_assets_of_the_template_sign_in_are_gone_from_static(path):
    assert finders.find(path) is None


def test_the_outfitkit_copy_is_gone_from_static():
    assert finders.find("vendor/outfitkit/palettes.css") is None
    assert finders.find("vendor/outfitkit/layout.css") is None
    assert finders.find("css/outfitkit-theme.css") is None


@pytest.mark.parametrize(
    "name",
    [
        "account/_auth_shell_top.html",
        "account/_auth_shell_bottom.html",
        "account/_auth_code_field.html",
        "account/_auth_header.html",
        "account/_auth_styles.html",
        "account/_auth_scripts.html",
    ],
)
def test_the_partials_of_the_retired_template_screens_are_gone(name):
    """The sign-in, 2FA and launcher screens are Vue pages (``AuthShell.vue``, ``CodeField.vue``): nothing
    includes these partials any more."""
    with pytest.raises(TemplateDoesNotExist):
        get_template(name)
