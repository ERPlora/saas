"""What the panel's assistant knows of ERPlora (ASSISTANT-F27; plan 2026-10-30-asistente-saas §5): the documentation,
cut into the excerpts ``assistant.docs.search`` returns and ``index_docs`` keeps with their fingerprints.

- ``chunk_markdown`` cuts a document at its ``##`` and ``###`` headings (a FAQ's questions are ``###``), names each
  excerpt by its path of headings («FAQ > Access > Why…?») and windows a long section into excerpts of ``MAX_WORDS``
  words that overlap by ``OVERLAP_WORDS``: a sentence cut at the edge of one is whole in the next. HTML comments go;
  a heading inside a code block is text. The idea of the old product's in-memory index (``apps/dashboard/assistant/
  knowledge.py``), without its store: the excerpts live in ``assistant.DocChunk``.
- The four sources (``SOURCES``), each in English and Spanish: the public help (``docs/<lang>/help/*.md``; a guide
  still waiting for its translation is only its ``<!-- pending translation from en -->``, with no excerpt); the user documentation of the Hub's apps
  (``apps.doc.list``, what the Hub registers with each release); the customer's part of the WORKBOOKs of the panel's
  apps (``WORKBOOK_APPS``: from their first ``##`` to «Para quien lo mantiene», never what is written for the
  maintainers); and one document of the plans on sale (``hubs.plan.list``) with their prices and what each one
  includes, so the assistant never quotes a price from memory.

Nothing here touches the database: the catalogue and the plans are read through their operations.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from django.conf import settings
from django.utils import formats, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from apps import queries as apps_queries
from apps.schemas import AppDocListIn
from assistant.models import content_hash
from assistant.services import platform_context
from hubs import queries as hubs_queries
from hubs.schemas import PlanListIn
from public import help as public_help

#: The words of an excerpt, and how many of them the next one repeats.
MAX_WORDS = 220
OVERLAP_WORDS = 50
#: What of an excerpt its fingerprint is computed from, at most: well under the 8192 tokens the model reads at once,
#: so one huge «word» (an address, a picture written inline) never makes the provider refuse the whole batch.
MAX_EMBEDDING_CHARS = 6000
SOURCES = ("help", "app_doc", "workbook", "plans")
#: The languages the documentation is written in.
LANGUAGES = ("en", "es")
#: The apps of the panel whose WORKBOOK speaks to the customer, each with the name its excerpts carry.
WORKBOOK_APPS = {
    "accounts": gettext_lazy("Account"),
    "hubs": gettext_lazy("Businesses"),
    "billing": gettext_lazy("Billing"),
    "apps": gettext_lazy("Apps"),
    "public": "erplora.com",
}
#: Each language's WORKBOOK file.
WORKBOOK_FILES = (("WORKBOOK.md", "es"), ("WORKBOOK.en.md", "en"))
#: Where the customer's part of a WORKBOOK ends (``base.catalog.MAINTAINERS_HEADING`` of the Hub); a translation
#: already stops there, but would it carry the heading, it stops at its English words.
MAINTAINERS_HEADINGS = frozenset({"## Para quien lo mantiene", "## For whoever maintains it", "## For maintainers"})

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


class WorkbookWithoutCut(Exception):
    """A WORKBOOK without the heading where its customer's part ends: nothing of it is indexed."""


@dataclass(frozen=True)
class Section:
    """An excerpt of a document: its path of headings and its text, in one line."""

    heading: str
    text: str


@dataclass(frozen=True)
class Chunk:
    """An excerpt of a source, where it comes from (``path``) and in which language."""

    source: str
    path: str
    lang: str
    heading: str
    text: str

    @property
    def content_hash(self) -> str:
        """What tells one excerpt from another (``assistant.models.content_hash``)."""
        return content_hash(self.source, self.path, self.lang, self.heading, self.text)

    @property
    def embedding_text(self) -> str:
        """What its fingerprint is computed from: its headings weigh as much as its words."""
        return (f"{self.heading}\n{self.text}" if self.heading else self.text)[:MAX_EMBEDDING_CHARS]


