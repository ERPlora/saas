"""The public web keeps the look of the previous site: the bars, the footer, the plan cards and the deed title as
they were, and every page title reads «<page> · ERPlora»."""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from public.tests.template_pages import COMPONENT_CSS, PUBLIC_STATIC, ROOT, public_templates

pytestmark = pytest.mark.urls("public.tests.urls")


# --- The public web keeps the look of the previous site (side-by-side captures) -----------------


def css_rule(path: Path, selector: str, *, inside: str = "") -> str:
    """The declarations of the first rule whose whole selector is ``selector`` (after ``inside``,
    e.g. a media query, when given), with the comments dropped."""
    css = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    css = css[css.index(inside) :] if inside else css
    match = re.search(rf"(?:^|[{{}};])\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert match, f"no rule {selector!r} in {path.name}"
    return match.group(1)


def test_the_navbar_links_are_brand_blue_on_the_bar_and_plain_in_the_panel():
    """The links of the bar take the brand colour; inside the mobile panel, the text one."""
    navbar = COMPONENT_CSS / "navbar.css"

    assert "--ep-primary" in css_rule(navbar, ".ep-navbar__links a")
    assert "--ep-text" in css_rule(
        navbar, ".ep-navbar__links a", inside="@media (max-width: 800px)"
    )


@pytest.mark.parametrize(
    ("sheet", "selector"),
    [
        ("navbar.css", ".ep-navbar__bar"),
        ("footer.css", ".ep-footer__columns"),
        ("footer.css", ".ep-footer__bottom"),
    ],
)
def test_the_bar_and_the_footer_are_as_wide_as_today(sheet, selector):
    """1140 px of content plus the padding (1172 px at 1440), as on the previous site; with the page's border-box
    they would be 16 px narrower on each side."""
    assert "box-sizing: content-box" in css_rule(COMPONENT_CSS / sheet, selector)


def test_on_a_phone_the_footer_brand_takes_a_whole_row():
    """At 390 px the brand spans the row above the columns, never a column next to «Product», whether the grid has
    one column or two."""
    rule = css_rule(
        COMPONENT_CSS / "footer.css",
        ".ep-footer__brand-column",
        inside="@media (max-width: 400px)",
    )

    assert "grid-column: 1 / -1" in rule


def test_a_plan_card_lists_plain_checks_with_no_rule_and_no_stretch():
    """«✓ feature» as text, no line above the list, the button right after it."""
    card = COMPONENT_CSS / "pricing-card.css"
    features = css_rule(card, ".ep-pricing-card__features")
    check = css_rule(card, ".ep-pricing-card__check")

    assert "border-top" not in features
    assert "flex: 1" not in features
    assert "background" not in check
    assert "border-radius" not in check


def test_the_deed_title_has_the_size_of_a_page_title():
    """The ``<h2 class="ep-deed-title">`` of the declaración responsable (``demote_h1``)."""
    assert "font-size" in css_rule(
        PUBLIC_STATIC / "layout.css", ".ep-prose .ep-deed-title"
    )


#: The title of a public page: «<page> · ERPlora».
TITLE_BLOCK = re.compile(r"\{%\s*block title\s*%\}(.*?)\{%\s*endblock", re.DOTALL)


def test_every_public_title_separates_the_brand_with_a_middle_dot():
    """Every title reads «<page> · ERPlora», the cookie settings and the not-found page too, never «… - ERPlora»."""
    offenders = [
        f"{template.relative_to(ROOT)}: {title.strip()}"
        for template in public_templates()
        for title in TITLE_BLOCK.findall(template.read_text(encoding="utf-8"))
        if " - ERPlora" in title
    ]

    assert offenders == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "args", "title"),
    [
        ("cookie_consent_cookie_group_list", [], "Cookie Settings · ERPlora"),
        ("test_error_page", [404], "Page not found · ERPlora"),
        ("test_error_page", [500], "Something went wrong · ERPlora"),
    ],
)
def test_the_cookie_settings_and_the_error_titles_read_like_the_rest(
    client, name, args, title
):
    html = client.get(reverse(name, args=args)).content.decode()

    assert f"<title>{title}</title>" in html
