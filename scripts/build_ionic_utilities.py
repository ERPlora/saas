#!/usr/bin/env python3
"""Writes ``public/static/public/ionic-utilities.css``: the utility classes the public templates
really use, defined by US over Ionic's ``--ion-*`` tokens.

Port of ``scripts/build_ionic_utilities.py`` of the old SaaS (origin/develop), with the same scales
and the same output shape, plus the card-scoped re-emission its sibling
``build_ion_card_content_utilities.py`` wrote to a second file (saas#1728): one generator, one sheet,
so the two cannot drift apart. ``frontend/public.ts`` bundles the sheet; the Tailwind of the SPA
never sees the public templates.

Two engines:
  - COLOUR    : ``bg-*``/``text-*``/``border-*``… over ``--ion-*`` (surface, text, brand, states).
  - UTILITIES : spacing, layout, typography, borders, opacity… with the scale of the old frozen
                bundle baked in as literals. They are NOT Tailwind's defaults (``--text-4xl`` is
                2.5rem here, not 2.25rem).

Usage (from saas-next/): ``uv run python scripts/build_ionic_utilities.py``. Regenerate whenever a
template gains a class: ``public/tests/test_build_ionic_utilities.py`` fails until you do.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "public" / "templates"
OUT = ROOT / "public" / "static" / "public" / "ionic-utilities.css"

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
class_attr_re = re.compile(r'class="([^"]*)"')


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


# ---------------------------------------------------------------------------
# UTILITIES engine (spacing, layout, typography, borders…)
# ---------------------------------------------------------------------------

SPACING_REM = 0.25  # --spacing

BREAKPOINT = {"sm": "40rem", "md": "48rem", "lg": "64rem", "xl": "80rem"}
HOVER_MEDIA = "(hover:hover)"
DARK_MEDIA = "(prefers-color-scheme:dark)"

# class -> (font-size, line-height). The line-height is the EXACT division the bundle emitted, not
# a rounded ratio: `1.3333` over 12px gives 15.9996px, the browser loses a pixel of line height and
# it adds up down the page (1px of drift in 12 captures of the old visual gate).
FONT_SIZE = {
    "xs": (".75rem", "calc(1 / .75)"),
    "sm": (".875rem", "calc(1.25 / .875)"),
    "base": ("1rem", "calc(1.5 / 1)"),
    "lg": ("1.125rem", "calc(1.75 / 1.125)"),
    "xl": ("1.25rem", "calc(1.75 / 1.25)"),
    "2xl": ("1.5rem", "calc(2 / 1.5)"),
    "3xl": ("1.875rem", "calc(2.25 / 1.875)"),
    "4xl": ("2.5rem", "calc(2.5 / 2.25)"),
    "5xl": ("3.25rem", "1"),
    "6xl": ("4rem", "1"),
    "7xl": ("4.5rem", "1"),
}
RADIUS = {
    "": ".25rem",
    "-md": ".375rem",
    "-lg": ".5rem",
    "-xl": ".75rem",
    "-2xl": "1rem",
    "-3xl": "1.5rem",
    # the literal calc(infinity * 1px) resolves to, as the bundle emitted it
    "-full": "3.40282e38px",
}
CONTAINER = {
    "xs": "20rem",
    "sm": "24rem",
    "md": "28rem",
    "lg": "32rem",
    "xl": "36rem",
    "2xl": "42rem",
    "3xl": "48rem",
    "4xl": "56rem",
    "5xl": "64rem",
    "6xl": "72rem",
    "7xl": "80rem",
}
LEADING = {"tight": "1.25", "relaxed": "1.625"}
TRACKING = {
    "tighter": "-.03em",
    "tight": "-.015em",
    "wide": ".025em",
    "wider": ".05em",
    "widest": ".1em",
}
WEIGHT = {"normal": "400", "medium": "500", "semibold": "600", "bold": "700"}
TRANSITION_PROPERTY = {
    "all": "all",
    "colors": (
        "color,background-color,border-color,outline-color,text-decoration-color,"
        "fill,stroke,--tw-gradient-from,--tw-gradient-via,--tw-gradient-to"
    ),
    "shadow": "box-shadow",
    "transform": "transform,translate,scale,rotate",
}
TRANSITION_REST = {
    "transition-timing-function": "cubic-bezier(.4, 0, .2, 1)",
    "transition-duration": ".15s",
}
SHADOW = {
    "-sm": "0 1px 3px 0 #0000001a, 0 1px 2px -1px #0000001a",
    "-md": "0 4px 6px -1px #0000001a, 0 2px 4px -2px #0000001a",
    "-lg": "0 10px 15px -3px #0000001a, 0 4px 6px -4px #0000001a",
    "-xl": "0 20px 25px -5px #0000001a, 0 8px 10px -6px #0000001a",
}
# One literal colour, on purpose: a media letterbox is black in every theme and Ionic has no token
# for it.
LITERAL_COLOR = {
    "black": "#000",
}


def _with_alpha(color: str, alpha: str) -> str:
    """`/NN` on a literal colour: composed into the hex (`#fff` at 15% → `#ffffff26`)."""
    if not alpha:
        return color
    if re.fullmatch(r"#[0-9a-fA-F]{3}", color):
        color = "#" + "".join(ch * 2 for ch in color[1:])
    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return f"{color}{round(int(alpha) * 255 / 100):02x}"
    return f"color-mix(in oklab, {color} {alpha}%, transparent)"


# Utilities without an argument: class -> declarations.
STATIC = {
    "block": {"display": "block"},
    "inline": {"display": "inline"},
    "inline-block": {"display": "inline-block"},
    "flex": {"display": "flex"},
    "inline-flex": {"display": "inline-flex"},
    "grid": {"display": "grid"},
    "hidden": {"display": "none"},
    "list-item": {"display": "list-item"},
    "table": {"display": "table"},
    "contents": {"display": "contents"},
    "static": {"position": "static"},
    "relative": {"position": "relative"},
    "absolute": {"position": "absolute"},
    "fixed": {"position": "fixed"},
    "sticky": {"position": "sticky"},
    "collapse": {"visibility": "collapse"},
    "visible": {"visibility": "visible"},
    "flex-wrap": {"flex-wrap": "wrap"},
    "flex-nowrap": {"flex-wrap": "nowrap"},
    "flex-row": {"flex-direction": "row"},
    "flex-col": {"flex-direction": "column"},
    "flex-1": {"flex": "1"},
    "flex-auto": {"flex": "auto"},
    "flex-none": {"flex": "none"},
    "flex-grow": {"flex-grow": "1"},
    "grow": {"flex-grow": "1"},
    "flex-shrink": {"flex-shrink": "1"},
    "flex-shrink-0": {"flex-shrink": "0"},
    "shrink-0": {"flex-shrink": "0"},
    "truncate": {
        "text-overflow": "ellipsis",
        "white-space": "nowrap",
        "overflow": "hidden",
    },
    "uppercase": {"text-transform": "uppercase"},
    "lowercase": {"text-transform": "lowercase"},
    "capitalize": {"text-transform": "capitalize"},
    "normal-case": {"text-transform": "none"},
    "italic": {"font-style": "italic"},
    "not-italic": {"font-style": "normal"},
    "underline": {"text-decoration-line": "underline"},
    "no-underline": {"text-decoration-line": "none"},
    "line-through": {"text-decoration-line": "line-through"},
    "align-middle": {"vertical-align": "middle"},
    "align-top": {"vertical-align": "top"},
    "tabular-nums": {"font-variant-numeric": "tabular-nums"},
    "whitespace-nowrap": {"white-space": "nowrap"},
    "whitespace-pre-line": {"white-space": "pre-line"},
    "whitespace-pre-wrap": {"white-space": "pre-wrap"},
    "break-all": {"word-break": "break-all"},
    "break-words": {"overflow-wrap": "break-word"},
    "list-disc": {"list-style-type": "disc"},
    "list-decimal": {"list-style-type": "decimal"},
    "list-none": {"list-style-type": "none"},
    "list-inside": {"list-style-position": "inside"},
    "object-cover": {"object-fit": "cover"},
    "object-contain": {"object-fit": "contain"},
    "overflow-hidden": {"overflow": "hidden"},
    "overflow-auto": {"overflow": "auto"},
    "overflow-x-auto": {"overflow-x": "auto"},
    "overflow-y-auto": {"overflow-y": "auto"},
    "cursor-pointer": {"cursor": "pointer"},
    "cursor-default": {"cursor": "default"},
    "cursor-not-allowed": {"cursor": "not-allowed"},
    "select-none": {"-webkit-user-select": "none", "user-select": "none"},
    "select-all": {"-webkit-user-select": "all", "user-select": "all"},
    "resize-none": {"resize": "none"},
    "appearance-none": {"appearance": "none"},
    "pointer-events-none": {"pointer-events": "none"},
    "pointer-events-auto": {"pointer-events": "auto"},
    "place-items-center": {"place-items": "center"},
    "mx-auto": {"margin-inline": "auto"},
    "mt-auto": {"margin-top": "auto"},
    "mb-auto": {"margin-bottom": "auto"},
    "ml-auto": {"margin-left": "auto"},
    "mr-auto": {"margin-right": "auto"},
    "sr-only": {
        "position": "absolute",
        "width": "1px",
        "height": "1px",
        "padding": "0",
        "margin": "-1px",
        "overflow": "hidden",
        "clip": "rect(0,0,0,0)",
        "white-space": "nowrap",
        "border-width": "0",
    },
    # marker: only there so `group-hover:*` has something to look at
    "group": {},
}
ALIGN = {
    "start": "flex-start",
    "end": "flex-end",
    "center": "center",
    "between": "space-between",
    "around": "space-around",
    "evenly": "space-evenly",
    "stretch": "stretch",
    "baseline": "baseline",
}
SIDE = {"t": "top", "r": "right", "b": "bottom", "l": "left"}

_size_re = re.compile(
    r"^(?:(\d+(?:\.\d+)?)|(auto|full|screen|px|min|max|fit|dvh|none)|\[(.+)\])$"
)


def _rem(number: str) -> str:
    """N -> N * --spacing, in the bundle's format (.75rem, 1rem, 0)."""
    value = float(number) * SPACING_REM
    text = f"{value:.4f}".rstrip("0").rstrip(".") or "0"
    if text == "0":
        return "0"
    if text.startswith("0."):
        text = text[1:]
    return text + "rem"