def _windows(words: list[str], max_words: int, overlap_words: int) -> list[list[str]]:
    if len(words) <= max_words:
        return [words]
    step = max(1, max_words - overlap_words)
    out = []
    for start in range(0, len(words), step):
        out.append(words[start : start + max_words])
        if start + max_words >= len(words):
            break
    return out


def chunk_markdown(
    text: str, *, title: str = "", max_words: int = MAX_WORDS, overlap_words: int = OVERLAP_WORDS
) -> list[Section]:
    """The excerpts of a markdown document, in reading order. ``title`` names a document without its own ``#``
    (and wins over it)."""
    heads = {1: title, 2: "", 3: ""}
    sections: list[tuple[str, list[str]]] = []
    body: list[str] = []

    def close() -> None:
        found = " ".join(body).split()
        if found:
            sections.append((" > ".join(head for head in heads.values() if head), found))
        body.clear()

    in_code = False
    for line in _COMMENT.sub("", text.replace("\r\n", "\n")).split("\n"):
        if _FENCE.match(line):
            in_code = not in_code
            body.append(line)
            continue
        heading = None if in_code else _HEADING.match(line)
        if heading is None:
            body.append(line)
            continue
        close()
        level, name = len(heading.group(1)), heading.group(2).strip()
        if level == 1:
            heads[1] = title or name
            heads[2] = heads[3] = ""
        elif level == 2:
            heads[2], heads[3] = name, ""
        else:
            heads[3] = name
    close()
    return [
        Section(heading, " ".join(piece))
        for heading, found in sections
        for piece in _windows(found, max_words, overlap_words)
    ]


def _chunks(source: str, path: str, lang: str, text: str, title: str = "") -> list[Chunk]:
    return [Chunk(source, path, lang, piece.heading, piece.text) for piece in chunk_markdown(text, title=title)]


# --- The sources -----------------------------------------------------------------------------------------------


def help_chunks(root: Path) -> list[Chunk]:
    """The guides of ``/help/`` in each language they are written in."""
    chunks = []
    for lang in public_help.SUPPORTED_LANGS:
        for path in sorted((root / "docs" / lang / "help").glob("*.md")):
            # A guide still waiting for its translation is only its marker, a comment: it has no excerpt.
            chunks += _chunks("help", path.relative_to(root).as_posix(), lang, path.read_text(encoding="utf-8"))
    return chunks


def app_doc_chunks() -> list[Chunk]:
    """The user documentation of every app of the Hub the store lists, named by the app."""
    docs = apps_queries.doc_list(platform_context(), AppDocListIn()).docs
    chunks = []
    for doc in docs:
        chunks += _chunks("app_doc", f"app_doc:{doc.app}", doc.lang, doc.markdown, title=doc.name)
    return chunks


def user_part(text: str, where: str) -> str:
    """The customer's part of a WORKBOOK: from its first ``##`` to where the maintainers' starts. A Spanish one
    without that heading is refused (its whole text would be published by mistake)."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = next((index for index, line in enumerate(lines) if line.startswith("## ")), None)
    end = next((index for index, line in enumerate(lines) if line.rstrip() in MAINTAINERS_HEADINGS), None)
    if end is None and not where.endswith(".en.md"):
        raise WorkbookWithoutCut(f"{where}: no «## Para quien lo mantiene» heading where the customer's part ends.")
    if start is None or (end is not None and start >= end):
        return ""
    return "\n".join(lines[start:end])


def workbook_chunks(root: Path) -> list[Chunk]:
    """The customer's part of the WORKBOOK of each app of the panel, in Spanish and in its English translation."""
    chunks = []
    for app, name in WORKBOOK_APPS.items():
        for filename, lang in WORKBOOK_FILES:
            path = root / app / filename
            if not path.is_file():
                continue
            where = f"{app}/{filename}"
            with translation.override(lang):
                title = str(name)
            chunks += _chunks("workbook", where, lang, user_part(path.read_text(encoding="utf-8"), where), title)
    return chunks


