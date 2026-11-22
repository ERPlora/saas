"""The COLOUR engine of ``build_ionic_utilities.py``: ``bg-*``/``text-*``/``border-*``… over Ionic's ``--ion-*``
tokens (surface, text, brand, states)."""

from __future__ import annotations

import re

# Supported colours → Ionic token. info/accent are defined in public/static/public/theme.css.
COLOR_VALUE = {
    # surfaces / text
    "surface": "var(--ion-background-color, #ffffff)",
    "surface-2": "var(--ion-color-step-50, #f4f5f8)",
    "surface-3": "var(--ion-border-color, var(--ion-color-step-150, #e0e0e0))",
    "fg": "var(--ion-text-color, #1c1b18)",
    # brand / states
    "primary-content": "var(--ion-color-primary-contrast, #ffffff)",
    "primary": "var(--ion-color-primary)",
    "secondary-content": "var(--ion-color-secondary-contrast, #ffffff)",
    "secondary": "var(--ion-color-secondary)",
    "accent-content": "var(--ion-color-accent-contrast, #ffffff)",
    "accent": "var(--ion-color-accent)",
    "neutral-content": "var(--ion-color-medium-contrast, #ffffff)",
    "neutral": "var(--ion-color-medium)",
    "info-content": "var(--ion-color-info-contrast, #ffffff)",
    "info": "var(--ion-color-info)",
    "success-content": "var(--ion-color-success-contrast, #ffffff)",
    "success": "var(--ion-color-success)",
    "warning-content": "var(--ion-color-warning-contrast, #1c1b18)",
    "warning": "var(--ion-color-warning)",
    "danger": "var(--ion-color-danger)",
    "danger-content": "var(--ion-color-danger-contrast, #ffffff)",
}
# Longest first, so the regex alternation does not cut "surface-2" into "surface".
COLORS = sorted(COLOR_VALUE, key=len, reverse=True)
PREFIX_PROP = {
    "bg": "background-color",
    "text": "color",
    "border": "border-color",
    "divide": "border-color",  # special selector (children)
    "ring": "--tw-ring-color",
    "fill": "fill",
    "stroke": "stroke",
    "placeholder": "color",  # special selector (::placeholder)
    "from": "--tw-gradient-from",
    "to": "--tw-gradient-to",
    "via": "--tw-gradient-via",
}
VARIANTS = {  # colour variant → selector suffix
    "hover": ":hover",
    "focus": ":focus",
    "focus-within": ":focus-within",
    "active": ":active",
    "disabled": ":disabled",
}
MEDIA = {"sm": "640px", "md": "768px", "lg": "1024px", "xl": "1280px"}

color_re = "|".join(re.escape(c) for c in COLORS)
token_re = re.compile(
    rf"^(?:(?P<variant>[a-z-]+):)?(?P<prefix>{'|'.join(PREFIX_PROP)})-(?P<color>{color_re})(?:/(?P<alpha>\d+))?$"
)


def css_value(color: str, alpha: str | None) -> str:
    base = COLOR_VALUE[color]
    if alpha:
        return f"color-mix(in oklab, {base} {alpha}%, transparent)"
    return base


def selector(token: str, variant: str | None, prefix: str) -> str:
    esc = token.replace("/", "\\/").replace(":", "\\:")
    sel = f".{esc}"
    if variant in VARIANTS:
        sel += VARIANTS[variant]
    if prefix == "divide":
        sel += " > :not([hidden]) ~ :not([hidden])"
    elif prefix == "placeholder":
        sel += "::placeholder"
    return sel
