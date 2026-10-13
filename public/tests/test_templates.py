"""The public web's base template, its partials, the component partials and the cookie templates.

Port of ``apps/public/templates/public/public_base.html`` and its partials, ``templates/cookie_consent/``
(origin/develop) and the contracts that pinned them: ``apps/public/tests/test_navbar_session.py`` (4)
and the base-level half of ``apps/public/landing/tests/test_ui_stack_contract.py``. What changed, and
why (spec §8.4, plan §3.b):

* no ``ok-*``: OutfitKit is gone (PLAN §16.11). Its components are HTML + CSS partials
  (``public/components/``, ``ep-*`` classes) and its ``layout.css`` classes are ``ep-*`` too, so the
  contracts that named ``ok-container``/``ok-table-surface``… name the ``ep-*`` classes now;
* no CDN and no runtime icon fetch: one Vite entry (``frontend/public.ts``) and ``{% icon %}``;
* no demo CTA: ``/demo`` is out of scope (block 7). The navbar contract asserted «Try the demo»
  for a visitor; it now asserts it is absent;
* no PWA manifest, back bar or app-shell head: the Tauri app does not open these pages in phase 1;
* the CTA for a customer with a session goes to the SPA's launcher (``/launch``), the old
  ``overview:index`` dashboard does not exist in saas-next; its language comes from the ``_lang``
  cookie (plan §3.a), not from ``UserPreferences``.

The page-specific contracts of ``test_ui_stack_contract.py`` (pricing, legal, help, contact, app,
industries…) move with their pages to the lots that port them.
"""

import re
from datetime import date
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.template import Context, Template
from django.urls import reverse

from accounts.handoff import LAUNCHER
from public.tests.conftest import PUBLIC_CSS, PUBLIC_JS

pytestmark = pytest.mark.urls("public.tests.urls")

ROOT = Path(settings.BASE_DIR)
PUBLIC_TEMPLATES = ROOT / "public" / "templates"
PUBLIC_STATIC = ROOT / "public" / "static" / "public"
COMPONENTS = PUBLIC_TEMPLATES / "public" / "components"
COMPONENT_CSS = PUBLIC_STATIC / "components"
#: The templates this lot owns: the base, its partials, the components, the errors and the cookies.
SHELL_TEMPLATES = [
    PUBLIC_TEMPLATES / "public" / "public_base.html",
    PUBLIC_TEMPLATES / "public" / "404.html",
    PUBLIC_TEMPLATES / "public" / "500.html",
    *sorted((PUBLIC_TEMPLATES / "public" / "partials").glob("*.html")),
    *sorted(COMPONENTS.glob("*.html")),
    *sorted((PUBLIC_TEMPLATES / "cookie_consent").glob("*.html")),
]

NATIVE_VISIBLE_TAGS = re.compile(
    r"<(details|summary|select|textarea|button)(?:\s|>)", re.IGNORECASE
)
RAW_INPUT = re.compile(r"<input\b[^>]*>", re.IGNORECASE)
INPUT_TYPE = re.compile(r"\btype=[\"']([^\"']+)[\"']", re.IGNORECASE)
NOSCRIPT_BLOCK = re.compile(r"<noscript>.*?</noscript>", re.IGNORECASE | re.DOTALL)
#: Copy of the retired local/offline desktop product (ADR-0154): whole phrases, never bare words.
RETIRED_LOCAL_OFFLINE_COPY = (
    "fully offline",
    "100% offline",
    "native app",
    "single device",
    "encrypted cloud backup",
    "Hub Local",
    "offline-first pwa",
    "offline-first design",
    "works offline at the counter",
    "mobile + offline pwa",
    "even offline",
)


def without_comments(source: str) -> str:
    source = re.sub(r"\{#.*?#\}", "", source, flags=re.DOTALL)
    source = re.sub(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", source, flags=re.DOTALL
    )
    return re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)


def without_noscript(source: str) -> str:
    """``<noscript>`` renders only without JavaScript, when Ionic does not exist: there a plain
    ``<button>`` is the only control that works, so it is the one place a native control is allowed."""
    return NOSCRIPT_BLOCK.sub("", source)


