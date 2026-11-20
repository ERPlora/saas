"""Guardrails over every public template: no OutfitKit, CDN or runtime icons, no visible native controls, no copy of
the retired local product, shared containers and surfaces, no inline style in the shell, and the closing section of
the download pages written once."""

import re
from pathlib import Path

import pytest

from public.tests.template_pages import COMPONENTS, PUBLIC_STATIC, PUBLIC_TEMPLATES, public_templates, without_comments

pytestmark = pytest.mark.urls("public.tests.urls")

#: The templates under test: the base, its partials, the components, the errors and the cookies.
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
#: Copy of the retired local/offline desktop product: whole phrases, never bare words.
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


def without_noscript(source: str) -> str:
    """``<noscript>`` renders only without JavaScript, when Ionic does not exist: there a plain
    ``<button>`` is the only control that works, so it is the one place a native control is allowed."""
    return NOSCRIPT_BLOCK.sub("", source)


#: The navbar's burger and close button: native, because Ionic 8.8.9 copies the ``aria-*`` of
#: an ``ion-button`` host to its inner button once and never follows ``aria-expanded``.
NAVBAR_NATIVE_BUTTON = re.compile(
    r'<button type="button" class="ep-navbar__(?:burger|close)"[^>]*\bdata-navbar-(?:toggle|close)\b[^>]*>'
)


def without_navbar_buttons(source: str) -> str:
    """The second and last exception to native controls: the navbar's two disclosure buttons."""
    return NAVBAR_NATIVE_BUTTON.sub("", source)


# --- Guardrails over every public template ----------------------------------------------------


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
        if relative == Path("public/partials/navbar.html"):
            source = without_navbar_buttons(source)
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


def test_the_navbar_exception_is_narrow():
    """Only the burger and the close button of the navbar, never any other native button."""
    source = (
        '<button type="button" class="ep-navbar__burger" aria-expanded="false" data-navbar-toggle>'
        '<button type="button" class="ep-navbar__close" data-navbar-close>'
        '<button type="button" class="ep-navbar__burger">'
        '<button type="submit" data-navbar-toggle>'
        '<button type="button" class="other" data-navbar-close>'
    )

    assert len(NATIVE_VISIBLE_TAGS.findall(without_navbar_buttons(source))) == 3


def test_public_navigation_has_no_global_floating_back_control():
    base = (PUBLIC_TEMPLATES / "public" / "public_base.html").read_text(
        encoding="utf-8"
    )

    assert "back_button" not in base
    assert "app_back_bar" not in base
    assert not (PUBLIC_TEMPLATES / "public" / "partials" / "back_button.html").exists()


def test_no_public_template_advertises_the_retired_local_offline_product_or_the_old_demo_host():
    """The demo is ``/demo/``, always by ``{% url 'public:demo' %}``; never the old
    server-side demo host, nor a typed path that the route could leave behind."""
    offenders = []
    for template in public_templates():
        source = without_comments(template.read_text(encoding="utf-8"))
        offenders += [
            f"{template.relative_to(PUBLIC_TEMPLATES)}: {phrase!r}"
            for phrase in RETIRED_LOCAL_OFFLINE_COPY
            if phrase.lower() in source.lower()
        ]
        if re.search(r"demo\.erplora\.com", source):
            offenders.append(f"{template.relative_to(PUBLIC_TEMPLATES)}: links to the old demo host")
        if re.search(r"(href|action)=[\"']/demo", source):
            offenders.append(f"{template.relative_to(PUBLIC_TEMPLATES)}: types the demo's path")

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


# --- The two download pages close with the same section: one partial, not two copies ---------------

DOWNLOAD_PAGES = ("appdist/index.html", "appdist/android.html")


@pytest.mark.parametrize("template", DOWNLOAD_PAGES)
def test_the_download_pages_share_their_closing_section(template):
    """«You need a hub before you need the app» (heading, lead and two buttons) is one partial,
    `appdist/_get_started.html`, not a copy per download page (`dup-guard.sh` would count it): each page tells it
    where its second button goes."""
    source = without_comments((PUBLIC_TEMPLATES / "public" / template).read_text(encoding="utf-8"))

    assert 'id="get-started"' not in source
    assert re.search(r'\{% include "public/appdist/_get_started\.html" with [^%]*\bsee_href=[^%]*\bonly %\}', source)


def test_the_closing_section_of_the_download_pages_is_written_once():
    partial = PUBLIC_TEMPLATES / "public" / "appdist" / "_get_started.html"

    assert partial.exists()
    owners = [
        template.relative_to(PUBLIC_TEMPLATES)
        for template in public_templates()
        if 'id="get-started"' in without_comments(template.read_text(encoding="utf-8"))
    ]
    assert owners == [partial.relative_to(PUBLIC_TEMPLATES)]