def _length(raw: str, *, axis: str = "") -> str | None:
    """The argument of w-/h-/max-w-/min-h-… as a CSS length."""
    m = _size_re.match(raw)
    if not m:
        return None
    number, keyword, arbitrary = m.groups()
    if arbitrary is not None:
        return arbitrary.replace("_", " ")
    if number is not None:
        return _rem(number)
    return {
        "auto": "auto",
        "full": "100%",
        "px": "1px",
        "none": "none",
        "min": "min-content",
        "max": "max-content",
        "fit": "fit-content",
        "screen": "100vw" if axis == "w" else "100vh",
        "dvh": "100dvh",
    }[keyword]


def utility_declarations(base: str) -> dict[str, str] | None:  # noqa: C901, PLR0911, PLR0912 - one grammar
    """Declarations of a utility class WITHOUT a variant. None = not one we know."""
    if base in STATIC:
        return dict(STATIC[base])

    # typography
    if base.startswith("text-"):
        key = base[5:]
        if key in FONT_SIZE:
            size, leading = FONT_SIZE[key]
            # `leading-*` must beat the line of `text-*` wherever it sits in the sheet, so `text-*`
            # READS `--tw-leading` and `leading-*` sets it (as Tailwind does): `.leading-*` comes
            # first alphabetically and a literal here would win.
            return {"font-size": size, "line-height": f"var(--tw-leading, {leading})"}
        if key in ("left", "center", "right", "justify"):
            return {"text-align": key}
        if key == "inherit":
            return {"color": "inherit"}
        if key in LITERAL_COLOR:
            return {"color": LITERAL_COLOR[key]}
        if key.startswith("[") and key.endswith("]"):
            return {"font-size": key[1:-1].replace("_", " ")}
    if base.startswith("font-") and base[5:] in WEIGHT:
        return {"font-weight": WEIGHT[base[5:]]}
    if base.startswith("leading-") and base[8:] in LEADING:
        # the variable IS the mechanism (see `text-*`); the line-height is for an element with no
        # `text-*`, which does not read the variable
        return {"--tw-leading": LEADING[base[8:]], "line-height": LEADING[base[8:]]}
    if base.startswith("tracking-") and base[9:] in TRACKING:
        return {"letter-spacing": TRACKING[base[9:]]}

    # literal colour (see LITERAL_COLOR)
    if base.startswith("bg-"):
        key, _, alpha = base[3:].partition("/")
        if key in LITERAL_COLOR:
            return {"background-color": _with_alpha(LITERAL_COLOR[key], alpha)}
    if base.startswith("border-") and base[7:] in LITERAL_COLOR:
        return {"border-color": LITERAL_COLOR[base[7:]]}

    # spacing
    m = re.fullmatch(r"(-?)(p|m)([trblxy]?)-(.+)", base)
    if m:
        sign, kind, side, raw = m.groups()
        length = _length(raw)
        if length is None:
            return None
        if sign and length != "0":
            length = "-" + length
        prop = "padding" if kind == "p" else "margin"
        if side == "":
            return {prop: length}
        if side == "x":
            return {f"{prop}-inline": length}
        if side == "y":
            return {f"{prop}-block": length}
        return {f"{prop}-{SIDE[side]}": length}

    # sizes: the named widths (max-w-lg…) BEFORE the numeric engine, which would return None
    m = re.fullmatch(r"max-w-(.+)", base)
    if m and m.group(1) in CONTAINER:
        return {"max-width": CONTAINER[m.group(1)]}
    m = re.fullmatch(r"(max-|min-)?([wh])-(.+)", base)
    if m:
        bound, axis, raw = m.groups()
        length = _length(raw, axis=axis)
        if length is None:
            return None
        prop = ("max-" if bound == "max-" else "min-" if bound == "min-" else "") + (
            "width" if axis == "w" else "height"
        )
        return {prop: length}

    # layout
    if base.startswith("gap-"):
        length = _length(base[4:])
        return {"gap": length} if length else None
    if base.startswith("grid-cols-"):
        arg = base[10:]
        if arg.isdigit():
            return {"grid-template-columns": f"repeat({arg},minmax(0,1fr))"}
        if arg.startswith("[") and arg.endswith("]"):
            return {"grid-template-columns": arg[1:-1].replace("_", " ")}
    if base.startswith("col-span-"):
        arg = base[9:]
        if arg == "full":
            return {"grid-column": "1 / -1"}
        if arg.isdigit():
            return {"grid-column": f"span {arg}/span {arg}"}
    if base.startswith("items-") and base[6:] in ALIGN:
        return {"align-items": ALIGN[base[6:]]}
    if base.startswith("justify-") and base[8:] in ALIGN:
        return {"justify-content": ALIGN[base[8:]]}
    if base.startswith("self-") and base[5:] in ALIGN:
        return {"align-self": ALIGN[base[5:]]}

    # borders / radii
    m = re.fullmatch(r"rounded(-[a-z0-9]+)?", base)
    if m and (m.group(1) or "") in RADIUS:
        return {"border-radius": RADIUS[m.group(1) or ""]}
    m = re.fullmatch(r"border(-[trbl])?(?:-(\d+))?", base)
    if m:
        side, width = m.groups()
        width = f"{width}px" if width is not None else "1px"
        if side:
            name = SIDE[side[1:]]
            return {f"border-{name}-style": "solid", f"border-{name}-width": width}
        return {"border-style": "solid", "border-width": width}

    # position / layers
    m = re.fullmatch(r"(top|right|bottom|left|inset)-(.+)", base)
    if m:
        prop, raw = m.groups()
        length = _length(raw)
        return {prop: length} if length else None
    if base.startswith("z-") and base[2:].isdigit():
        return {"z-index": base[2:]}
    if base.startswith("opacity-") and base[8:].isdigit():
        value = f"{int(base[8:]) / 100:.2f}".rstrip("0").rstrip(".")
        return {"opacity": value[1:] if value.startswith("0.") else value}

    # shadows / transitions
    m = re.fullmatch(r"shadow(-[a-z]+)?", base)
    if m and (m.group(1) or "-sm") in SHADOW:
        return {"box-shadow": SHADOW[m.group(1) or "-sm"]}
    m = re.fullmatch(r"transition(?:-([a-z]+))?", base)
    if m:
        prop = TRANSITION_PROPERTY.get(m.group(1) or "colors")
        if prop:
            return {"transition-property": prop, **TRANSITION_REST}
    m = re.fullmatch(r"ring-(\d+)", base)
    if m:
        # Like `text-*`/`leading-*`: the width READS the colour `ring-<colour>` writes (saas#1831).
        return {
            "box-shadow": f"0 0 0 {m.group(1)}px var(--tw-ring-color, currentcolor)"
        }
    m = re.fullmatch(r"translate-([xy])-(.+)", base)
    if m:
        axis, raw = m.groups()
        length = _length(raw)
        if length:
            return {"translate": f"{length} 0" if axis == "x" else f"0 {length}"}
    return None


