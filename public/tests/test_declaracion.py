"""The declaración responsable of the Hub (art. 13 RRSIF, RD 1007/2023), its archive and its signed
PDF: ``/legal/declaracion-responsable/``, ``<version>/`` and ``<version>/pdf/`` (spec §8.1, plan §3.e).

The route is Spanish on purpose: it is the legal term the customer, the reseller and the AEAT
inspector look up.

Ported from ERPlora/saas (origin/develop c5ca8ca):

* ``apps/public/legal/tests/test_declaracion_responsable_page.py`` (7) — art. 13.2: the declaration
  has to be *available* to the customer and the reseller at acquisition, so the page is public; and
  art. 13.3 (*"deberá guardar y conservar las declaraciones responsables de todas las versiones"*)
  makes it an **archive** in which every version is reachable;
* ``apps/public/legal/tests/test_declaracion_responsable_pdf.py`` (20) — the signed copy is served
  **byte for byte**, or the PAdES signature over its ``/ByteRange`` stops being valid (and the
  document keeps opening, so nobody notices); inline by default, ``?download=1`` to save it (a
  browser's PDF viewer does not check signatures); a 404 when there is no signed copy;
* the archive half of ``apps/dashboard/fiscal/tests/test_declaracion_responsable.py`` (the loader,
  the archive, the modality, the text quoting what the JSON declares, the composition).

Not ported, with the reason: the contract against ``producer_facts`` (what the SaaS serves to the
fleet in ``SistemaInformatico``: it does not exist in saas-next yet) and the coverage per Hub version
with ``declaration_reference`` (the heartbeat that tells a hub which declaration covers it: it comes
with the Hub ↔ SaaS fiscal contract). Nor the two checks on v2's architecture (``verifactu-gateway``
in the composition, the certificate no longer distributed): they pin the old fleet, not the archive.
"""

import dataclasses
import hashlib
import json
import re
import shutil

import pytest
from django.urls import resolve, reverse

from public import declaracion
from public.declaracion import (
    DECLARATIONS_DIR,
    MODALITY_SOLO_VERIFACTU,
    Declaration,
    current_declaration,
    declarations,
    latest_signed_declaration,
    render_declaration,
)

pytestmark = [pytest.mark.django_db]

URL = "/legal/declaracion-responsable/"

#: Status markers of the template. Asserted on THESE and not on the sentence: the text goes through
#: i18n and changes language, the guarantee does not.
#: The NOTE that the version in force is not signed yet…
PENDING_MARKER = 'data-note="pending-signature"'
#: …and, apart, how the date-and-place row of the summary is labelled. Two markers on purpose: with
#: one, a test looking for the note was satisfied by the row's label, and the false sentence could
#: come back without anything catching it.
SIGNED_ROW_MARKER = 'data-state="signed"'


def served_bytes(response) -> bytes:
    return (
        b"".join(response.streaming_content) if response.streaming else response.content
    )


@pytest.fixture
def signed_declaration():
    """The newest version that HAS a signed copy — the one handed over at purchase.

    **Not** ``current_declaration()``: the version in force can be published as text while its
    signed copy waits for the signature. Asserted rather than skipped when there is none: an archive
    with nothing signed means there is nothing to deliver (art. 13.2), which is a failure.
    """
    declaration = latest_signed_declaration()
    assert declaration is not None, (
        "no version has a signed copy to deliver (art. 13.2)"
    )
    return declaration


@pytest.fixture
def signed_bytes(signed_declaration):
    return (
        DECLARATIONS_DIR / signed_declaration.version / signed_declaration.signed_pdf
    ).read_bytes()


# --- Routes ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "args", "path"),
    [
        ("public:declaracion_responsable", [], URL),
        ("public:declaracion_responsable_version", ["v1"], f"{URL}v1/"),
        ("public:declaracion_responsable_pdf", ["v1"], f"{URL}v1/pdf/"),
    ],
)
def test_the_declaration_routes(name, args, path):
    assert reverse(name, args=args) == path
    assert resolve(path).view_name == name


def test_the_pages_only_answer_safe_methods(client):
    assert client.post(URL).status_code == 405
    assert client.post(f"{URL}v1/pdf/").status_code == 405


# --- The page (test_declaracion_responsable_page.py) -------------------------------------------


def test_the_page_is_public(client):
    assert client.get(URL).status_code == 200


def test_it_shows_the_identifying_data_the_records_actually_carry(client):
    """Art. 13.4. These are the values in ``SistemaInformatico`` of every record we emit."""
    html = client.get(URL).content.decode()

    for value in current_declaration().facts.values():
        assert value in html, f"the published declaration never states {value!r}"


