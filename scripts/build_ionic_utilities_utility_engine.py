"""The UTILITIES engine of ``build_ionic_utilities.py``: spacing, layout, typography, borders, opacity… with the
scale of the old frozen bundle baked in as literals, not Tailwind's defaults."""

from __future__ import annotations

import re

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


def utility_declarations(base: str) -> dict[str, str] | None:  # noqa: C901, PLR0911, PLR0912, PLR0915 - one grammar
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
        # Like `text-*`/`leading-*`: the width READS the colour `ring-<colour>` writes.
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
