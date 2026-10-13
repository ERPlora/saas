"""The icon of an app, safe to paint inline (spec decision 11, §8.4 and §5.3).

The Hub bakes each app's icon into ``shared.app.icon_svg`` from the shell's packages (spec §4.6):
``ionicons/icons`` for ``ion:`` (outline icons styled by the classes ``ionicon-fill-none`` and
``ionicon-stroke-width``) and ``@iconify-json/*`` for the other sets. The SaaS paints it inline, so
it cleans it with ``nh3`` first: only shape elements, no script, no style, no ``on*`` attribute.
"""

import re

import pytest

from apps.icons import FALLBACK_ICON, FALLBACK_ICON_SVG, ICON_TAGS, clean_icon_svg
from apps.tests.factories import CUBE_SVG

#: ionicons/icons' cube-outline (the shell's form), as the Hub bakes it.
IONICONS_CUBE = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512' class='ionicon'>"
    "<path d='m69 153.99 187 110 187-110M256 463.99v-200' stroke-linecap='round' stroke-linejoin='round' "
    "class='ionicon-fill-none ionicon-stroke-width'/></svg>"
)
#: lucide:database, an Iconify body wrapped in its <svg>: g, ellipse, path.
LUCIDE_DATABASE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">'
    '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
    '<ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M3 5V19A9 3 0 0 0 21 19V5"></path>'
    '<path d="M3 12A9 3 0 0 0 21 12"></path></g></svg>'
)


def test_the_allowed_elements_are_shapes():
    """Spec §8.4's list plus ``ellipse``, a shape that ionicons (25 icons) and lucide (16) draw with."""
    assert ICON_TAGS == {
        "svg",
        "path",
        "g",
        "circle",
        "ellipse",
        "rect",
        "line",
        "polyline",
        "polygon",
        "title",
    }


@pytest.mark.parametrize("svg", [CUBE_SVG, LUCIDE_DATABASE])
def test_a_clean_icon_stays_as_it_is(svg):
    assert clean_icon_svg(svg) == svg


def test_the_ionicons_classes_survive_and_no_other_does():
    """``ion-icon`` styles the outline icons by class: without them the page would fill them."""
    cleaned = clean_icon_svg(
        IONICONS_CUBE.replace("class='ionicon'", "class='ionicon page-hijack'")
    )

    assert 'class="ionicon"' in cleaned
    assert 'class="ionicon-fill-none ionicon-stroke-width"' in cleaned
    assert "page-hijack" not in cleaned


def test_script_style_and_event_handlers_are_removed():
    svg = (
        '<svg viewBox="0 0 24 24" onload="steal()"><script>steal()</script><style>*{display:none}</style>'
        '<path d="M0 0h24" style="fill:red" onclick="steal()"></path>'
        '<a href="javascript:steal()"><circle cx="1" cy="1" r="1"></circle></a>'
        '<foreignObject><div>x</div></foreignObject><image href="https://evil.example/x.png"></image>'
        '<use href="#a"></use></svg>'
    )

    cleaned = clean_icon_svg(svg)

    assert (
        cleaned
        == '<svg viewBox="0 0 24 24"><path d="M0 0h24"></path><circle cx="1" cy="1" r="1"></circle></svg>'
    )


@pytest.mark.parametrize(
    "svg",
    [
        "",
        "   ",
        "<p>not an icon</p>",
        # Nothing to draw once the dangerous parts are gone.
        '<svg viewBox="0 0 24 24"><script>steal()</script></svg>',
        '<svg viewBox="0 0 24 24"><image href="https://evil.example/x.png"></image></svg>',
        # Something outside the <svg>.
        'text<svg viewBox="0 0 24 24"><path d="M0 0"></path></svg>',
    ],
)
def test_an_empty_or_unusable_icon_does_not_pass(svg):
    assert clean_icon_svg(svg) is None


def test_the_fallback_is_ionicons_apps_outline_and_is_clean():
    """Baked in the SaaS (no network for icons, PLAN §16.4), in the attributes form of ionicons'
    ``dist/svg``: it paints the same with or without the ``ion-icon`` classes."""
    assert FALLBACK_ICON == "ion:apps-outline"
    assert clean_icon_svg(FALLBACK_ICON_SVG) == FALLBACK_ICON_SVG
    assert len(re.findall(r"<rect ", FALLBACK_ICON_SVG)) == 9
    assert 'fill="none" stroke="currentColor"' in FALLBACK_ICON_SVG
