"""The public web's base template and its partials as a page paints them: the head, the colour mode, the body, the
navbar, the footer and the error pages.

* No CDN and no runtime icon fetch: one Vite entry (``frontend/public.ts``) and ``{% icon %}``.
* The navbar offers «Try the demo» (``/demo/``, public/demo.py) to a visitor, not to a customer with a session.
* No PWA manifest nor app-shell head.
* The CTA for a customer with a session goes to the SPA's launcher (``/launch``); its language comes from the
  ``_lang`` cookie.
"""

import re
from datetime import date

import pytest
from django.conf import settings
from django.urls import NoReverseMatch, reverse

from accounts.adapters import SPA_LOGIN
from accounts.handoff import LAUNCHER
from public.sitemaps import SITEMAPS
from public.tests.conftest import PUBLIC_CSS, PUBLIC_JS, without_tokens
from public.tests.template_pages import (
    PUBLIC_STATIC,
    PUBLIC_TEMPLATES,
    ROOT,
    get_page,
    public_templates,
    region,
    without_comments,
)

pytestmark = pytest.mark.urls("public.tests.urls")

PUBLIC_CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.po"
SITEMAP_HOST = "localhost:8001"

#: The strip that said ERPlora was in development, with its English and Spanish copy.
RETIRED_PRE_LAUNCH_STRIP = (
    "dev-banner",
    "dev_banner",
    "Pre-launch",
    "Prelanzamiento",
    "active development",
    "pleno desarrollo",
    "product preview",
    "vista previa del producto",
)


def navbar_of(html: str) -> str:
    """Only the navbar: «Start free» may also live in a hero or a footer of a page."""
    return region(html, '<nav class="ep-navbar"', "</nav>")


def sitemap_locations():
    for sitemap_class in SITEMAPS.values():
        sitemap = sitemap_class(SITEMAP_HOST)
        yield from map(sitemap.location, sitemap.items())


# --- The head ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_head_carries_description_open_graph_twitter_favicon_and_canonical(client):
    html = get_page(client).content.decode()
    url = "https://testserver/test-public-page/"

    assert '<html lang="en"' in html
    assert (
        '<meta name="description" content="ERPlora - The ERP that adapts to your business'
        in html
    )
    assert '<meta property="og:type" content="website">' in html
    assert (
        f'<meta property="og:url" content="http://testserver/test-public-page/">'
        in html
    )
    assert (
        '<meta property="og:title" content="ERPlora · The modular ERP/POS for your business">'
        in html
    )
    assert (
        '<meta property="og:image" content="https://testserver/static/public/img/og-image.png">'
        in html
    )
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert (
        '<link rel="icon" type="image/x-icon" href="/static/img/favicon.ico">' in html
    )
    assert (
        '<link rel="apple-touch-icon" href="/static/public/img/apple-touch-icon.png">'
        in html
    )
    assert f'<link rel="canonical" href="{url}">' in html
    assert "<title>Test page</title>" in html


@pytest.mark.django_db
def test_hreflang_points_en_es_and_x_default_at_the_same_url(client):
    """No `/es/` prefix: one URL per page, the language comes from the cookie."""
    html = get_page(client).content.decode()
    url = "https://testserver/test-public-page/"

    for lang in ("en", "es", "x-default"):
        assert f'<link rel="alternate" hreflang="{lang}" href="{url}">' in html


