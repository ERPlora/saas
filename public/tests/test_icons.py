"""``{% icon %}``: the public templates paint their icons on the server, from a baked JSON (spec §8.4).

Port of ``apps/core/templatetags/icons.py`` (origin/develop), which emitted an empty
``<span class="iconify">`` that Iconify filled in the browser from ``api.iconify.design``. Here the
SVG comes from ``frontend/generated/public-icons.json``, written by ``pnpm gen:public-icons`` from the
same icon packages the shell uses, with only the icons the public pages paint: the ones the templates
cite and the sector and business type icons of ``hubs/data/taxonomy.json`` (the industries pages).
Never a network call.
"""

import json
import logging
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template

from hubs.management.commands.seed_taxonomy import TAXONOMY_FILE
from public.templatetags import icons

PUBLIC_TEMPLATES = Path(settings.BASE_DIR) / "public" / "templates"
ICONS_JSON = Path(settings.BASE_DIR) / "frontend" / "generated" / "public-icons.json"

#: ``{% icon "set:name" … %}`` with a literal name, and ``icon="…"`` / ``<x>_icon="…"`` passed to an
#: ``{% include %}`` (the component partials paint them with ``{% icon icon %}``). The same reading
#: as ``scripts/gen-public-icons.mjs``; usage examples inside template comments do not count.
TEMPLATE_COMMENT = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|\{#.*?#\}", re.S)
ICON_TAG = re.compile(r"""\{%\s*icon\s+["']([^"']+)["']""")
INCLUDE_TAG = re.compile(r"\{%\s*include\b[^%]*%\}")
INCLUDE_ICON_ARG = re.compile(r"""\b(?:\w+_)?icon=["']([^"']+)["']""")


def cited_icons() -> set[str]:
    """Every icon a public page paints: cited by a template or named by a row of the taxonomy.

    The industries pages paint the ``icon`` of each sector and business type of the seed; one that is
    not baked would paint the generic default instead (``public/industries.py``).
    """
    names: set[str] = set()
    for template in PUBLIC_TEMPLATES.rglob("*.html"):
        source = TEMPLATE_COMMENT.sub("", template.read_text(encoding="utf-8"))
        names.update(ICON_TAG.findall(source))
        for include in INCLUDE_TAG.findall(source):
            names.update(INCLUDE_ICON_ARG.findall(include))
    taxonomy = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
    for row in taxonomy["sectors"] + taxonomy["activities"]:
        if row.get("icon"):
            names.add(row["icon"])
    return {icons.icon_key(name) for name in names}


def empty_taxonomy(tmp_path, monkeypatch, sectors=(), activities=()) -> None:
    path = tmp_path / "taxonomy.json"
    path.write_text(
        json.dumps({"sectors": list(sectors), "activities": list(activities)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.TAXONOMY_FILE", path)


def render(source: str, **context) -> str:
    return Template("{% load icons %}" + source).render(Context(context))


@pytest.fixture
def baked(tmp_path, monkeypatch):
    """A baked JSON of our own, so the tests do not depend on which icons the templates cite today."""
    path = tmp_path / "public-icons.json"
    path.write_text(
        json.dumps(
            {
                "ion:cube-outline": {
                    "body": '<path d="M1 1h10"/>',
                    "viewBox": "0 0 512 512",
                },
                "lucide:check": {
                    "body": '<path d="M20 6 9 17l-5-5"/>',
                    "viewBox": "0 0 24 24",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(icons, "ICONS_FILE", path)
    icons.load_icons.cache_clear()
    yield path
    icons.load_icons.cache_clear()


def test_every_icon_the_public_pages_paint_is_baked():
    """The guardrail of spec §9: an icon that is not in the JSON would paint the fallback in production.

    Templates and taxonomy alike: a sector or business type icon missing from the JSON would paint
    the generic ``ion:business-outline`` on the industries pages.
    """
    baked_names = set(json.loads(ICONS_JSON.read_text(encoding="utf-8")))
    cited = cited_icons()

    assert cited, "the scanner found no icon in public/templates: it is blind"
    assert cited - baked_names == set(), "run `pnpm gen:public-icons`"


def test_the_baked_json_holds_only_what_the_public_pages_paint():
    """Only the icons the templates cite and the taxonomy names (spec §8.4): a stale entry is weight
    nobody paints."""
    baked_names = set(json.loads(ICONS_JSON.read_text(encoding="utf-8")))

    assert baked_names - cited_icons() == set(), "run `pnpm gen:public-icons`"


def test_the_scanner_reads_literal_tags_and_component_include_arguments(
    tmp_path, monkeypatch
):
    """Positive control of the reader above, on a template of its own."""
    folder = tmp_path / "templates"
    folder.mkdir()
    (folder / "page.html").write_text(
        '{% icon "construct-outline" %}'
        '{% include "public/components/feature_card.html" with icon="lucide:check" heading="x" %}'
        '{% include "public/partials/page_hero.html" with hero_icon="mdi:star" %}'
        '<p>icon="lucide:not-an-include"</p>'
        '{% comment %}Usage: {% include "x.html" with icon="lucide:example" %}{% endcomment %}'
        '{# {% icon "lucide:inline-comment" %} #}',
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.PUBLIC_TEMPLATES", folder)
    empty_taxonomy(tmp_path, monkeypatch)

    assert cited_icons() == {"ion:construct-outline", "lucide:check", "mdi:star"}


def test_the_scanner_reads_the_icon_of_every_sector_and_business_type(
    tmp_path, monkeypatch
):
    """Positive control of the taxonomy half: the industries pages paint these icons, no template cites them."""
    folder = tmp_path / "templates"
    folder.mkdir()
    monkeypatch.setattr(f"{__name__}.PUBLIC_TEMPLATES", folder)
    empty_taxonomy(
        tmp_path,
        monkeypatch,
        sectors=[{"code": "hospitality", "icon": "ion:restaurant-outline"}],
        activities=[
            {"code": "spa", "icon": "material-symbols:spa", "sector": "personal_services"},
            {"code": "cafe", "icon": "cafe-outline", "sector": "hospitality"},
            {"code": "no_icon_yet", "icon": "", "sector": "hospitality"},
        ],
    )

    assert cited_icons() == {
        "ion:restaurant-outline",
        "material-symbols:spa",
        "ion:cafe-outline",
    }


def test_the_real_taxonomy_icons_count_as_painted():
    """Not blind to the seed: its 58 distinct icons are all among the painted ones."""
    taxonomy = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
    seeded = {
        icons.icon_key(row["icon"])
        for row in taxonomy["sectors"] + taxonomy["activities"]
    }

    assert "material-symbols:spa" in seeded
    assert seeded <= cited_icons()


def test_a_name_without_a_set_is_an_ionicon():
    assert icons.icon_key("cube-outline") == "ion:cube-outline"
    assert icons.icon_key("ion:cube-outline") == "ion:cube-outline"
    assert icons.icon_key("lucide:check") == "lucide:check"


def test_the_tag_paints_the_baked_svg_inline(baked):
    html = render('{% icon "ion:cube-outline" %}')

    assert html.startswith("<svg ")
    assert 'viewBox="0 0 512 512"' in html
    assert '<path d="M1 1h10"/>' in html
    assert 'aria-hidden="true"' in html
    assert 'focusable="false"' in html
    # Sized by the font like Iconify's span was, and painted in the text colour.
    assert 'width="1em" height="1em"' in html
    assert 'fill="currentColor"' in html
    assert 'class="ep-icon"' in html
    assert "iconify" not in html
    assert "api.iconify.design" not in html


def test_the_default_set_is_ionicons(baked):
    assert '<path d="M1 1h10"/>' in render('{% icon "cube-outline" %}')


def test_size_class_and_extra_attributes(baked):
    html = render(
        '{% icon "lucide:check" size=20 css_class="dev-banner__icon" data_state="on" %}'
    )

    assert 'width="20" height="20"' in html
    assert 'class="ep-icon dev-banner__icon"' in html
    assert 'data-state="on"' in html


def test_attribute_values_are_escaped(baked):
    html = render(
        '{% icon "lucide:check" css_class=klass %}', klass='"><script>alert(1)</script>'
    )

    assert "<script>" not in html
    assert "&quot;&gt;&lt;script&gt;" in html


def test_a_variable_name_works_too(baked):
    """The component partials paint the icon their caller passes: ``{% icon icon %}``."""
    assert '<path d="M20 6 9 17l-5-5"/>' in render(
        "{% icon name %}", name="lucide:check"
    )


def test_an_icon_that_is_not_baked_fails_loudly_with_debug(baked, settings):
    settings.DEBUG = True

    with pytest.raises(
        icons.IconNotBaked, match=r"ion:not-there.*pnpm gen:public-icons"
    ):
        render('{% icon "not-there" %}')


def test_an_icon_that_is_not_baked_paints_the_fallback_and_warns_in_production(
    baked, settings, caplog
):
    settings.DEBUG = False

    with caplog.at_level(logging.WARNING, logger="public.templatetags.icons"):
        html = render('{% icon "not-there" %}')

    assert html == render('{% icon "not-there" %}')
    assert html.startswith("<svg ") and icons.FALLBACK_BODY in html
    assert any("ion:not-there" in record.getMessage() for record in caplog.records)


def test_the_baked_file_is_read_once_per_change(baked):
    first = icons.load_icons()
    assert icons.load_icons() is first

    baked.write_text(
        json.dumps({"lucide:x": {"body": "<path/>", "viewBox": "0 0 24 24"}}),
        encoding="utf-8",
    )
    icons.load_icons.cache_clear()

    assert set(icons.load_icons()) == {"lucide:x"}


def test_the_tag_never_reaches_the_network(baked, monkeypatch):
    """It reads the JSON on disk and nothing else (spec §8.4: no network call for icons)."""
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("the icon tag opened a socket")

    monkeypatch.setattr(socket.socket, "connect", no_network)

    assert render('{% icon "lucide:check" %}').startswith("<svg ")