# Variants: name -> (media query or None, selector suffix)
UTILITY_VARIANTS = {
    "hover": (HOVER_MEDIA, ":hover"),
    "focus": (None, ":focus"),
    "dark": (DARK_MEDIA, ""),
    "first": (None, ":first-child"),
    "last": (None, ":last-child"),
    "group-hover": (HOVER_MEDIA, ":is(:where(.group):hover *)"),
    **{bp: (f"(min-width:{width})", "") for bp, width in BREAKPOINT.items()},
}


def escape(token: str) -> str:
    """A class name as a CSS selector fragment (`md:p-4` → `md\\:p-4`)."""
    out = ""
    for ch in token:
        out += "\\" + ch if ch in ".:/[]()%#," else ch
    return out


def _utility_parts(token: str) -> tuple[str | None, str, str] | None:
    """(media query, selector, body) of a utility class, or None if it is not one we know."""
    variant, _, base = token.rpartition(":")
    if variant and variant not in UTILITY_VARIANTS:
        return None
    media, suffix = UTILITY_VARIANTS[variant] if variant else (None, "")

    # space-y-* / divide-y space the children, not the element
    m = re.fullmatch(r"space-y-(.+)", base)
    if m:
        length = _length(m.group(1))
        if length is None:
            return None
        body = f"margin-block-start: 0; margin-block-end: {length};"
        return media, f":where(.{escape(token)}{suffix} > :not(:last-child))", body
    if base == "divide-y":
        body = "border-top-style: solid; border-bottom-style: solid; border-top-width: 0; border-bottom-width: 1px;"
        return media, f":where(.{escape(token)}{suffix} > :not(:last-child))", body

    decls = utility_declarations(base)
    if not decls:  # unknown, or a marker without declarations (.group)
        return None
    body = " ".join(f"{prop}: {value};" for prop, value in decls.items())
    return media, f".{escape(token)}{suffix}", body