@pytest.mark.django_db
def test_the_html_language_follows_the_request(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    html = get_page(client).content.decode()

    assert '<html lang="es"' in html
    assert "El ERP que se adapta a tu negocio" in html


def test_pages_can_fill_the_seo_blocks():
    base = (PUBLIC_TEMPLATES / "public" / "public_base.html").read_text(
        encoding="utf-8"
    )

    for block in (
        "title",
        "meta_description",
        "og_title",
        "og_description",
        "og_image",
        "twitter_title",
        "twitter_description",
        "twitter_image",
        "canonical_url",
        "hreflang",
        "meta_robots",
        "extra_seo",
        "extra_css",
        "extra_head_scripts",
        "content",
        "page_content",
        "cookie_banner",
        "scripts",
    ):
        assert f"{{% block {block} %}}" in base, block


@pytest.mark.django_db
def test_css_and_js_come_from_the_public_vite_entry_with_the_nonce(client):
    response = get_page(client)
    html = response.content.decode()
    nonce = re.search(
        r"'nonce-([^']+)'", response.headers["Content-Security-Policy"]
    ).group(1)

    # The build of the public entry (public/tests/conftest.py), not the SPA's.
    assert (
        f'<script type="module" src="/static/spa/{PUBLIC_JS}" nonce="{nonce}">' in html
    )
    assert f'<link rel="stylesheet" href="/static/spa/{PUBLIC_CSS}">' in html
    assert "assets/main-" not in html
    # every inline script carries the nonce too
    for tag in re.findall(r"<script\b[^>]*>", html):
        assert f'nonce="{nonce}"' in tag, tag


# --- The colour mode (light, dark or the system's), as the panel paints it --------------------


def _html_tag(html: str) -> str:
    return re.search(r"<html\b[^>]*>", html).group(0)


@pytest.mark.django_db
def test_a_visitor_gets_the_system_mode_and_no_dark_class_from_the_server(client):
    """``system`` (no account, no cookie): the head's script follows ``prefers-color-scheme``."""
    html_tag = _html_tag(get_page(client).content.decode())

    assert 'data-ep-theme="system"' in html_tag
    assert "ion-palette-dark" not in html_tag


@pytest.mark.django_db
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_theme_cookie_paints_the_public_web_from_the_server(client, mode):
    """A visitor without an account gets the ``theme`` cookie: a dark choice needs no script and never
    flashes light."""
    client.cookies["theme"] = mode

    html_tag = _html_tag(get_page(client).content.decode())

    assert f'data-ep-theme="{mode}"' in html_tag
    assert ("ion-palette-dark" in html_tag) is (mode == "dark")


@pytest.mark.django_db
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_an_account_gets_the_mode_it_chose_in_the_panel(client, ana, mode):
    """Account → Preferences is the panel's mode: the public web paints the same one, from the
    server, so a dark choice needs no script and never flashes light."""
    from accounts.models import UserPreferences

    UserPreferences.objects.create(user=ana, theme_mode=mode)
    client.force_login(ana)

    html_tag = _html_tag(get_page(client).content.decode())

    assert f'data-ep-theme="{mode}"' in html_tag
    assert ("ion-palette-dark" in html_tag) is (mode == "dark")


@pytest.mark.django_db
def test_the_head_resolves_the_system_mode_before_the_first_stylesheet(client):
    """No flash: an inline script, with the nonce, darkens <html> before any CSS is parsed. It reads
    the mode from <html> and the system's preference, as frontend/public.ts does afterwards."""
    html = get_page(client).content.decode()
    head = region(html, "<head>", "</head>")
    script = re.search(
        r"<script nonce=\"[^\"]+\">(?:(?!</script>).)*ion-palette-dark(?:(?!</script>).)*</script>",
        head,
        re.S,
    )

    assert script is not None
    assert "data-ep-theme" in script.group(0)
    assert "(prefers-color-scheme: dark)" in script.group(0)
    assert script.start() < head.index('<link rel="stylesheet"')


@pytest.mark.django_db
def test_no_cdn_no_runtime_icons_no_pwa_and_no_app_shell(client, tokens_spelling):
    tokens_spelling("htmx")
    html = without_tokens(get_page(client).content.decode())

    for gone in (
        "cdn.jsdelivr.net",
        "api.iconify.design",
        "iconify",
        "ionic.esm.js",
        "htmx",
        'rel="manifest"',
        "in-app-shell",
        "data-app-only",
        "outfitkit",
        "<ok-",
    ):
        assert gone not in html, gone


# --- The body ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_body_order_is_navbar_main_footer_with_nothing_above_the_navbar(client, cookie_groups):
    html = get_page(client).content.decode()

    assert region(html, "<body>", '<nav class="ep-navbar"').removeprefix("<body>").strip() == ""
    order = [
        html.index('<nav class="ep-navbar"'),
        html.index("<main"),
        html.index('<h1 id="test-page">'),
        html.index("</main>"),
        html.index('<footer class="ep-footer"'),
        html.index('id="cookie-consent-banner"'),
    ]
    assert order == sorted(order)


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_no_public_page_carries_the_pre_launch_strip(client, language):
    """ERPlora is on sale: no page of the public web says it is a preview in development."""
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    pages = [(location, 200) for location in sitemap_locations()]
    pages += [(reverse("test_public_page"), 200), ("/pricing/no-such-plan/", 404)]

    offenders = []
    for location, status in pages:
        response = client.get(location, HTTP_HOST=SITEMAP_HOST)
        assert response.status_code == status, location
        html = response.content.decode().lower()
        offenders += [
            f"{location}: {marker!r}" for marker in RETIRED_PRE_LAUNCH_STRIP if marker.lower() in html
        ]

    assert reverse("public:home") in dict(pages)
    assert offenders == []


def test_no_public_template_stylesheet_or_catalog_keeps_the_pre_launch_strip():
    sources = [*public_templates(), *sorted(PUBLIC_STATIC.rglob("*.css")), PUBLIC_CATALOG]

    offenders = [
        f"{source.relative_to(ROOT)}: {marker!r}"
        for source in sources
        for marker in RETIRED_PRE_LAUNCH_STRIP
        if marker.lower() in without_comments(source.read_text(encoding="utf-8")).lower()
    ]

    assert offenders == []


@pytest.mark.django_db
def test_server_messages_reach_the_page(client):
    """The contact form and other public forms answer with `messages.*` and a redirect."""
    html = get_page(client, "test_message_page").content.decode()
    messages = region(html, "data-server-messages", "</div>")

    assert 'data-level="success"' in messages
    assert "Message sent" in messages


@pytest.mark.django_db
def test_no_messages_no_region(client):
    assert "data-server-messages" not in get_page(client).content.decode()


# --- The navbar -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_anonymous_visitor_is_offered_to_start_free_and_the_demo(client):
    navbar = navbar_of(get_page(client).content.decode())

    # The sign-in is the launcher's (``/launch``), which also signs up.
    assert "Start free" in navbar
    assert f'href="{LAUNCHER}"' in navbar
    assert "Dashboard" not in navbar
    # The demo: a look without an account.
    assert "Try the demo" in navbar
    assert f'href="{reverse("public:demo")}"' in navbar


@pytest.mark.django_db
def test_a_customer_with_a_session_is_sent_to_the_launcher(client, ana):
    client.force_login(ana)

    navbar = navbar_of(get_page(client).content.decode())

    assert f'href="{LAUNCHER}"' in navbar
    assert "Dashboard" in navbar
    assert "Start free" not in navbar
    assert "Try the demo" not in navbar


@pytest.mark.django_db
def test_the_session_aware_navbar_is_not_servable_from_a_shared_cache(client, ana):
    client.force_login(ana)

    assert "Cookie" in get_page(client).headers.get("Vary", "")


@pytest.mark.django_db
def test_the_navbar_labels_are_translated(client, ana):
    """Through i18n, not hard-coded: the `_lang` cookie picks Spanish."""
    client.force_login(ana)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    navbar = navbar_of(get_page(client).content.decode())

    assert "Panel" in navbar
    assert "Dashboard" not in navbar


def opening_tag(html: str, marker: str, *, also: str = "") -> str:
    """The opening tag of the one element that carries ``marker`` (and ``also``, if given)."""
    tags = [
        tag
        for tag in re.findall(rf"<[a-z-]+\b[^>]*\b{marker}\b[^>]*>", html)
        if also in tag
    ]
    assert len(tags) == 1, tags
    return tags[0]


@pytest.mark.django_db
def test_the_mobile_menu_is_a_native_button_with_its_labels(client):
    """Ionic 8.8.9 copies the ``aria-*`` of an ``ion-button`` host to its inner button once and never follows
    ``aria-expanded`` again: a screen reader would hear «collapsed» with the panel open."""
    navbar = navbar_of(get_page(client).content.decode())
    burger = opening_tag(navbar, "data-navbar-toggle")
    close = opening_tag(navbar, "data-navbar-close", also="ep-navbar__close")

    assert burger.startswith('<button type="button"')
    assert 'aria-controls="ep-navbar-panel"' in burger
    assert 'aria-expanded="false"' in burger
    assert 'aria-label="Menu"' in burger
    assert close.startswith('<button type="button"')
    assert 'aria-label="Close"' in close
    assert 'id="ep-navbar-panel"' in navbar


@pytest.mark.django_db
def test_the_mobile_menu_opens_from_an_inline_script_with_the_nonce(client):
    """Pressed before ``frontend/public.ts`` arrives, the burger still opens the panel: the script that opens it
    comes with the navbar, right after it, and runs as the page is parsed; under the CSP, only with the nonce."""
    response = get_page(client)
    html = response.content.decode()
    nonce = re.search(r"'nonce-([^']+)'", response.headers["Content-Security-Policy"]).group(1)

    after_the_navbar = html[html.index("</nav>", html.index('<nav class="ep-navbar"')) + len("</nav>") :]
    script = re.match(r"\s*<script nonce=\"([^\"]+)\">((?:(?!</script>).)*)</script>", after_the_navbar, re.DOTALL)

    assert script is not None
    assert script.group(1) == nonce
    assert "data-navbar-toggle" in script.group(2)


#: A literal path in a template: an ``href`` or the fallback of a ``|default``.
LITERAL_PATH = re.compile(r"""(?:href=|default:)["'](/[^"'{]*)["']""")


def literal_paths_to_public_routes(source: str) -> list[str]:
    """The literal paths of ``source`` that land on a route of the public web (``/`` included)."""
    from public.urls import PUBLIC_PREFIXES

    own = {"", *PUBLIC_PREFIXES}
    return [
        path
        for path in LITERAL_PATH.findall(source)
        if not path.startswith("/static/") and path.strip("/").split("/")[0] in own
    ]


def test_no_template_writes_the_path_of_a_public_route():
    """A route of the public web is a ``{% url %}``: a literal path survives a rename of the route and points at a
    404."""
    offenders = [
        f"{template.relative_to(PUBLIC_TEMPLATES)}: {path}"
        for template in public_templates()
        for path in literal_paths_to_public_routes(
            without_comments(template.read_text(encoding="utf-8"))
        )
    ]

    assert offenders == []


def test_the_literal_path_sweep_catches_what_was_written():
    """Positive control: the shapes the templates actually had, and what it must let through."""
    source = (
        '<ion-button href="/contact/">'
        "{% include 'card.html' with href=\"/contact/\" %}"
        "href=pricing_url|default:'/pricing/'"
        "{{ contact_url|default:'/contact/' }}"
        '<a href="/">'
        '<img src="/static/public/img/logo.png"><a href="/static/public/x.pdf">'
        '<a href="/launch"><a href="{% url \'public:contact\' %}"><a href="https://erplora.com/">'
    )

    assert literal_paths_to_public_routes(source) == [
        "/contact/",
        "/contact/",
        "/pricing/",
        "/contact/",
        "/",
    ]


def names_a_route(href: str) -> bool:
    try:
        reverse(href)
    except NoReverseMatch:
        return False
    return True


def test_navbar_and_footer_link_only_to_routes_that_exist():
    """Nothing points at a page that does not exist. An internal link is a `{% url %}` or the name of a route (the
    ``href`` of a ``{% button %}``), or a page of the SPA: its launcher or its sign-in."""
    for name in ("navbar.html", "nav_links.html", "footer.html", "footer_links.html"):
        source = without_comments(
            (PUBLIC_TEMPLATES / "public" / "partials" / name).read_text(
                encoding="utf-8"
            )
        )
        for href in re.findall(r'href="([^"]*)"', source):
            assert (
                href.startswith(("{% url ", "mailto:", "https://", "{% static "))
                or href in (LAUNCHER, SPA_LOGIN)
                or names_a_route(href)
            ), f"{name}: {href}"


# --- The footer -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_footer_brand_social_support_and_bottom_bar(client, settings):
    settings.SUPPORT_EMAIL = "help@example.com"
    footer = region(
        get_page(client).content.decode(), '<footer class="ep-footer"', "</footer>"
    )

    assert "One ERP. Infinite configurations. Yours." in footer
    assert "Your business. Your rules." in footer
    for url, label in (
        ("https://www.facebook.com/erplora", "Facebook"),
        ("https://x.com/erplora", "X (Twitter)"),
        ("https://www.linkedin.com/company/erplora", "LinkedIn"),
        ("https://www.tiktok.com/@erplora", "TikTok"),
    ):
        assert (
            f'href="{url}" target="_blank" rel="noopener" aria-label="{label}"'
            in footer
        )
    assert footer.count("<svg") >= 4
    assert 'href="mailto:help@example.com"' in footer
    assert f'href="{reverse("cookie_consent_cookie_group_list")}"' in footer
    assert f"© {date.today().year} erplora.com. All rights reserved." in footer


# --- The error pages --------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_404_page_is_a_public_page_with_a_way_home(client):
    response = client.get(reverse("test_error_page", args=[404]))
    html = response.content.decode()

    assert response.status_code == 404
    assert '<nav class="ep-navbar"' in html
    assert "Page not found" in html
    assert f'href="{reverse("home")}"' in html
    assert '<meta name="robots" content="noindex">' in html


@pytest.mark.django_db
def test_the_500_page_stays_up_without_the_database(client, django_assert_num_queries):
    """No navbar (session), no cookie banner and no analytics (cookie groups): an error page that
    needs the database cannot report that the database is down.

    The maintenance switch every request reads (``base.maintenance``) is kept in the cache and, when it
    cannot be read, leaves the site open (the next test): read once here, so only the page itself is counted."""
    from base.queries import maintenance_state

    maintenance_state()
    with django_assert_num_queries(0):
        response = client.get(reverse("test_error_page", args=[500]))
    html = response.content.decode()

    assert response.status_code == 500
    assert "Something went wrong" in html
    assert f'href="{reverse("home")}"' in html
    assert "ep-navbar" not in html
    assert "cookie-consent-banner" not in html
    assert f"/static/spa/{PUBLIC_JS}" in html


@pytest.mark.django_db
def test_the_500_page_stays_up_when_the_maintenance_switch_cannot_be_read(client, monkeypatch):
    """The database down for the maintenance switch too: the site stays open and the 500 page answers."""
    from django.core.cache import cache
    from django.db import DatabaseError

    from base import queries

    def unreadable():
        raise DatabaseError("connection refused")

    cache.clear()
    monkeypatch.setattr(queries, "_read_maintenance", unreadable)

    response = client.get(reverse("test_error_page", args=[500]))

    assert response.status_code == 500
    assert "Something went wrong" in response.content.decode()
