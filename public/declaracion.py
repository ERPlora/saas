"""The declaración responsable of the Hub (art. 13 RRSIF, RD 1007/2023): its archive and its public
pages, ``/legal/declaracion-responsable/``, ``<version>/`` and ``<version>/pdf/`` (spec §8.1, plan §3.e).

Ported from ERPlora/saas (origin/develop c5ca8ca): the archive service
``apps/dashboard/fiscal/services/declaracion_responsable.py`` and the two views of
``apps/public/legal/views.py``. The route is Spanish on purpose: it is the legal term the customer,
the reseller and the AEAT look up.

ERPlora is the **producer** of a SIF, and art. 13 makes the producer certify compliance by its own
responsible declaration: there is neither third-party certification nor prior registration (AEAT
FAQ «Certificación de los sistemas informáticos: declaración responsable», 22/07/2026). We sign it,
publish it and keep it. Art. 13 asks three things of this archive:

* **13.2: available** to the customer and the reseller at the moment of purchase, so the page is
  public, before anyone has an account;
* **13.3: every version is kept.** :func:`declarations` parses every directory it finds and raises
  on the one it cannot read: an archive that skips what it does not understand is not an archive;
* **13.4: identifying data.** Each version carries a machine-readable ``declared-facts.json`` next
  to the signed text, and ``public/tests/test_declaracion.py`` asserts the text quotes every value.

The archive lives in ``public/declaracion/``: one directory per version (``v1``, ``v2``…) with
``declaracion-responsable.md`` (the text that is signed and handed over), ``declared-facts.json``
(``modality``, ``covers_from``, ``composition``, ``signed_on``, ``signed_at``, ``status``,
``signed_pdf`` and ``facts``) and, once signed, the PDF that ``signed_pdf`` names. A new version is a
new directory with ``status: "pending_signature"``; once the legal representative of ERPLORA CLOUD SL
signs the PDF (PAdES), it is added and the JSON says ``signed`` and names it. No version is ever
withdrawn (art. 13.3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe
from live.markdown import render_markdown

#: Where the archive lives: one directory per version. Inside the app, not in a docs folder:
#: art. 13.2 makes it part of the product, not documentation about it.
DECLARATIONS_DIR = Path(__file__).resolve().parent / "declaracion"

#: The declared modality: the product can only be used in VERI*FACTU mode. Declaring DUAL would make
#: the *registro de eventos* mandatory (developer FAQ §15, note 1), which it does not implement.
MODALITY_SOLO_VERIFACTU = "SOLO VERI*FACTU"

#: File names inside a version directory.
TEXT_FILENAME = "declaracion-responsable.md"
FACTS_FILENAME = "declared-facts.json"


@dataclass(frozen=True)
class Declaration:
    """One version of the declaration: the signed text plus the facts it certifies."""

    version: str
    modality: str
    #: First version of the PRODUCT (the Hub binary) this declaration covers, until the next one
    #: starts. Hub semver, NOT the declaration's ``v1``/``v2``.
    covers_from: str
    #: The components of the SIF in the versions it covers, named as the signed text names them.
    composition: tuple[str, ...]
    signed_on: date
    signed_at: str
    status: str
    #: File name of the SIGNED PDF inside the version's directory, or ``""`` while there is none.
    #: A file name, never a path: whoever serves it resolves it INSIDE the archive.
    signed_pdf: str
    facts: dict[str, str]
    text: str

    @property
    def is_signed(self) -> bool:
        """Is there a signed copy to hand over? (art. 13.2)

        The status is what is declared; this is what can be served. A ``signed`` status without a
        PDF would be a page promising a download that answers 404.
        """
        return self.status == "signed" and bool(self.signed_pdf)

    def signed_pdf_path(self) -> Path | None:
        """Absolute path of the signed PDF, or ``None``.

        The name comes from the archive's JSON and is resolved **inside the version's directory**:
        if the result leaves it, it is not served. We write that field ourselves, but a file sent
        over HTTP is not resolved by trusting that a value in the repo is sane.
        """
        if not self.is_signed:
            return None
        base = (DECLARATIONS_DIR / self.version).resolve()
        candidate = (base / self.signed_pdf).resolve()
        return candidate if candidate.parent == base and candidate.is_file() else None

    @staticmethod
    def version_sort_key(version: str) -> int:
        """``v10`` sorts after ``v9``: a lexicographic sort would hand out the wrong current one.

        :raises ValueError: for anything that is not ``v<number>``. A directory nobody can order
            has no place in an archive that must be complete (art. 13.3).
        """
        if not version.startswith("v") or not version[1:].isdigit():
            raise ValueError(f"not a declaration version directory: {version!r}")
        return int(version[1:])

    @property
    def sort_key(self) -> int:
        return self.version_sort_key(self.version)


def _load(version_dir: Path) -> Declaration:
    raw = json.loads((version_dir / FACTS_FILENAME).read_text(encoding="utf-8"))
    return Declaration(
        version=version_dir.name,
        modality=raw["modality"],
        covers_from=raw["covers_from"],
        composition=tuple(raw["composition"]),
        signed_on=date.fromisoformat(raw["signed_on"]),
        signed_at=raw["signed_at"],
        status=raw["status"],
        signed_pdf=raw.get("signed_pdf") or "",
        facts=dict(raw["facts"]),
        text=(version_dir / TEXT_FILENAME).read_text(encoding="utf-8"),
    )


def declarations() -> list[Declaration]:
    """Every version kept in the archive, oldest first (art. 13.3).

    Read from disk on every call on purpose: a handful of small files, and a cache on a legal
    artefact buys microseconds in exchange for the chance of serving a stale one.
    """
    return sorted(
        (_load(path) for path in DECLARATIONS_DIR.iterdir() if path.is_dir()),
        key=lambda declaration: declaration.sort_key,
    )


def current_declaration() -> Declaration:
    """The declaration in force: the one shown in the product and handed over at purchase."""
    return declarations()[-1]


def latest_signed_declaration() -> Declaration | None:
    """The newest version with a signed copy to hand over, or ``None`` if there is none.

    Not the same question as :func:`current_declaration`: the text goes up when it is written and
    the signed PDF when it is signed, and in between the version in force has no copy to deliver.
    The archive never withdraws one (art. 13.3), so what can be delivered then is the previous
    signature. ``None`` rather than an exception: an archive with nothing signed is a state the
    page has to render, not an error.
    """
    return next(
        (
            declaration
            for declaration in reversed(declarations())
            if declaration.is_signed
        ),
        None,
    )


def render_declaration(declaration: Declaration) -> str:
    """The signed text as HTML: ``live.markdown`` (``tables`` for the identifying data of art.
    13.4) and its allowlist. The source is a file of this repository, never user input, but "it
    is our own file" is exactly the assumption that ages badly."""
    return render_markdown(declaration.text)


