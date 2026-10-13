"""The help center: ``/help/`` and the guides it renders, ``docs/<lang>/help/*.md``.

Port of ``apps/dashboard/core/help_docs.py`` and of the ``help_center`` view of
``apps/public/resources`` (origin/develop c5ca8ca). The guides live in the repository, one markdown
file per guide and language, ordered by their numeric prefix; this module lists and renders them
with ``live.markdown.render_markdown`` (markdown + nh3, ids on the headings). Only ``en`` and ``es``
ship (spec §7, §12); a language without guides, or a guide still marked
``<!-- pending translation from en -->``, falls back to English, so the help is never empty.

The in-app help of the Hub and of the panel is out of scope (spec §12): this is the public page.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import get_language
from django.views.decorators.http import require_safe
from live.markdown import render_markdown

#: The languages that ship help guides under ``docs/<lang>/help/``.
SUPPORTED_LANGS = ("en", "es")
DEFAULT_LANG = "en"

#: A guide's title when its file has no leading ``# Heading`` (the H1 wins when present).
_FALLBACK_TITLES = {
    "01-getting-started": "Getting Started",
    "02-installation": "Installation",
    "03-users-and-roles": "Users & Roles",
    "04-settings": "Settings",
    "05-faq": "FAQ",
}

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_PENDING_TRANSLATION_RE = re.compile(
    r"^\s*<!--\s*pending translation from en\s*-->\s*$", re.IGNORECASE
)


def _is_pending_translation(raw: str) -> bool:
    """Whether a guide is only an untranslated placeholder (or empty)."""
    return not raw.strip() or bool(_PENDING_TRANSLATION_RE.fullmatch(raw))


def _docs_root() -> Path:
    return Path(settings.BASE_DIR) / "docs"


def _help_dir(lang: str) -> Path:
    return _docs_root() / lang / "help"


def resolve_lang(lang: str | None = None) -> str:
    """A shipped help language: the given one, else the active one, else the default."""
    code = (lang or get_language() or DEFAULT_LANG)[:2]
    return code if code in SUPPORTED_LANGS else DEFAULT_LANG


def _split_title(raw: str, stem: str) -> tuple[str, str]:
    """``(title, body without its H1)`` of a guide."""
    match = _H1_RE.search(raw)
    if match and match.start() < 4:  # a leading H1 only
        body = (raw[: match.start()] + raw[match.end() :]).strip()
        return match.group(1).strip(), body
    return _FALLBACK_TITLES.get(stem, stem.replace("-", " ").title()), raw


@lru_cache(maxsize=len(SUPPORTED_LANGS) + 1)
def _load(lang: str) -> tuple[dict, ...]:
    """``{id, title}`` of every guide of ``lang``, by file name (cached: immutable on disk)."""
    directory = _help_dir(lang)
    if not directory.is_dir():
        return ()
    docs = []
    for path in sorted(directory.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        if _is_pending_translation(raw):
            continue
        title, _body = _split_title(raw, path.stem)
        docs.append({"id": path.stem, "title": title})
    return tuple(docs)


def list_docs(lang: str | None = None) -> list[dict]:
    """``{id, title}`` of the guides of the language, in reading order (English as fallback)."""
    resolved = resolve_lang(lang)
    docs = _load(resolved)
    if not docs and resolved != DEFAULT_LANG:
        docs = _load(DEFAULT_LANG)
    return [dict(doc) for doc in docs]


def get_doc(doc_id: str, lang: str | None = None) -> dict | None:
    """One rendered guide ``{id, title, html}``, or ``None`` if there is no such guide.

    ``doc_id`` is checked against the guides on disk, so a crafted value can never leave the help
    directory (no path traversal).
    """
    resolved = resolve_lang(lang)
    known = {doc["id"] for doc in _load(resolved)} or {
        doc["id"] for doc in _load(DEFAULT_LANG)
    }
    if doc_id not in known:
        return None

    path = _help_dir(resolved) / f"{doc_id}.md"
    raw = path.read_text(encoding="utf-8") if path.is_file() else ""
    if _is_pending_translation(raw) and resolved != DEFAULT_LANG:
        path = _help_dir(DEFAULT_LANG) / f"{doc_id}.md"
        raw = path.read_text(encoding="utf-8") if path.is_file() else ""
    if _is_pending_translation(raw):
        return None
    title, body = _split_title(raw, doc_id)
    return {"id": doc_id, "title": title, "html": render_markdown(body)}


def all_sections(lang: str | None = None) -> list[dict]:
    """Every guide rendered as ``{id, title, html}``: the accordions of ``/help/``."""
    sections = (get_doc(doc["id"], lang) for doc in list_docs(lang))
    return [section for section in sections if section is not None]


@require_safe
def help_center(request: HttpRequest) -> HttpResponse:
    """``/help/``: the guides in the visitor's language, one accordion each, with a search."""
    return render(request, "public/resources/help.html", {"sections": all_sections()})