def utility_rule(token: str) -> tuple[str | None, str] | None:
    """(media query, CSS rule) of a utility class, or None if it is not one we know."""
    parts = _utility_parts(token)
    if parts is None:
        return None
    media, sel, body = parts
    return media, f"{sel} {{ {body} }}"


# ---------------------------------------------------------------------------
# Card scope (saas#1728)
# ---------------------------------------------------------------------------
# Ionic injects the styles of `ion-card-content` at runtime as a plain `<style>` with NO cascade
# layer (`.card-content-ios p { margin-bottom: 2px; font-size: .875rem }`…), and an unlayered
# declaration beats a layered one whatever its specificity: `mb-4` on a card's `<h3>` computed to
# 2px. The utilities that touch those properties are re-emitted UNLAYERED and scoped to the card,
# with two classes so specificity, not order, decides. Opt-in by construction: a rule only matches
# an element that carries the utility. Classified by the properties they declare, never by name.
CARD_CLASSES = (".card-content-ios", ".card-content-md")
# What Ionic sets on the card's h1…h6 / p, and on `ion-card-content` itself.
CHILD_PROPERTIES = ("margin", "font-size", "font-weight")
CONTAINER_PROPERTIES = ("padding", "font-size", "line-height")
_SINGLE_CLASS = re.compile(r"^\.[^ ,>+~.:\[\]()]+(?::[a-z-]+)*$")