def test_it_states_the_modality(client):
    assert current_declaration().modality in client.get(URL).content.decode()


def test_the_signed_text_is_rendered_not_just_linked(client):
    """The declaration is the document, not a promise of one."""
    html = client.get(URL).content.decode()

    assert "Declaración responsable" in html
    assert "artículo 29.2.j)" in html
    assert "<h2" in html, "the markdown body is not being rendered"


def test_the_page_has_one_h1_and_the_deed_keeps_its_title(client):
    """L8: the hero is the page's ``<h1>``; the deed's ``# title`` is published, as an ``<h2>``."""
    html = client.get(URL).content.decode()

    assert len(re.findall(r"<h1[\s>]", html)) == 1
    assert re.search(
        r"<h2\b[^>]*>Declaración responsable del sistema informático", html
    )


def test_the_deed_title_keeps_the_size_of_a_page_title(client):
    """L8: as a bare ``<h2>`` the title looked like «1. Declarante»; ``ep-deed-title`` (layout.css)
    gives it back the size it had as the old page's ``<h1>``. Only the title carries it, next to
    the ``id`` of its anchor."""
    html = client.get(URL).content.decode()

    assert re.search(
        r'<h2 class="ep-deed-title"[^>]*>Declaración responsable del sistema informático',
        html,
    )
    assert html.count("ep-deed-title") == 1


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_deed_is_marked_as_spanish_whatever_the_page_language(
    client, settings, language
):
    """The deed is Spanish in every language of the page: a screen reader must read it as such."""
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    html = client.get(URL).content.decode()
    deed = html.index('<div lang="es" class="ep-prose">')

    assert html.index("1. Declarante") > deed
    assert html.index("</div>", html.index("10. Fecha y lugar de la firma")) > deed


def test_every_archived_version_is_reachable(client):
    """Art. 13.3 — all versions are kept, so all versions must be servable."""
    index = client.get(URL).content.decode()

    for declaration in declarations():
        assert declaration.version in index
        assert client.get(f"{URL}{declaration.version}/").status_code == 200


def test_an_unknown_version_is_a_404_not_a_crash(client):
    assert client.get(f"{URL}v999/").status_code == 404
    assert client.get(f"{URL}..%2F..%2Fetc/").status_code == 404


def test_the_chrome_is_translated_even_though_the_deed_is_spanish(client, settings):
    """The declaration is a Spanish legal instrument and stays in Spanish; the page is not.

    Deliberately a string that exists ONLY in the page chrome: "Declaración responsable" also
    appears inside the Spanish deed, so asserting on it would pass with i18n switched off.
    """
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    assert "Archivo de todas las versiones" in client.get(URL).content.decode()


def test_only_the_version_in_force_is_not_marked_superseded(client):
    *older, in_force = declarations()

    for declaration in older:
        html = client.get(f"{URL}{declaration.version}/").content.decode()
        assert "superseded" in html, declaration.version
    assert "superseded" not in client.get(f"{URL}{in_force.version}/").content.decode()


def test_the_page_uses_the_shared_public_reading_pattern():
    from public.tests.test_legal import LEGAL_TEMPLATES

    source = (LEGAL_TEMPLATES / "declaracion_responsable.html").read_text(
        encoding="utf-8"
    )

    assert "{% block page_content %}" in source
    assert "hero_compact=True" in source
    assert 'class="ep-section--compact ep-section--divider"' in source
    assert 'class="ep-container ep-section-content"' in source
    assert 'class="ep-prose max-w-4xl mx-auto"' in source
    assert 'style="' not in source
    assert "<style" not in source


# --- 1. Byte for byte, or the signature is worthless (test_declaracion_responsable_pdf.py) ----


class TestTheSignatureSurvives:
    def test_the_bytes_served_are_the_bytes_signed(
        self, client, signed_declaration, signed_bytes
    ):
        response = client.get(f"{URL}{signed_declaration.version}/pdf/")

        assert response.status_code == 200
        assert (
            hashlib.sha256(served_bytes(response)).hexdigest()
            == hashlib.sha256(signed_bytes).hexdigest()
        )

    def test_what_is_served_still_carries_the_signature(
        self, client, signed_declaration
    ):
        """The check that really matters, made on what goes over the wire."""
        served = served_bytes(client.get(f"{URL}{signed_declaration.version}/pdf/"))

        assert b"/Type/Sig" in served or b"/Type /Sig" in served
        assert b"ETSI.CAdES.detached" in served
        assert b"/ByteRange" in served

    def test_it_is_served_as_a_pdf(self, client, signed_declaration):
        response = client.get(f"{URL}{signed_declaration.version}/pdf/")

        assert response["Content-Type"] == "application/pdf"


