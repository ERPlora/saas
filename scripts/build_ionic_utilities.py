#!/usr/bin/env python3
"""Writes ``public/static/public/ionic-utilities.css``: the utility classes the public templates
really use, defined by US over Ionic's ``--ion-*`` tokens.

The card-scoped classes come out of the same generator into the same sheet, so the two cannot drift
apart. ``frontend/public.ts`` bundles the sheet; the Tailwind of the SPA
never sees the public templates.

Two engines, each in its own module next to this script (``build_ionic_utilities_colour_engine.py`` and
``build_ionic_utilities_utility_engine.py``):
  - COLOUR    : ``bg-*``/``text-*``/``border-*``… over ``--ion-*`` (surface, text, brand, states).
  - UTILITIES : spacing, layout, typography, borders, opacity… with the scale of the old frozen
                bundle baked in as literals. They are NOT Tailwind's defaults (``--text-4xl`` is
                2.5rem here, not 2.25rem).

Usage (from the repo): ``uv run python scripts/build_ionic_utilities.py``. Regenerate whenever a
template gains a class: ``public/tests/test_build_ionic_utilities.py`` fails until you do.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

from build_ionic_utilities_colour_engine import MEDIA, PREFIX_PROP, VARIANTS, css_value, selector, token_re
from build_ionic_utilities_utility_engine import _utility_parts

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "public" / "templates"
OUT = ROOT / "public" / "static" / "public" / "ionic-utilities.css"
class_attr_re = re.compile(r'class="([^"]*)"')


# ---------------------------------------------------------------------------
# Card scope
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


def render(tokens: list[str]) -> str:  # noqa: C901, PLR0912 - the sheet, section by section
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