@require_safe
def declaracion_responsable(
    request: HttpRequest, version: str | None = None
) -> HttpResponse:
    """The declaración responsable in force (or ``version``) and the archive of every version.

    ``version`` is matched against the archive, never joined onto a path: an unknown or crafted
    value is a 404, not a file read.
    """
    archive = declarations()
    if version is None:
        declaration = current_declaration()
    else:
        declaration = next((d for d in archive if d.version == version), None)
        if declaration is None:
            raise Http404("no such declaration version")

    return render(
        request,
        "public/legal/declaracion_responsable.html",
        {
            "declaration": declaration,
            "declaration_html": render_declaration(declaration),
            "archive": list(reversed(archive)),
            "is_current": declaration == archive[-1],
            # The latest SIGNED copy, not always the one in force: between publishing a version
            # and signing it, the previous signature is the one that can be handed over.
            "latest_signed": latest_signed_declaration(),
        },
    )


@require_safe
def declaracion_responsable_pdf(request: HttpRequest, version: str) -> FileResponse:
    """The SIGNED copy of a version (art. 13.2): what is handed to the customer and the reseller,
    and what holds before an inspection.

    **Byte for byte, or the signature is worthless.** A PAdES signature covers a given
    ``/ByteRange`` of the file: recompressing it, "optimising" it, rewriting its XMP or stamping it
    invalidates it, and the document keeps opening, so nobody notices until someone validates it.
    So no generation, no template, no post-processing: ``FileResponse`` over the archived file.

    **Inline by default, ``?download=1`` to save it.** A browser's PDF viewer does not check
    signatures; verifying it means downloading it and opening it with AutoFirma, Adobe or VALIDe.
    The page offers both and says which is for what.

    A 404 when the version does not exist **or is not signed yet**: promising a download that is
    not there is worse than saying there is none.
    """
    declaration = next((d for d in declarations() if d.version == version), None)
    if declaration is None:
        raise Http404("no such declaration version")

    path = declaration.signed_pdf_path()
    if path is None:
        raise Http404("this version has no signed copy yet")

    return FileResponse(
        path.open("rb"),
        content_type="application/pdf",
        as_attachment=bool(request.GET.get("download")),
        filename=f"declaracion-responsable-erplora-hub-{declaration.version}.pdf",
    )