# --- 2. Opening and downloading are the same URL with a different intent -----------------------


class TestOpenAndDownload:
    def test_by_default_it_opens_in_the_browser(self, client, signed_declaration):
        """Whoever only wants to read it should not have to download a file."""
        response = client.get(f"{URL}{signed_declaration.version}/pdf/")

        assert response["Content-Disposition"].startswith("inline")

    def test_with_download_it_is_saved(self, client, signed_declaration):
        response = client.get(f"{URL}{signed_declaration.version}/pdf/?download=1")

        assert response["Content-Disposition"].startswith("attachment")

    @pytest.mark.parametrize("value", ["0", "false", "no", ""])
    def test_any_download_other_than_1_opens_it(
        self, client, signed_declaration, value
    ):
        """Only ``?download=1`` saves it: ``?download=0`` asking for a download was a surprise."""
        response = client.get(
            f"{URL}{signed_declaration.version}/pdf/?download={value}"
        )

        assert response["Content-Disposition"].startswith("inline")

    def test_the_filename_says_what_it_is_and_which_version(
        self, client, signed_declaration
    ):
        disposition = client.get(f"{URL}{signed_declaration.version}/pdf/")[
            "Content-Disposition"
        ]

        assert "declaracion-responsable" in disposition
        assert signed_declaration.version in disposition


# --- 3. Only the file the archive declares -----------------------------------------------------


class TestOnlyTheDeclaredFile:
    def test_an_unknown_version_is_a_404(self, client):
        assert client.get(f"{URL}v999/pdf/").status_code == 404

    def test_no_path_can_be_traversed_out_of_the_archive(self, client):
        """The file name comes from the archive's JSON, never from the URL.

        The version does travel in the route, so it is matched against the archive and never
        joined onto a path.
        """
        for attempt in ["..", "..%2F..%2Fetc", "v1%2F..%2F..", "%2Fetc%2Fpasswd"]:
            assert client.get(f"{URL}{attempt}/pdf/").status_code == 404

    def test_a_version_without_a_signed_copy_answers_404_not_a_broken_file(
        self, client, monkeypatch
    ):
        """While a version is unsigned there is no PDF to deliver, and the answer says so."""
        original = current_declaration()
        unsigned = dataclasses.replace(
            original, signed_pdf="", status="pending_signature"
        )
        monkeypatch.setattr(declaracion, "declarations", lambda: [unsigned])

        assert client.get(f"{URL}{original.version}/pdf/").status_code == 404


# --- 4. The page links it, and says how it is checked ------------------------------------------


class TestThePageLinksIt:
    def test_the_page_offers_both_opening_and_downloading(
        self, client, signed_declaration
    ):
        html = client.get(f"{URL}{signed_declaration.version}/").content.decode()

        assert f"{URL}{signed_declaration.version}/pdf/" in html
        assert "download=1" in html

    def test_the_page_says_the_browser_does_not_validate_the_signature(
        self, client, signed_declaration, settings
    ):
        """A PDF viewer shows the document and says nothing about the signature."""
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        html = client.get(f"{URL}{signed_declaration.version}/").content.decode()

        assert "valide.redsara.es" in html

    def test_a_signed_version_says_so_in_its_summary(self, client, signed_declaration):
        html = client.get(f"{URL}{signed_declaration.version}/").content.decode()

        assert SIGNED_ROW_MARKER in html

    def test_a_signed_version_is_not_flagged_as_pending(
        self, client, signed_declaration
    ):
        """The «pending signature» note goes away as soon as the copy exists. Anchored on the
        block's marker and not on its sentence: the string goes through i18n."""
        html = client.get(f"{URL}{signed_declaration.version}/").content.decode()

        assert PENDING_MARKER not in html


# --- 5. When the version in FORCE is published and not signed yet ------------------------------


def _pending_note(html: str) -> str:
    """The note's paragraph, cut out of the rest of the page."""
    start = html.index(PENDING_MARKER)
    return html[start : html.index("</p>", start)]


