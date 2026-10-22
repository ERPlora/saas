"""``/help/`` and the help guides it renders (public/help.py, ``docs/<lang>/help/*.md``).

Port of ``apps/dashboard/core/help_docs.py`` and its suite ``apps/dashboard/help/tests/test_help_docs.py``
(9), plus the help case of ``apps/public/resources/test_views.py`` and of
``tests/unit/test_public_pages.py`` (origin/develop c5ca8ca). What changed, and why (spec §7, §12;
plan §3.d):

* only ``en`` and ``es`` ship (``fr``, ``it``, ``de`` and ``pt`` are out of scope): the case that
  read a German placeholder now builds its own placeholder in Spanish;
* ``03-bridge.md`` (the Bridge, ADR-0196) and ``04-modules.md`` (the module marketplace) are
  retired, and the rest are renumbered ``01``…``05``; no guide speaks of either;
* the markdown is rendered by ``live.markdown.render_markdown`` (headings get their ``id``);
* the page is the public web's: ``ep-*`` classes instead of OutfitKit's, ``{% icon %}`` instead of
  ``<iconify-icon>``.
"""

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from public import help as help_docs

ROOT = Path(settings.BASE_DIR)

# ADR-0196 deleted the standalone Bridge app (one single `erplora-app` IS the hardware access) and
# ADR-0254 dropped the word from the product vocabulary. AWS "EventBridge" is another product.
_RETIRED_BRIDGE_RE = re.compile(r"(?<!event)\bbridge\b", re.IGNORECASE)
# The dead WebSocket of the standalone Bridge and its retired public page.
_RETIRED_BRIDGE_MARKERS = ("12321", "(/bridge/)")


def _help_files():
    """Every help guide on disk, across the shipped languages."""
    root = help_docs._docs_root()
    return sorted(
        path
        for lang in help_docs.SUPPORTED_LANGS
        for path in (root / lang / "help").glob("*.md")
    )


@pytest.fixture
def docs_root(tmp_path, monkeypatch):
    """A help tree of the test's own; the cache is cleared before and after."""
    help_docs._load.cache_clear()
    monkeypatch.setattr(help_docs, "_docs_root", lambda: tmp_path)
    yield tmp_path
    help_docs._load.cache_clear()


def write_doc(root: Path, lang: str, name: str, text: str) -> None:
    directory = root / lang / "help"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


# --- The service (test_help_docs.py) ---------------------------------------------------------


def test_list_docs_returns_repo_guides():
    """The in-repo guides (docs/<lang>/help/) are listed, ordered."""
    docs = help_docs.list_docs("es")
    ids = [doc["id"] for doc in docs]

    assert ids == [
        "01-getting-started",
        "02-installation",
        "03-users-and-roles",
        "04-settings",
        "05-faq",
    ]
    # Every entry has a human title (from the H1 or the fallback map).
    assert all(doc["title"] for doc in docs)


def test_list_docs_falls_back_to_default_lang_for_unknown():
    """An unsupported language falls back to the default so help is never empty."""
    assert [doc["id"] for doc in help_docs.list_docs("xx")] == [
        doc["id"] for doc in help_docs.list_docs("en")
    ]


def test_get_doc_renders_sanitized_html():
    """A known doc renders to HTML through live.markdown: tags, heading ids, no script."""
    doc = help_docs.get_doc("05-faq", "es")

    assert doc is not None
    assert doc["id"] == "05-faq"
    assert doc["title"] == "Preguntas frecuentes"
    assert '<h2 id="acceso">Acceso</h2>' in doc["html"]
    assert "<script" not in doc["html"].lower()


def test_get_doc_escapes_what_a_guide_must_not_carry(docs_root):
    write_doc(
        docs_root,
        "en",
        "01-a.md",
        "# A\n\nText <script>alert(1)</script> and ![x](https://evil.example/x.png)\n",
    )

    html = help_docs.get_doc("01-a", "en")["html"]

    assert "<script" not in html
    assert "evil.example" not in html


def test_get_doc_unknown_id_returns_none():
    """An unknown / path-traversal id is rejected (no escape from the help directory)."""
    assert help_docs.get_doc("../../config/settings", "es") is None
    assert help_docs.get_doc("does-not-exist", "es") is None


@pytest.mark.parametrize("crafted", ["../../UI-REQUESTS-panel", "../../../README"])
def test_get_doc_never_reads_a_markdown_file_outside_the_guides(crafted):
    """PUBLIC-G21: the id is checked against the guides, so an existing file next to them never leaks."""
    assert (Path(settings.BASE_DIR) / "docs" / "en" / "help" / f"{crafted}.md").resolve().is_file()

    assert help_docs.get_doc(crafted, "en") is None


def test_pending_translation_falls_back_to_english_source(docs_root):
    """A placeholder locale file must not produce an empty help article."""
    write_doc(docs_root, "en", "01-start.md", "# First access\n\nOn a new device.\n")
    write_doc(docs_root, "es", "01-start.md", "<!-- pending translation from en -->\n")

    doc = help_docs.get_doc("01-start", "es")

    assert doc is not None
    assert doc["title"] == "First access"
    assert "On a new device." in doc["html"]


def test_a_language_without_guides_falls_back_to_english(docs_root):
    write_doc(docs_root, "en", "01-start.md", "# First access\n\nBody.\n")

    assert [section["title"] for section in help_docs.all_sections("es")] == [
        "First access"
    ]


def test_resolve_lang_uses_active_language():
    """resolve_lang honours the active translation when supported."""
    with translation.override("es"):
        assert help_docs.resolve_lang() == "es"
    with translation.override("en"):
        assert help_docs.resolve_lang() == "en"
    with translation.override("de"):
        assert help_docs.resolve_lang() == help_docs.DEFAULT_LANG