def _declares(body: str, properties: tuple[str, ...]) -> bool:
    """True when ``body`` sets one of ``properties`` (``margin`` covers ``margin-bottom``…)."""
    for declaration in body.split(";"):
        name = declaration.split(":", 1)[0].strip()
        if name.startswith("--"):
            continue  # a custom property: the longhand next to it is what lands
        if any(name == prop or name.startswith(prop + "-") for prop in properties):
            return True
    return False


def _card_rule(sel: str, body: str) -> str | None:
    if not _SINGLE_CLASS.match(re.sub(r"\\.", "", sel)):
        return None
    selectors = []
    if _declares(body, CHILD_PROPERTIES):
        selectors += [f"{card} {sel}" for card in CARD_CLASSES]
    if _declares(body, CONTAINER_PROPERTIES):
        selectors += [f"{card}{sel}" for card in CARD_CLASSES]
    if not selectors:
        return None
    return ",\n".join(selectors) + " { " + body.strip().rstrip(";") + " }"


# ---------------------------------------------------------------------------
# Reading the templates and writing the sheet
# ---------------------------------------------------------------------------


def template_files(root: Path = TEMPLATES) -> list[Path]:
    """Every public template, e-mails aside (no stylesheet reaches them)."""
    return sorted(path for path in root.glob("**/*.html") if "email" not in path.parts)