class TestWhenTheOneInForceIsNotSignedYet:
    """A new declaration is published as text and signed later, not both at once.

    In between, the page has to say exactly that. The note that used to sit on this branch said
    *«the signed copy is delivered to the customer and the reseller at the moment of acquisition»*
    — true while the version in force was signed, and **false** as soon as it has no signed copy.
    """

    @pytest.fixture
    def unsigned_page(self, client, monkeypatch):
        """The page of a version in force WITHOUT signature, whatever the real archive's state.

        The archive is patched rather than relying on v2 staying pending: the day it is signed
        these guarantees must keep running, because the next declaration will go through here.
        """
        archive = declarations()
        pending = dataclasses.replace(
            archive[-1], signed_pdf="", status="pending_signature"
        )
        monkeypatch.setattr(
            declaracion, "declarations", lambda: [*archive[:-1], pending]
        )
        monkeypatch.setattr(declaracion, "current_declaration", lambda: pending)
        return lambda: client.get(URL).content.decode()

    def test_the_page_says_the_signature_is_pending(self, unsigned_page):
        assert PENDING_MARKER in unsigned_page()

    def test_it_never_claims_a_signed_copy_of_it_is_delivered(self, unsigned_page):
        """The concrete false statement to kill, in both languages we serve."""
        html = unsigned_page()

        assert "La copia firmada se entrega" not in html
        assert "The signed copy is delivered" not in html

    def test_no_pdf_is_offered_for_a_version_that_has_none(self, unsigned_page):
        """A link to a download that does not exist is a 404 promised from a legal page."""
        pending = declarations()[-1]

        assert f"{URL}{pending.version}/pdf/" not in unsigned_page()

    def test_the_summary_does_not_present_it_as_already_signed(self, unsigned_page):
        """The date and place exist before the signature (art. 13.4 asks for them and the text
        declares them), but labelling them «Signed» asserts an act that has not happened yet."""
        assert SIGNED_ROW_MARKER not in unsigned_page()

    def test_the_note_is_served_in_spanish(self, client, unsigned_page, settings):
        """English source + its `es`: the Spanish customer reads the page in Spanish."""
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

        assert "Pendiente de firma." in _pending_note(unsigned_page())

    def test_the_note_itself_points_at_the_last_signed_copy(
        self, unsigned_page, signed_declaration
    ):
        """Whoever needs a signed document TODAY must reach it without searching.

        Looked for INSIDE the note, not in the page: the archive list below links the signed
        copies anyway, so an `in html` would accept a note that offered nothing.
        """
        note = _pending_note(unsigned_page())

        assert f"{URL}{signed_declaration.version}/pdf/" in note

    def test_every_archived_version_that_is_signed_is_downloadable(self, client):
        for declaration in declarations():
            if declaration.signed_pdf:
                assert client.get(f"{URL}{declaration.version}/pdf/").status_code == 200


def test_every_unsigned_version_answers_404_for_its_pdf(client):
    for declaration in declarations():
        if not declaration.is_signed:
            assert client.get(f"{URL}{declaration.version}/pdf/").status_code == 404


# --- The archive (test_declaracion_responsable.py, without producer_facts) ---------------------


class TestArchive:
    def test_there_is_at_least_one_declaration(self):
        assert declarations(), "art. 13 requires a declaration; the archive is empty"

    def test_every_version_directory_on_disk_is_parsed(self):
        """A directory that fails to parse must break the build, never be skipped (art. 13.3)."""
        on_disk = {p.name for p in DECLARATIONS_DIR.iterdir() if p.is_dir()}

        assert {d.version for d in declarations()} == on_disk

    def test_versions_come_back_in_order_and_the_current_one_is_the_last(self):
        loaded = declarations()
        keys = [d.sort_key for d in loaded]

        assert keys == sorted(keys)
        assert current_declaration() == loaded[-1]

    def test_a_declaration_carries_the_four_things_art_13_4_asks_for(self):
        for declaration in declarations():
            assert declaration.facts, f"{declaration.version}: no identifying data"
            assert declaration.modality, f"{declaration.version}: no modality"
            assert declaration.signed_on, f"{declaration.version}: no signature date"
            assert declaration.signed_at, f"{declaration.version}: no signature place"
            assert declaration.text.strip(), f"{declaration.version}: no text"

    def test_every_declaration_says_from_which_product_version_it_applies(self):
        for declaration in declarations():
            assert declaration.covers_from, declaration.version

    def test_a_directory_nobody_can_order_breaks_the_archive_loudly(
        self, monkeypatch, tmp_path
    ):
        # A complete version (text and facts) whose only defect is its name.
        shutil.copytree(DECLARATIONS_DIR / "v1", tmp_path / "draft")
        monkeypatch.setattr(declaracion, "DECLARATIONS_DIR", tmp_path)

        with pytest.raises(ValueError, match="not a declaration version"):
            declarations()

    def test_a_version_without_its_facts_breaks_the_archive_loudly(
        self, monkeypatch, tmp_path
    ):
        (tmp_path / "v1").mkdir()
        monkeypatch.setattr(declaracion, "DECLARATIONS_DIR", tmp_path)

        with pytest.raises(FileNotFoundError):
            declarations()