def _price(value) -> str:
    return formats.number_format(value, decimal_pos=2, use_l10n=True)


def _counted(count: int, none: str, some: str) -> str:
    """``none`` for 0 (no limit, or nothing at all), else ``some`` with the count."""
    return none if count == 0 else some % {"count": count}


def _plan_markdown(plan) -> str:
    """One plan as its section of the document, in the active language."""
    lines = [f"## {plan.name}", ""]
    if plan.description:
        lines.append(plan.description)
    lines.append(
        _("%(monthly)s € a month or %(annual)s € a year, VAT excluded.")
        % {"monthly": _price(plan.price_monthly), "annual": _price(plan.price_annual)}
    )
    users, devices, apps = plan.max_users, plan.max_devices, plan.max_apps
    assistant, whatsapp = plan.assistant_messages_per_month, plan.whatsapp_messages_per_month
    lines += [
        _counted(users, _("Unlimited users."), ngettext("Up to %(count)s user.", "Up to %(count)s users.", users)),
        _counted(
            devices, _("Unlimited devices."), ngettext("Up to %(count)s device.", "Up to %(count)s devices.", devices)
        ),
        _counted(
            apps,
            _("No limit on the apps turned on."),
            ngettext(
                "Up to %(count)s app turned on at once, besides the ones it requires.",
                "Up to %(count)s apps turned on at once, besides the ones they require.",
                apps,
            ),
        ),
        _counted(
            assistant,
            _("No assistant."),
            ngettext(
                "%(count)s message a month with the assistant.", "%(count)s messages a month with the assistant.", assistant
            ),
        ),
        _counted(
            whatsapp,
            _("No WhatsApp messages."),
            ngettext("%(count)s WhatsApp message a month.", "%(count)s WhatsApp messages a month.", whatsapp),
        ),
    ]
    if plan.upgrade_only:
        lines.append(_("Not chosen when signing up: only as an upgrade from another plan."))
    if plan.features:
        lines.append(_("Includes: %(features)s.") % {"features": "; ".join(str(feature) for feature in plan.features)})
    return "\n".join(lines)


def plans_chunks() -> list[Chunk]:
    """The plans on sale, one document per language, each plan a section of its own."""
    chunks = []
    for lang in LANGUAGES:
        plans = hubs_queries.plan_list(replace(platform_context(), language=lang), PlanListIn())
        with translation.override(lang):
            title = _("ERPlora plans")
            document = [_("The plans a business can have on ERPlora, with their prices and what each one includes.")]
            if plans.signup_trial_days:
                document.append(
                    ngettext(
                        "A sign-up gets a trial of %(count)s day.",
                        "A sign-up gets a trial of %(count)s days.",
                        plans.signup_trial_days,
                    )
                    % {"count": plans.signup_trial_days}
                )
            document += [_plan_markdown(plan) for plan in plans.plans]
        chunks += _chunks("plans", "plans", lang, "\n\n".join(document), title=title)
    return chunks


def collect(source: str, root: Path | None = None) -> list[Chunk]:
    """Every excerpt of ``source`` (one of ``SOURCES``), its files read under ``root`` (the project's)."""
    root = Path(settings.BASE_DIR) if root is None else root
    readers: dict[str, Callable[[], list[Chunk]]] = {
        "help": lambda: help_chunks(root),
        "app_doc": app_doc_chunks,
        "workbook": lambda: workbook_chunks(root),
        "plans": plans_chunks,
    }
    if source not in readers:
        raise ValueError(f"Unknown source {source!r}: one of {', '.join(SOURCES)}.")
    return readers[source]()