def public_templates() -> list[Path]:
    return sorted(PUBLIC_TEMPLATES.rglob("*.html"))


def region(html: str, start: str, end: str) -> str:
    begin = html.index(start)
    return html[begin : html.index(end, begin)]


def navbar_of(html: str) -> str:
    """Only the navbar: «Start free» may also live in a hero or a footer of a page."""
    return region(html, '<nav class="ep-navbar"', "</nav>")


@pytest.fixture
def cookie_groups(db):
    call_command("init_cookie_groups")


def get_page(client, name="test_public_page", **headers):
    response = client.get(reverse(name), **headers)
    assert response.status_code == 200
    return response


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
    """No `/es/` prefix: one URL per page, the language comes from the cookie (spec §7)."""
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


@pytest.mark.django_db
def test_no_cdn_no_runtime_icons_no_pwa_and_no_app_shell(client):
    html = get_page(client).content.decode()

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
def test_body_order_is_dev_banner_navbar_main_footer(client, cookie_groups):
    html = get_page(client).content.decode()

    order = [
        html.index('class="dev-banner"'),
        html.index('<nav class="ep-navbar"'),
        html.index("<main"),
        html.index('<h1 id="test-page">'),
        html.index("</main>"),
        html.index('<footer class="ep-footer"'),
        html.index('id="cookie-consent-banner"'),
    ]
    assert order == sorted(order)


@pytest.mark.django_db
def test_the_dev_banner_announces_the_pre_launch(client):
    banner = region(get_page(client).content.decode(), 'class="dev-banner"', "</div>")

    assert 'role="status"' in banner
    assert "Pre-launch" in banner
    assert (
        "ERPlora is in active development. You're viewing a product preview."
        in banner
    )
    assert "<svg" in banner


@pytest.mark.django_db
def test_server_messages_reach_the_page(client):
    """The contact form and other public forms answer with `messages.*` and a redirect (saas#1754)."""
    html = get_page(client, "test_message_page").content.decode()
    messages = region(html, "data-server-messages", "</div>")

    assert 'data-level="success"' in messages
    assert "Message sent" in messages


@pytest.mark.django_db
def test_no_messages_no_region(client):
    assert "data-server-messages" not in get_page(client).content.decode()


# --- The navbar (port of test_navbar_session.py) ----------------------------------------------


@pytest.mark.django_db
def test_an_anonymous_visitor_is_offered_to_start_free_and_no_demo(client):
    navbar = navbar_of(get_page(client).content.decode())

    assert "Start free" in navbar
    assert f'href="{reverse("account_login")}"' in navbar
    assert f'href="{LAUNCHER}"' not in navbar
    # The demo CTA is out of scope (block 7, plan §3.b): it is never painted.
    assert "Try the demo" not in navbar


@pytest.mark.django_db
def test_a_customer_with_a_session_is_sent_to_the_launcher(client, ana):
    client.force_login(ana)

    navbar = navbar_of(get_page(client).content.decode())

    assert f'href="{LAUNCHER}"' in navbar
    assert "Dashboard" in navbar
    assert "Start free" not in navbar
    assert f'href="{reverse("account_login")}"' not in navbar


@pytest.mark.django_db
def test_the_session_aware_navbar_is_not_servable_from_a_shared_cache(client, ana):
    client.force_login(ana)

    assert "Cookie" in get_page(client).headers.get("Vary", "")


@pytest.mark.django_db
def test_the_navbar_labels_are_translated(client, ana):
    """Through i18n, not hard-coded: the `_lang` cookie picks Spanish (plan §3.a)."""
    client.force_login(ana)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    navbar = navbar_of(get_page(client).content.decode())

    assert "Panel" in navbar
    assert "Dashboard" not in navbar


@pytest.mark.django_db
def test_the_mobile_menu_is_an_ionic_control_with_its_labels(client):
    navbar = navbar_of(get_page(client).content.decode())

    assert "data-navbar-toggle" in navbar
    assert 'aria-controls="ep-navbar-panel"' in navbar
    assert 'aria-expanded="false"' in navbar
    assert 'aria-label="Menu"' in navbar
    assert 'aria-label="Close"' in navbar
    assert 'id="ep-navbar-panel"' in navbar