class TestModality:
    def test_no_version_has_ever_declared_anything_but_solo_verifactu(self):
        """Declaring DUAL would make the *registro de eventos* mandatory (developer FAQ §15)."""
        assert {d.modality for d in declarations()} == {MODALITY_SOLO_VERIFACTU}

    def test_solo_verifactu_comes_with_the_flag_every_record_carries(self):
        for declaration in declarations():
            assert declaration.facts["TipoUsoPosibleSoloVerifactu"] == "S"

    def test_id_sistema_informatico_fits_the_xsd(self):
        """``TextMax2Type``: a longer value is AEAT error 1100 on every record of every hub."""
        assert len(current_declaration().facts["IdSistemaInformatico"]) <= 2


class TestTextAndFactsAgree:
    def test_the_signed_text_quotes_every_value_it_declares(self):
        """The PDF is what gets signed; the JSON is what gets tested. Testing only the JSON would
        leave the signed paper free to name a different product."""
        for declaration in declarations():
            for field, value in declaration.facts.items():
                assert value in declaration.text, (
                    f"{declaration.version}: the text never states {field} = {value!r}"
                )

    def test_the_text_states_the_modality_and_the_signature(self):
        for declaration in declarations():
            assert declaration.modality in declaration.text
            assert declaration.signed_at in declaration.text
            assert declaration.signed_on.isoformat() in declaration.text

    def test_the_machine_block_is_plain_json_with_no_surprises(self):
        for version_dir in sorted(p for p in DECLARATIONS_DIR.iterdir() if p.is_dir()):
            raw = json.loads(
                (version_dir / "declared-facts.json").read_text(encoding="utf-8")
            )

            assert raw["version"] == version_dir.name
            assert isinstance(raw["facts"], dict)
            assert all(isinstance(v, str) for v in raw["facts"].values())


class TestComposition:
    def test_every_declaration_lists_the_components_of_the_system(self):
        for declaration in declarations():
            assert declaration.composition, declaration.version
            assert all(
                isinstance(c, str) and c.strip() for c in declaration.composition
            )

    def test_the_signed_text_names_every_component_it_lists(self):
        for declaration in declarations():
            for component in declaration.composition:
                assert component in declaration.text, (
                    f"{declaration.version}: the text never names {component!r}"
                )


class TestLoader:
    def test_versions_sort_numerically_not_lexicographically(self):
        """``v10`` comes after ``v9``: a string sort would hand out the wrong current one."""
        assert Declaration.version_sort_key("v10") > Declaration.version_sort_key("v9")

    def test_a_version_that_is_not_a_version_is_rejected_loudly(self):
        with pytest.raises(ValueError):
            Declaration.version_sort_key("draft")

    def test_a_signed_copy_is_only_resolved_inside_its_own_version(self):
        """The PDF's name comes from the JSON, and is resolved INSIDE the version's directory."""
        signed = latest_signed_declaration()
        escaping = dataclasses.replace(
            signed, signed_pdf="../v2/declaracion-responsable.md"
        )
        missing = dataclasses.replace(signed, signed_pdf="not-there.pdf")

        assert signed.signed_pdf_path() is not None
        assert escaping.signed_pdf_path() is None
        assert missing.signed_pdf_path() is None

    def test_signed_needs_both_the_status_and_the_file(self):
        signed = latest_signed_declaration()

        assert signed.is_signed
        assert not dataclasses.replace(signed, status="pending_signature").is_signed
        assert not dataclasses.replace(signed, signed_pdf="").is_signed


class TestRendering:
    def test_the_identifying_data_render_as_a_table(self):
        assert "<table>" in render_declaration(current_declaration())

    def test_the_text_cannot_inject_markup(self):
        """Our own file, but "it is our own file" is the assumption that ages badly."""
        tampered = dataclasses.replace(
            current_declaration(),
            text=(
                "## Title\n\n<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n"
                '<p onclick="x">hi</p>'
            ),
        )

        html = render_declaration(tampered)

        assert "<script" not in html
        assert "javascript:" not in html
        assert not re.search(r"<[^>]*\sonclick=", html)
