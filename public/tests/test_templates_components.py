"""The public web's component partials (``public/components/``) and the page hero, painted on their own, and the
layout classes and component stylesheets they rely on.

* No ``ok-*``: the components are HTML + CSS partials (``ep-*`` classes) and the layout classes are ``ep-*`` too.
"""

import re

import pytest
from django.template import Context, Template

from public.tests.template_pages import COMPONENT_CSS, COMPONENTS, PUBLIC_STATIC, region

pytestmark = pytest.mark.urls("public.tests.urls")


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


# --- Layout classes and component partials ----------------------------------------------------

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


#: Every OutfitKit component the public templates used, as a partial. The hero, the
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


def test_no_public_stylesheet_washes_a_band_with_ionics_light_colour():
    """``--ion-color-light`` stays light in dark (theme.css pins it, so the CTA band's
    ``color="light"`` buttons stay white): a background mixed from it turned every page hero grey on
    a dark page. A soft band washes with ``--ep-wash``, which theme.css darkens with the page. The one rule that
    may read it is that button's own, ``.ep-button--light``: a link."""
    offenders = []
    for sheet in PUBLIC_STATIC.rglob("*.css"):
        if sheet.name == "theme.css":
            continue
        text = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.S)
        if sheet.name == "button.css":
            text = re.sub(r"\.ep-button--light\s*\{[^}]*\}", "", text)
        if "--ion-color-light" in text:
            offenders.append(sheet.name)
    theme = (PUBLIC_STATIC / "theme.css").read_text(encoding="utf-8")
    dark = region(theme, ":root.ion-palette-dark {", "}")

    assert offenders == []
    assert "--ep-wash:" in region(theme, ":root {", "}")
    assert "--ep-wash:" in dark


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
    css = re.sub(
        r"/\*.*?\*/",
        "",
        (COMPONENT_CSS / "navbar.css").read_text(encoding="utf-8"),
        flags=re.S,
    )
    open_rule = re.search(r"\.ep-navbar\[data-open\]\s*\{([^}]*)\}", css)

    assert "backdrop-filter" in css, "the closed bar is glass"
    assert open_rule, "no rule for the open navbar"
    assert "backdrop-filter: none" in open_rule.group(1)
    assert "-webkit-backdrop-filter: none" in open_rule.group(1)