def test_all_sections_renders_every_doc():
    sections = help_docs.all_sections("en")

    assert len(sections) == len(help_docs.list_docs("en"))
    assert all({"id", "title", "html"} <= set(section) for section in sections)


def test_only_english_and_spanish_ship():
    assert help_docs.SUPPORTED_LANGS == ("en", "es")
    for lang in help_docs.SUPPORTED_LANGS:
        assert [path.name for path in (ROOT / "docs" / lang / "help").glob("*.md")]


def test_both_languages_ship_the_same_guides():
    en = sorted(path.name for path in (ROOT / "docs" / "en" / "help").glob("*.md"))
    es = sorted(path.name for path in (ROOT / "docs" / "es" / "help").glob("*.md"))

    assert en == es


def test_help_docs_do_not_document_the_retired_bridge():
    """The help must not sell a product ADR-0196 deleted (saas#1275)."""
    offenders = []
    for path in _help_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if _RETIRED_BRIDGE_RE.search(line) or any(
                marker in line for marker in _RETIRED_BRIDGE_MARKERS
            ):
                offenders.append(f"{path.name}:{number}: {line.strip()}")

    assert not offenders, "\n".join(offenders)


def test_help_docs_do_not_speak_of_a_marketplace():
    """Every app is ours: there is no module marketplace to install from (spec §8.3)."""
    offenders = [
        str(path.relative_to(ROOT))
        for path in _help_files()
        if "marketplace" in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == []


@pytest.mark.django_db
def test_help_docs_link_only_to_pages_that_exist(client):
    """A relative link in a guide is a public page: each must be a route of the public web."""
    links = set()
    for path in _help_files():
        links |= set(re.findall(r"\]\((/[^)]*)\)", path.read_text(encoding="utf-8")))

    assert links, "the guides link the support and download pages"
    for link in links:
        assert client.get(link).status_code == 200, link


def test_every_listed_help_doc_is_readable():
    """A doc in the index that cannot be rendered is a hole in the help center."""
    for lang in help_docs.SUPPORTED_LANGS:
        for entry in help_docs.list_docs(lang):
            document = help_docs.get_doc(entry["id"], lang)
            assert document is not None, (
                f"{lang}/{entry['id']} is listed but does not render"
            )
            assert document["html"].strip(), f"{lang}/{entry['id']} renders empty"


def test_the_help_guides_ship_in_the_image():
    """The image's build context drops ``docs/`` (research notes, issues) but not the help."""
    rules = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    # Every way of writing «drop docs/»: the exceptions must come after the last of them (the last
    # matching pattern wins).
    dropping = [
        index
        for index, rule in enumerate(rules)
        if rule.removesuffix("/**").rstrip("/") in {"docs", "/docs"}
    ]
    assert dropping, "the check is moot: docs/ is no longer dropped (then nothing to keep)"
    for lang in help_docs.SUPPORTED_LANGS:
        keep = f"!docs/{lang}/help/**"
        assert keep in rules, keep
        assert rules.index(keep) > max(dropping), keep


# --- The page ---------------------------------------------------------------------------------


@pytest.mark.django_db
def test_help_center_uses_ionic_accordions(client):
    sections = [
        {"id": "getting-started", "title": "Getting Started", "html": "<p>Welcome</p>"},
        {"id": "inventory", "title": "Inventory", "html": "<p>Stock guide</p>"},
    ]

    with patch("public.help.all_sections", return_value=sections):
        response = client.get("/help/")

    assert response.status_code == 200
    html = response.content.decode()
    assert '<ion-accordion-group expand="inset"' in html
    assert html.count("<ion-accordion ") == 2
    assert 'value="getting-started"' in html
    assert "<p>Stock guide</p>" in html
    assert "<details" not in html
    assert "<iconify-icon" not in html


@pytest.mark.django_db
def test_help_center_renders_repo_guides(client):
    """The FAQ guide title proves the page reads the in-repo docs."""
    body = client.get("/help/").content.decode().lower()

    assert "frequently asked questions" in body


@pytest.mark.django_db
def test_help_center_in_spanish(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
    html = client.get("/help/").content.decode()

    assert "Centro de ayuda." in html
    assert "Preguntas frecuentes" in html
    assert "Buscar en la ayuda..." in html


@pytest.mark.django_db
def test_help_center_says_so_when_there_is_no_guide(client):
    with patch("public.help.all_sections", return_value=[]):
        html = client.get("/help/").content.decode()

    assert "No help documentation found." in html
    assert "ep-inline-feedback" in html
    assert "<ion-accordion " not in html


@pytest.mark.django_db
def test_help_center_search_has_its_no_results_state(client):
    html = client.get("/help/").content.decode()

    assert '<ion-searchbar id="help-search"' in html
    assert 'id="help-no-results" hidden' in html
    assert "No guides found" in html
    assert 'class="ep-empty-state"' in html


@pytest.mark.django_db
def test_help_center_page_basics(client):
    response = client.get("/help/")
    html = response.content.decode()

    assert reverse("public:help") == "/help/"
    assert "<title>Help · ERPlora</title>" in html
    assert '<meta name="robots" content="noindex, follow">' in html
    assert '<footer class="ep-footer"' in html
    assert client.post("/help/").status_code == 405


def test_help_docs_do_not_name_the_old_hosting():
    """The servers are on AWS, Ireland region, not on Hetzner in Germany (Ioan, 2026-10-13)."""
    offenders = [
        f"{path.relative_to(ROOT)}: {name}"
        for path in _help_files()
        for name in ("hetzner", "falkenstein", "germany", "alemania")
        if name in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == []
