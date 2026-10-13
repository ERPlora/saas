"""``scripts/build_ionic_utilities.py``: the utility classes the public templates use, owned by us.

Port of the old SaaS's generator and of its contract ``tests/unit/test_owned_css_utilities.py``
(origin/develop). It reads ``public/templates/**`` and writes ``public/static/public/ionic-utilities.css``
(Tailwind-like names over ``--ion-*`` tokens), which ``frontend/public.ts`` bundles. Same scales, same
``@layer utilities``, same ``--tw-leading`` / ``--tw-ring-color`` indirection. New here: the
card-scoped re-emission that the old ``build_ion_card_content_utilities.py`` wrote to a second file
(saas#1728) is part of the same output, so the two cannot drift apart.
"""

import importlib.util
import re
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
SCRIPT = ROOT / "scripts" / "build_ionic_utilities.py"
GENERATED = ROOT / "public" / "static" / "public" / "ionic-utilities.css"


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("build_ionic_utilities", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _layer_bodies(css: str) -> str:
    return "".join(re.findall(r"@layer utilities \{(.*?)\n\}", css, flags=re.S))


def test_the_committed_sheet_is_what_the_generator_writes_today(generator):
    """The working rule «new class in a template ⇒ regenerate», as a test."""
    assert GENERATED.read_text(encoding="utf-8") == generator.render(
        generator.tokens_used(generator.template_files())
    ), "run `uv run python scripts/build_ionic_utilities.py`"


def test_it_reads_the_public_templates_and_writes_the_public_sheet(generator):
    files = generator.template_files()

    assert files, "no template read"
    assert all(ROOT / "public" / "templates" in path.parents for path in files)
    assert generator.OUT == GENERATED


def test_tokens_come_from_class_attributes_without_template_fragments(
    generator, tmp_path
):
    page = tmp_path / "page.html"
    page.write_text(
        '<div class="p-4 md:grid-cols-2 {% if x %}hidden{% endif %} text-fg/55">'
        '<span class="ep-eyebrow">x</span></div>',
        encoding="utf-8",
    )

    assert generator.tokens_used([page]) == [
        "p-4",
        "md:grid-cols-2",
        "hidden",
        "text-fg/55",
        "ep-eyebrow",
    ]


def test_positive_control_layers_media_scales_and_colours(generator):
    css = generator.render(
        [
            "p-4",
            "gap-3",
            "md:grid-cols-2",
            "text-sm",
            "text-fg/55",
            "bg-surface",
            "ep-eyebrow",
        ]
    )
    layered = _layer_bodies(css)

    # spacing with the bundle's scale, INSIDE the layer: unlayered it would beat Ionic's component CSS
    assert ".p-4 { padding: 1rem; }" in layered
    assert ".gap-3 { gap: .75rem; }" in layered
    # a responsive variant inside its media query
    assert re.search(
        r"@media \(min-width:48rem\) \{\s*\.md\\:grid-cols-2 \{ grid-template-columns: repeat\(2,minmax\(0,1fr\)\); \}",
        css,
    )
    # colours over --ion-* tokens, outside the layer (they must win, as before)
    assert (
        ".text-fg\\/55 { color: color-mix(in oklab, var(--ion-text-color, #1c1b18) 55%, transparent); }"
        in css
    )
    assert ".bg-surface {" not in layered
    # a component class is not a utility: nothing emitted for it
    assert "ep-eyebrow" not in css


def test_leading_overrides_the_text_size_line_height_regardless_of_order(generator):
    """`text-*` reads `--tw-leading` with its own line as the fallback; `leading-*` sets it (saas#1811)."""
    css = generator.render(["text-sm", "leading-relaxed"])

    assert (
        ".text-sm { font-size: .875rem; line-height: var(--tw-leading, calc(1.25 / .875)); }"
        in css
    )
    assert ".leading-relaxed { --tw-leading: 1.625; line-height: 1.625; }" in css
    assert '@property --tw-leading { syntax: "*"; inherits: false; }' in css


def test_ring_colour_overrides_the_ring_default_regardless_of_order(generator):
    """`ring-<n>` reads `--tw-ring-color`; `ring-<colour>` only sets it (saas#1831)."""
    css = generator.render(["ring-2", "hover:ring-primary/30"])

    assert "box-shadow: 0 0 0 2px var(--tw-ring-color, currentcolor);" in css
    assert (
        "--tw-ring-color: color-mix(in oklab, var(--ion-color-primary) 30%, transparent);"
        in css
    )
    assert '@property --tw-ring-color { syntax: "*"; inherits: false; }' in css


def test_utilities_ionic_shadows_inside_a_card_are_re_emitted_unlayered_and_card_scoped(
    generator,
):
    """saas#1728: Ionic injects `ion-card-content` styles with no layer, so a layered `mb-4` on a card's
    `<h3>` computed to 2px. Re-emitted with two classes and no layer, the utility wins inside a card."""
    css = generator.render(["mb-4", "p-6", "text-primary", "md:mb-8"])
    unlayered = re.sub(r"@layer utilities \{.*?\n\}", "", css, flags=re.S)

    assert (
        ".card-content-ios .mb-4,\n.card-content-md .mb-4 { margin-bottom: 1rem }"
        in unlayered
    )
    assert (
        ".card-content-ios.p-6,\n.card-content-md.p-6 { padding: 1.5rem }" in unlayered
    )
    # colour is not shadowed by Ionic: not re-emitted
    assert ".card-content-ios .text-primary" not in css
    # a responsive variant keeps its media query
    assert re.search(
        r"@media \(min-width:48rem\) \{\s*\.card-content-ios \.md\\:mb-8", unlayered
    )


def test_every_utility_the_generator_owns_in_the_public_templates_is_emitted(generator):
    css = GENERATED.read_text(encoding="utf-8")
    owned = [
        token
        for token in generator.tokens_used(generator.template_files())
        if generator.token_re.match(token) or generator.utility_rule(token) is not None
    ]
    missing = [token for token in owned if f".{generator.escape(token)}" not in css]

    assert missing == [], "run `uv run python scripts/build_ionic_utilities.py`"
