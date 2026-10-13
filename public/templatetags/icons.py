"""``{% icon %}``: an inline SVG painted on the server from the baked icon JSON (spec §8.4).

Port of ``apps/core/templatetags/icons.py`` of the old SaaS, same call shape::

    {% load icons %}
    {% icon "construct-outline" %}                       {# no set = Ionicons (ion:) #}
    {% icon "lucide:check" size=20 css_class="text-primary" %}
    {% icon icon %}                                      {# a component partial's variable #}

The old tag emitted an empty ``<span class="iconify">`` that Iconify filled in the browser from
``api.iconify.design``. Here the SVG comes from ``frontend/generated/public-icons.json``, which
``pnpm gen:public-icons`` (``scripts/gen-public-icons.mjs``) writes from the icon packages of the
shell (``ionicons``, ``@iconify-json/*``) with only the icons ``public/templates`` cite. Nothing is
fetched, ever. An icon that is not baked is a clear error with DEBUG and, in production, a warning
in the log plus a neutral fallback glyph: a missing icon must not take a page down.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe

logger = logging.getLogger(__name__)
register = template.Library()

#: The baked icons: ``{"<set>:<name>": {"body": "<path …/>", "viewBox": "0 0 512 512"}}``.
ICONS_FILE = Path(settings.BASE_DIR) / "frontend" / "generated" / "public-icons.json"
#: The set of a name without a prefix, as in the old tag and in the shell's ``HubIcon``.
DEFAULT_SET = "ion"
#: What a missing icon paints in production: a rounded square in the text colour.
FALLBACK_BODY = '<rect x="3" y="3" width="18" height="18" rx="4" fill="none" stroke="currentColor" stroke-width="2"/>'
FALLBACK_VIEWBOX = "0 0 24 24"


class IconNotBaked(ImproperlyConfigured):
    """A template names an icon the baked JSON does not hold."""


def icon_key(name: str) -> str:
    """``"cube-outline"`` → ``"ion:cube-outline"``; a name with a set stays as it is."""
    return name if ":" in name else f"{DEFAULT_SET}:{name}"


@lru_cache(maxsize=1)
def load_icons() -> dict[str, dict[str, str]]:
    """The baked icons, read once per process (``load_icons.cache_clear()`` after regenerating)."""
    try:
        return json.loads(ICONS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ImproperlyConfigured(
            f"{ICONS_FILE} does not exist: run `pnpm gen:public-icons` and commit the result."
        ) from None


def _svg(body: str, view_box: str, size, css_class: str, attrs: dict) -> SafeString:
    dimension = "1em" if size is None else str(size)
    classes = f"ep-icon {css_class}".strip()
    extra = format_html_join(
        "", ' {}="{}"', ((key.replace("_", "-"), value) for key, value in attrs.items())
    )
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{}" width="{}" height="{}" fill="currentColor"'
        ' class="{}" aria-hidden="true" focusable="false"{}>{}</svg>',
        view_box,
        dimension,
        dimension,
        classes,
        extra,
        # Trusted markup: the body comes from the icon packages, through the generator.
        mark_safe(body),
    )


@register.simple_tag
def icon(name: str, size=None, css_class: str = "", **attrs) -> SafeString:
    """The inline SVG of ``name``; ``size`` in pixels (default ``1em``), extra attributes with ``_`` → ``-``."""
    key = icon_key(str(name))
    baked = load_icons().get(key)
    if baked is None:
        if settings.DEBUG:
            raise IconNotBaked(
                f"Icon {key!r} is not baked into {ICONS_FILE.name}: run `pnpm gen:public-icons` "
                "(it reads the icons public/templates cite) and commit the JSON."
            )
        logger.warning(
            "public icon %s is not baked into %s; painting the fallback",
            key,
            ICONS_FILE.name,
        )
        return _svg(FALLBACK_BODY, FALLBACK_VIEWBOX, size, css_class, attrs)
    return _svg(baked["body"], baked["viewBox"], size, css_class, attrs)
