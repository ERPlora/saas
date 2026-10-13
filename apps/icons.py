"""The icon of an app of the catalog, safe to paint inline (spec decision 11, §8.4 and §5.3).

The Hub bakes each app's icon into ``shared.app.icon_svg`` (spec §4.6) from the shell's packages:
``ionicons/icons`` for ``ion:``, whose outline icons are styled by the classes ``ionicon-fill-none``
and ``ionicon-stroke-width``, and ``@iconify-json/*`` for the other sets. The SaaS learns about the
apps at run time, so it cannot bake them into its build and fetches nothing: it cleans the SVG it
reads with ``nh3`` and paints it inline. One that is empty, or that has nothing left to draw once
cleaned, is replaced by ``ion:apps-outline``, baked here.

Allowed: the shape elements of spec §8.4 plus ``ellipse``, a shape too (ionicons draws 25 icons with
it, lucide 16), their geometry and presentation attributes, and only the ionicons classes. Never a
script, a style, an ``on*`` attribute, a link or an external image.
"""

import re

import nh3

FALLBACK_ICON = "ion:apps-outline"
#: ionicons 8's apps-outline in the attributes form of its ``dist/svg``: it paints the same with or
#: without the CSS of ``ion-icon``.
FALLBACK_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="ionicon">'
    + "".join(
        f'<rect width="80" height="80" x="{x}" y="{y}" rx="40" ry="40" fill="none" stroke="currentColor" '
        f'stroke-miterlimit="10" stroke-width="32px"></rect>'
        for y in (64, 216, 368)
        for x in (64, 216, 368)
    )
    + "</svg>"
)

ICON_TAGS = frozenset(
    {
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
)
_PRESENTATION = {
    "fill",
    "fill-opacity",
    "fill-rule",
    "clip-rule",
    "opacity",
    "stroke",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-opacity",
    "stroke-width",
    "transform",
}
_ICON_ATTRIBUTES = {
    "*": _PRESENTATION,
    "svg": {"xmlns", "viewBox", "width", "height"},
    "path": {"d"},
    "circle": {"cx", "cy", "r"},
    "ellipse": {"cx", "cy", "rx", "ry"},
    "rect": {"x", "y", "width", "height", "rx", "ry"},
    "line": {"x1", "y1", "x2", "y2"},
    "polyline": {"points"},
    "polygon": {"points"},
}
_IONICONS_SHAPE_CLASSES = {"ionicon-fill-none", "ionicon-stroke-width"}
_ICON_CLASSES = {
    "svg": {"ionicon"},
    **{tag: _IONICONS_SHAPE_CLASSES for tag in ICON_TAGS - {"svg", "title"}},
}
# A whole <svg> element, with at least one shape inside: what is left must still draw something.
_USABLE_RE = re.compile(
    r"<svg[\s>].*<(?:path|circle|ellipse|rect|line|polyline|polygon)[\s>/].*</svg>",
    re.DOTALL,
)


def clean_icon_svg(svg: str) -> str | None:
    """``svg`` cleaned with ``nh3``, or ``None`` when nothing usable is left (empty, not a single
    ``<svg>`` element, or no shape to draw)."""
    cleaned = nh3.clean(
        svg or "",
        tags=ICON_TAGS,
        attributes=_ICON_ATTRIBUTES,
        allowed_classes=_ICON_CLASSES,
    ).strip()
    return cleaned if _USABLE_RE.fullmatch(cleaned) else None