def test_navbar_and_footer_link_only_to_routes_that_exist():
    """Each later lot adds its links in its turn (plan §3.i); until then nothing points at a page
    that does not exist. An internal link is a `{% url %}`, or the SPA's launcher."""
    for name in ("navbar.html", "nav_links.html", "footer.html", "footer_links.html"):
        source = without_comments(
            (PUBLIC_TEMPLATES / "public" / "partials" / name).read_text(
                encoding="utf-8"
            )
        )
        for href in re.findall(r'href="([^"]*)"', source):
            assert (
                href.startswith(("{% url ", "mailto:", "https://", "{% static "))
                or href == LAUNCHER
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


# --- The page hero ----------------------------------------------------------------------------


def render_partial(template_name: str, **context) -> str:
    return Template(f'{{% include "{template_name}" %}}').render(Context(context))


def test_the_page_hero_paints_eyebrow_title_accent_description_and_note():
    html = render_partial(
        "public/partials/page_hero.html",
        hero_eyebrow="Privacy controls",
        hero_title="Cookie preferences",
        hero_title_accent="Yours",
        hero_description="Choose which cookies.",
        hero_note="A note.",
        hero_compact=True,
        hero_align="split",
        hero_tone="gradient",
    )

    assert 'class="ep-hero ep-hero--split ep-hero--gradient ep-hero--compact"' in html
    assert '<span class="ep-hero__eyebrow">Privacy controls</span>' in html
    assert re.search(
        r'<h1 class="ep-hero__title">\s*Cookie preferences\s*<span class="ep-hero__accent">Yours</span>',
        html,
    )
    assert "Choose which cookies." in html
    assert "A note." in html


def test_the_page_hero_defaults_to_a_centred_soft_hero_without_empty_slots():
    html = render_partial("public/partials/page_hero.html", hero_title="Careers")

    assert 'class="ep-hero ep-hero--center ep-hero--soft"' in html
    assert "ep-hero__eyebrow" not in html
    assert "ep-hero__subtitle" not in html
    assert "ep-hero__actions" not in html


# --- The cookie banner and the cookie settings page -------------------------------------------


@pytest.mark.django_db
def test_the_cookie_banner_appears_until_a_choice_is_made(client, cookie_groups):
    assert 'id="cookie-consent-banner"' in get_page(client).content.decode()

    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    assert 'id="cookie-consent-banner"' not in get_page(client).content.decode()


@pytest.mark.django_db
def test_the_cookie_banner_uses_the_shared_container_and_compact_ionic_actions(
    client, cookie_groups
):
    html = get_page(client).content.decode()
    banner = region(html, 'id="cookie-consent-banner"', "</script>")
    banner_css = (PUBLIC_STATIC / "cookie-consent-banner.css").read_text(
        encoding="utf-8"
    )

    assert 'class="ep-container cookie-consent-layout"' in banner
    assert banner.count("<ion-button") == 3
    for control in ("cookie-customize", "cookie-decline", "cookie-accept"):
        assert f'id="{control}"' in banner
    assert (
        "We use optional cookies to understand traffic and improve ERPlora." in banner
    )
    assert f'href="{reverse("cookie_consent_cookie_group_list")}"' in banner
    assert reverse("cookie_consent_accept") in banner
    assert reverse("cookie_consent_decline") in banner
    assert "X-CSRFToken" in banner
    for control in ("customize", "decline", "accept"):
        assert f"activateOnKeyboard({control}" in banner
    assert ".cookie-consent-actions ion-button" in banner_css
    assert "min-height: 2.75rem" in banner_css


@pytest.mark.django_db
def test_the_cookie_settings_page_lists_every_group_with_its_cookies(
    client, cookie_groups
):
    from cookie_consent.models import CookieGroup

    response = client.get(reverse("cookie_consent_cookie_group_list"))
    html = response.content.decode()

    assert response.status_code == 200
    assert '<nav class="ep-navbar"' in html
    assert "Cookie preferences" in html
    assert 'class="ep-container ep-section-content"' in html
    assert 'class="public-preference-list"' in html
    for group in CookieGroup.objects.all():
        assert group.name in html
        assert group.description in html
    # the required group is always active; the others have a toggle with their state
    assert "Always active" in html
    assert (
        html.count("<ion-toggle")
        == CookieGroup.objects.filter(is_required=False).count()
    )
    assert "data-cookie-state" in html
    assert 'class="ep-table-surface"' in html
    assert 'class="ep-table-stack"' in html
    assert 'data-title="Cookie name"' in html
    # the page is the decision centre: never the banner on top of it
    assert 'id="cookie-consent-banner"' not in html


@pytest.mark.django_db
def test_the_cookie_settings_page_says_so_when_there_are_no_groups(client):
    html = client.get(reverse("cookie_consent_cookie_group_list")).content.decode()

    assert "No cookie categories are currently configured." in html
    assert 'class="ep-inline-feedback' in html


@pytest.mark.django_db
def test_each_toggle_posts_its_group_to_accept_or_decline(client, cookie_groups):
    html = client.get(reverse("cookie_consent_cookie_group_list")).content.decode()
    script = next(script for script in re.findall(r"<script\b.*?</script>", html, re.S) if "ion-toggle.cookie-toggle" in script)

    assert reverse("cookie_consent_accept") in script
    assert reverse("cookie_consent_decline") in script
    assert "cookie_groups" in script
    assert "csrfmiddlewaretoken" in script
    assert 'data-group="analytical"' in html


def test_the_cookie_templates_keep_the_shared_patterns():
    page = (PUBLIC_TEMPLATES / "cookie_consent" / "cookiegroup_list.html").read_text(
        encoding="utf-8"
    )
    group = (PUBLIC_TEMPLATES / "cookie_consent" / "_cookie_group.html").read_text(
        encoding="utf-8"
    )
    public_css = (PUBLIC_STATIC / "public-landing.css").read_text(encoding="utf-8")

    assert 'include "public/partials/page_hero.html"' in page
    assert "{% block cookie_banner %}{% endblock %}" in page
    # Stored in English by init_cookie_groups, translated by the catalogue.
    assert "{% translate cookie_group.name as group_name %}" in group
    assert "{% translate cookie_group.description %}" in group
    assert "{% translate cookie.description %}{% else %}—{% endif %}" in group
    assert "data-title=\"{% trans 'Cookie name' %}\"" in group
    assert ".public-preference-list" in public_css
    assert "ion-toggle.cookie-toggle" in public_css
    assert "main ion-toggle:focus-visible" in public_css


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
    needs the database cannot report that the database is down."""
    with django_assert_num_queries(0):
        response = client.get(reverse("test_error_page", args=[500]))
    html = response.content.decode()

    assert response.status_code == 500
    assert "Something went wrong" in html
    assert f'href="{reverse("home")}"' in html
    assert "ep-navbar" not in html
    assert "cookie-consent-banner" not in html
    assert f"/static/spa/{PUBLIC_JS}" in html


# --- Guardrails over every public template (base half of test_ui_stack_contract.py) -----------


def test_no_outfitkit_and_no_cdn_in_any_public_template():
    offenders = []
    for template in public_templates():
        source = without_comments(template.read_text(encoding="utf-8"))
        if re.search(r"<ok-|\bok-[a-z]", source):
            offenders.append(f"{template.relative_to(PUBLIC_TEMPLATES)}: ok-*")
        for gone in (
            "cdn.jsdelivr.net",
            "api.iconify.design",
            "<iconify-icon",
            "<ion-icon",
            "ionic.esm.js",
            "htmx",
        ):
            if gone in source:
                offenders.append(f"{template.relative_to(PUBLIC_TEMPLATES)}: {gone}")

    assert offenders == [], (
        "use ep-* partials, {% icon %} and the Vite entry:\n" + "\n".join(offenders)
    )


def test_public_templates_do_not_use_visible_native_controls():
    offenders = []
    for template in public_templates():
        source = without_noscript(
            without_comments(template.read_text(encoding="utf-8"))
        )
        relative = template.relative_to(PUBLIC_TEMPLATES)
        offenders += [
            f"{relative}: <{match.group(1).lower()}>"
            for match in NATIVE_VISIBLE_TAGS.finditer(source)
        ]
        for tag in RAW_INPUT.findall(source):
            kind = (
                INPUT_TYPE.search(tag).group(1) if INPUT_TYPE.search(tag) else "text"
            ).lower()
            if kind != "hidden":
                offenders.append(f'{relative}: <input type="{kind}">')

    assert offenders == [], (
        "use ion-* instead of visible native controls:\n" + "\n".join(offenders)
    )


def test_the_noscript_exception_is_narrow():
    source = '<button id="outside">a</button><noscript><button id="inside">b</button></noscript>'

    stripped = without_noscript(source)

    assert 'id="inside"' not in stripped
    assert 'id="outside"' in stripped


def test_public_navigation_has_no_global_floating_back_control():
    base = (PUBLIC_TEMPLATES / "public" / "public_base.html").read_text(
        encoding="utf-8"
    )

    assert "back_button" not in base
    assert "app_back_bar" not in base
    assert not (PUBLIC_TEMPLATES / "public" / "partials" / "back_button.html").exists()


def test_no_public_template_advertises_the_retired_local_offline_product_or_the_demo():
    offenders = []
    for template in public_templates():
        source = without_comments(template.read_text(encoding="utf-8"))
        offenders += [
            f"{template.relative_to(PUBLIC_TEMPLATES)}: {phrase!r}"
            for phrase in RETIRED_LOCAL_OFFLINE_COPY
            if phrase.lower() in source.lower()
        ]
        if re.search(
            r"href=[\"']/demo/?[\"']|\{% url ['\"]demo['\"]|demo\.erplora\.com|Try the demo",
            source,
        ):
            offenders.append(
                f"{template.relative_to(PUBLIC_TEMPLATES)}: links to the demo"
            )

    assert offenders == []


def test_public_templates_use_shared_containers_and_surfaces():
    offenders = []
    for template in public_templates():
        source = without_comments(template.read_text(encoding="utf-8"))
        for class_value in re.findall(r'class=["\']([^"\']*)["\']', source):
            classes = set(class_value.split())
            if "mx-auto" in classes and {"px-4", "lg:px-8"} & classes:
                offenders.append(
                    f"{template.relative_to(PUBLIC_TEMPLATES)}: {class_value} → .ep-container"
                )
            if {"section-soft", "bg-surface-2/30"} & classes:
                offenders.append(
                    f"{template.relative_to(PUBLIC_TEMPLATES)}: {class_value} → .ep-section--soft"
                )

    assert offenders == []


def test_the_shell_templates_carry_no_inline_style():
    """Their look lives in the stylesheets of the Vite entry: no `style=` and no `<style>` block."""
    offenders = []
    for template in SHELL_TEMPLATES:
        source = without_comments(template.read_text(encoding="utf-8"))
        if 'style="' in source or "<style" in source:
            offenders.append(str(template.relative_to(PUBLIC_TEMPLATES)))

    assert offenders == []


def test_public_ios_outline_fields_keep_a_visible_shared_boundary():
    css = (PUBLIC_STATIC / "public-landing.css").read_text(encoding="utf-8")

    assert 'ion-input.ios[fill="outline"]' in css
    assert 'ion-textarea.ios[fill="outline"]' in css
    assert "focus-within" in css


# --- Layout classes and component partials (spec §8.4) ----------------------------------------

#: The OutfitKit layout.css classes the public templates used, rebuilt as `ep-*`.
LAYOUT_CLASSES = (
    "ep-container",
    "ep-container-fluid",
    "ep-grid",
    "ep-col",
    "ep-md-4",
    "ep-md-8",
    "ep-grid-cards",
    "ep-section",
    "ep-section-content",
    "ep-section--compact",
    "ep-section--featured",
    "ep-section--divider",
    "ep-section--soft",
    "ep-section--center",
    "ep-section-head",
    "ep-eyebrow",
    "ep-section-title",
    "ep-section-sub",
    "ep-search",
    "ep-accordion",
    "ep-accordion-header",
    "ep-accordion-body",
    "ep-prose",
    "ep-display-title",
    "ep-page-title",
    "ep-intro",
    "ep-body",
    "ep-table-stack",
    "ep-table-surface",
    "ep-table-group",
)


def test_layout_css_defines_every_ep_class_over_ep_tokens():
    css = (PUBLIC_STATIC / "layout.css").read_text(encoding="utf-8")

    for name in LAYOUT_CLASSES:
        assert re.search(rf"\.{re.escape(name)}(?![\w-])", css), name
    assert "--ep-container-max" in css
    assert "--ep-type-section-title-size" in css


def test_no_outfitkit_token_or_class_is_left_in_the_public_stylesheets():
    for sheet in PUBLIC_STATIC.rglob("*.css"):
        # Comments may name the OutfitKit component a rule was ported from; rules and tokens may not.
        text = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
        assert "--ok-" not in text, sheet
        assert not re.search(r"(?<![\w-])\.?ok-[a-z]", text), sheet


#: Every OutfitKit component the public templates used, as a partial (spec §8.4). The hero, the
#: navbar and the footer are the base's partials.
COMPONENT_PARTIALS = (
    "reveal",
    "feature_card",
    "status_pill",
    "bento",
    "bento_item",
    "cta_band",
    "product_card",
    "stat",
    "inline_feedback",
    "pricing_card",
    "logo_cloud",
    "empty_state",
)


def test_every_component_has_its_partial_its_usage_comment_and_its_stylesheet():
    for name in COMPONENT_PARTIALS:
        source = (COMPONENTS / f"{name}.html").read_text(encoding="utf-8")
        assert re.search(
            r"\{%\s*comment\s*%\}.*Usage:.*\{%\s*include \"public/components/",
            source,
            re.S,
        ), name
        assert (COMPONENT_CSS / f"{name.replace('_', '-')}.css").is_file(), name
    for name in ("hero", "navbar", "footer"):
        assert (COMPONENT_CSS / f"{name}.css").is_file(), name


def test_component_stylesheets_only_style_their_own_ep_block():
    for sheet in COMPONENT_CSS.glob("*.css"):
        block = f"ep-{sheet.stem}"
        selectors = re.findall(
            r"(?:^|})\s*([^{}@]+)\{",
            re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S),
        )
        for selector in selectors:
            if selector.strip() in {"from", "to"} or re.fullmatch(
                r"\s*\d+%\s*", selector
            ):
                continue
            assert block in selector, f"{sheet.name}: {selector.strip()}"


def test_feature_card_as_a_link_with_its_icon():
    html = render_partial(
        "public/components/feature_card.html",
        icon="lucide:check",
        eyebrow="POS",
        heading="Sell faster",
        body="Text",
        href="/features/",
    )

    assert html.strip().startswith('<a class="ep-feature-card" href="/features/">')
    assert '<span class="ep-feature-card__icon"><svg' in html
    assert '<h3 class="ep-feature-card__title">Sell faster</h3>' in html
    assert '<span class="ep-feature-card__eyebrow">POS</span>' in html


def test_feature_card_without_a_link_is_a_block():
    html = render_partial(
        "public/components/feature_card.html", heading="Sell faster", glass=True
    )

    assert html.strip().startswith(
        '<div class="ep-feature-card ep-feature-card--glass">'
    )


def test_status_pill_tones_icon_and_hook():
    html = render_partial(
        "public/components/status_pill.html",
        tone="success",
        label="Enabled",
        icon="checkmark-circle-outline",
        hook="cookie-state",
    )

    assert 'class="ep-status-pill ep-status-pill--success"' in html
    assert "data-cookie-state" in html
    assert "<svg" in html and "Enabled" in html
    assert "ep-status-pill--neutral" in render_partial(
        "public/components/status_pill.html", label="Off"
    )
    assert 'class="ep-status-pill__dot"' in render_partial(
        "public/components/status_pill.html", label="x", dot=True
    )


def test_bento_grid_and_item():
    item = render_partial(
        "public/components/bento_item.html",
        cols=3,
        rows=2,
        tone="primary",
        heading="Inventory",
        body="Stock",
        href="/x/",
    )
    grid = render_partial(
        "public/components/bento.html",
        items_template="public/components/stat.html",
        cols=6,
        cols_md=4,
    )

    assert (
        'class="ep-bento-item ep-bento-item--c3 ep-bento-item--r2 ep-bento-item--primary"'
        in item
    )
    assert '<a class="ep-bento-item__cell" href="/x/">' in item
    assert 'class="ep-bento ep-bento--c6 ep-bento--md4"' in grid


def test_cta_band_with_its_actions():
    html = render_partial(
        "public/components/cta_band.html",
        eyebrow="Start",
        heading="Ready?",
        subheading="Free plan.",
        actions_template="public/components/stat.html",
        variant="soft",
    )

    assert 'class="ep-cta-band ep-cta-band--soft"' in html
    assert '<h2 class="ep-cta-band__title">Ready?</h2>' in html
    assert 'class="ep-cta-band__actions"' in html


def test_product_card_with_badge_price_and_arrow():
    html = render_partial(
        "public/components/product_card.html",
        icon="lucide:check",
        category="Sales",
        name="POS",
        badge="Free",
        price="0 €",
        href="/apps/pos/",
        body="Sell",
    )

    assert html.strip().startswith('<a class="ep-product-card" href="/apps/pos/">')
    assert '<span class="ep-product-card__badge">Free</span>' in html
    assert '<span class="ep-product-card__price">0 €</span>' in html
    assert 'class="ep-product-card__go"' in html


def test_stat_label_value_hint():
    html = render_partial(
        "public/components/stat.html", label="Apps", value="42", hint="and growing"
    )

    assert '<p class="ep-stat__label">Apps</p>' in html
    assert '<p class="ep-stat__value">42</p>' in html
    assert '<p class="ep-stat__hint">and growing</p>' in html


def test_inline_feedback_is_a_status_with_the_tone_icon():
    html = render_partial(
        "public/components/inline_feedback.html",
        tone="danger",
        heading="Error",
        message="Try again",
    )

    assert 'class="ep-inline-feedback ep-inline-feedback--danger" role="status"' in html
    assert "<svg" in html
    assert '<div class="ep-inline-feedback__heading">Error</div>' in html
    assert "Try again" in html
    assert "ep-inline-feedback--info" in render_partial(
        "public/components/inline_feedback.html", message="x"
    )


def test_pricing_card_featured_with_features():
    html = render_partial(
        "public/components/pricing_card.html",
        name="Standard",
        price="29 €",
        period="/month",
        description="For teams",
        features=["POS", "Invoices"],
        featured=True,
    )

    assert 'class="ep-pricing-card ep-pricing-card--featured"' in html
    assert '<span class="ep-pricing-card__badge">Popular</span>' in html
    assert html.count('class="ep-pricing-card__check"') == 2
    assert '<span class="ep-pricing-card__amount">29 €</span>' in html


def test_logo_cloud_and_empty_state_and_reveal():
    cloud = render_partial(
        "public/components/logo_cloud.html",
        label="Trusted by",
        logos_template="public/components/stat.html",
    )
    empty = render_partial(
        "public/components/empty_state.html",
        heading="Nothing here",
        message="Try again",
    )
    reveal = render_partial(
        "public/components/reveal.html",
        content_template="public/components/stat.html",
        variant="left",
        delay=80,
    )

    assert '<div class="ep-logo-cloud__label">Trusted by</div>' in cloud
    assert (
        'class="ep-empty-state"' in empty
        and "<svg" in empty
        and "Nothing here" in empty
    )
    assert '<div class="ep-reveal" data-reveal="left" data-reveal-delay="80">' in reveal


def test_the_open_mobile_panel_is_not_trapped_by_the_glass_bar():
    """`backdrop-filter` makes the navbar the containing block of its fixed descendants: with it on,
    the side panel and its backdrop were laid out inside the 50 px bar instead of the viewport (seen
    in Chrome at 390 px). The open navbar drops the glass."""
    css = re.sub(r"/\*.*?\*/", "", (COMPONENT_CSS / "navbar.css").read_text(encoding="utf-8"), flags=re.S)
    open_rule = re.search(r"\.ep-navbar\[data-open\]\s*\{([^}]*)\}", css)

    assert "backdrop-filter" in css, "the closed bar is glass"
    assert open_rule, "no rule for the open navbar"
    assert "backdrop-filter: none" in open_rule.group(1)
    assert "-webkit-backdrop-filter: none" in open_rule.group(1)