_TEMPLATE_SYNTAX = re.compile(r"\{%.*?%\}|\{\{.*?\}\}")


def tokens_used(files: list[Path]) -> list[str]:
    """Distinct classes of every ``class="…"``, in a stable order. Template tags and variables are
    dropped first, so a class written inside ``{% if %}…{% endif %}`` still counts."""
    seen: OrderedDict[str, None] = OrderedDict()
    for path in files:
        for attr in class_attr_re.findall(
            path.read_text(encoding="utf-8", errors="ignore")
        ):
            for token in _TEMPLATE_SYNTAX.sub(" ", attr).split():
                if "{" in token or "%" in token:
                    continue
                seen.setdefault(token, None)
    return list(seen)


def render(tokens: list[str]) -> str:  # noqa: C901 - the sheet, section by section
    color_rules: list[str] = []
    color_media_rules: set[str] = set()
    plain: list[str] = []
    by_media: OrderedDict[str, list[str]] = OrderedDict()
    card_plain: list[str] = []
    card_media: OrderedDict[str, list[str]] = OrderedDict()

    # 1) COLOUR engine (over --ion-*)
    for token in sorted(tokens):
        m = token_re.match(token)
        if not m:
            continue
        variant, prefix = m.group("variant"), m.group("prefix")
        if variant and variant not in VARIANTS and variant not in MEDIA:
            continue
        rule = (
            f"{selector(token, variant, prefix)} {{ "
            f"{PREFIX_PROP[prefix]}: {css_value(m.group('color'), m.group('alpha'))}; }}"
        )
        if variant in MEDIA:
            by_media.setdefault(f"(min-width: {MEDIA[variant]})", []).append(rule)
            color_media_rules.add(rule)
        else:
            color_rules.append(rule)

    # 2) UTILITIES engine (spacing, layout, typography…), and their card-scoped copies
    for token in sorted(tokens):
        if token_re.match(token):
            continue
        parts = _utility_parts(token)
        if parts is None:
            continue
        media, sel, body = parts
        rule = f"{sel} {{ {body} }}"
        if media:
            by_media.setdefault(media, []).append(rule)
        else:
            plain.append(rule)
        card = _card_rule(sel, body)
        if card and media:
            card_media.setdefault(media, []).append(card)
        elif card:
            card_plain.append(card)

    # The utilities live inside `@layer utilities`, as in the bundle: unlayered CSS beats layered
    # CSS whatever the specificity, so outside the layer `class="p-0"` on an `ion-card-content`
    # would start overriding Ionic's component CSS. The COLOUR rules stay outside on purpose: they
    # were generated to win the cascade.
    out = [
        "/* ionic-utilities.css - GENERATED by scripts/build_ionic_utilities.py (do not edit by hand).",
        " * The utilities the public templates really use: colour over Ionic tokens --ion-*,",
        " * plus spacing, layout and typography with the scale of the old bundle.",
        " * Regenerate: uv run python scripts/build_ionic_utilities.py */",
        "",
        *color_rules,
        "",
        "/* The --tw-* variables: the indirection that lets one utility beat another without",
        " * depending on rule order. `leading-*` over the line of `text-*`, `ring-<colour>` over",
        " * the colour of `ring-<n>`; the second one of each pair READS it, with a fallback.",
        " * WITHOUT inheritance: otherwise a child's `text-xs` would inherit the parent's",
        " * `leading-relaxed`, and a nested `ring-2` the ring colour of the outer one.",
        " * The reset on `*` is the one Tailwind emitted for browsers without @property. */",
        '@property --tw-leading { syntax: "*"; inherits: false; }',
        '@property --tw-ring-color { syntax: "*"; inherits: false; }',
        "@layer properties {",
        "  *, :before, :after, ::backdrop { --tw-leading: initial; --tw-ring-color: initial; }",
        "}",
        "",
        "/* Layout, spacing and typography utilities: INSIDE the layer. */",
        "@layer utilities {",
        *(f"  {rule}" for rule in plain),
        "}",
    ]
    for query, rules in by_media.items():
        color_in_media = [rule for rule in rules if rule in color_media_rules]
        util_in_media = [rule for rule in rules if rule not in color_media_rules]
        if color_in_media:
            out += [
                "",
                f"@media {query} {{",
                *(f"  {rule}" for rule in color_in_media),
                "}",
            ]
        if util_in_media:
            out += [
                "",
                "@layer utilities {",
                f"  @media {query} {{",
                *(f"    {rule}" for rule in util_in_media),
                "  }",
                "}",
            ]
    out += [
        "",
        "/* Card scope (saas#1728): Ionic's unlayered `ion-card-content` rules shadow layered",
        " * utilities, so these are re-emitted UNLAYERED with two classes. NEVER inside @layer. */",
        *card_plain,
    ]
    for query, rules in card_media.items():
        out += [
            "",
            f"@media {query} {{",
            *("  " + rule.replace("\n", "\n  ") for rule in rules),
            "}",
        ]
    return "\n".join(out) + "\n"


def main() -> None:
    files = template_files()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(tokens_used(files)), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: from {len(files)} templates")


if __name__ == "__main__":
    main()
