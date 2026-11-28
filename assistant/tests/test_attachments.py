"""ASSISTANT-F19 · Read what a question attaches: an image goes to the model as it is (a model that
cannot see gets a note instead), and so does a PDF, which the provider reads whole, a scanned one too (a model that
cannot see gets its text instead); any other document (Word, Excel, text, CSV, Markdown, JSON) is turned into its text.

The Hub sends each file inside the message, in base64: erplora.com downloads nothing (no address of a document or an
image is fetched, so there is no door to the internal network) and writes nothing to disk. Each attachment has a
size limit (``MAX_ATTACHMENT_BYTES`` of base64, about 9 MB; over it the turn is refused with 413, never cut) and a
conversation a number of them; their data does not count in the 1 MB of text. What cannot be read becomes a note for
the model, never a failed turn, even with a corrupt PDF, ``.docx`` or ``.xlsx``; the file's name never reaches a
log.
"""

import base64
import io
import logging
import zipfile

import pytest
from django.test import Client

from assistant import attachments
from assistant.tests.conftest import openai_answer
from assistant.tests.doors import door, error_code, frames
from config.tests.asgi_bodies import files_written
from assistant.turn import TurnRefused, prepare

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
COMPLETIONS = "/v1/chat/completions"


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def pdf_with(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    out = io.BytesIO()
    page = canvas.Canvas(out)
    page.drawString(72, 720, text)
    page.save()
    return out.getvalue()


def blank_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    out = io.BytesIO()
    page = canvas.Canvas(out)
    page.showPage()
    page.save()
    return out.getvalue()


def scanned_pdf() -> bytes:
    """A delivery note as a scanner or a phone makes it: one page that is only a picture, with no text in it."""
    from PIL import Image, ImageDraw

    page = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(page)
    for row, line in enumerate(["ALBARAN 0042", "Harina 25 kg x 4", "Aceite 5 L x 2", "Total 128,40"]):
        draw.text((20, 20 + 40 * row), line, fill="black")
    out = io.BytesIO()
    page.save(out, "PDF")
    return out.getvalue()


def docx_with(*paragraphs: str) -> bytes:
    from docx import Document

    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def xlsx_with(sheets: dict) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        sheet = book.create_sheet(title)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def document(data: bytes, mime: str, name: str) -> dict:
    return {"type": "input_file", "filename": name, "mime_type": mime, "data": b64(data)}


def asking(*parts) -> list[dict]:
    return [{"role": "user", "content": [{"type": "text", "text": "Read this"}, *parts]}]


def expanded_parts(*parts) -> list[dict]:
    return prepare(asking(*parts), "")[1]["content"]


def seen_parts(*parts, vision: bool) -> list[dict]:
    """What the model receives of the question, after ``prepare``."""
    return attachments.for_model(prepare(asking(*parts), ""), vision=vision)[1]["content"]


class TestDocumentsBecomeText:
    def test_a_model_that_cannot_see_reads_a_pdfs_text(self):
        part = seen_parts(document(pdf_with("Carta de vinos 2026"), "application/pdf", "carta.pdf"), vision=False)[1]

        assert part["type"] == "text"
        assert part["text"].startswith("[Attachment: carta.pdf]")
        assert "Carta de vinos 2026" in part["text"]

    def test_a_word_document_becomes_its_paragraphs(self):
        data = docx_with("Menú del día", "Lentejas")
        name = "menu.docx"
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        text = expanded_parts(document(data, mime, name))[1]["text"]

        assert "Menú del día\nLentejas" in text

    def test_a_spreadsheet_becomes_a_section_per_sheet_without_empty_rows(self):
        data = xlsx_with({"Stock": [["Producto", "Cantidad"], [None, None], ["Café", 12]], "Precios": [["Café", 1.5]]})
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        text = expanded_parts(document(data, mime, "stock.xlsx"))[1]["text"]

        assert "# Stock\nProducto | Cantidad\nCafé | 12" in text
        assert "# Precios\nCafé | 1.5" in text

    def test_a_spreadsheet_is_read_up_to_the_row_that_passes_the_limit_and_an_empty_sheet_says_nothing(self, monkeypatch):
        monkeypatch.setattr(attachments, "MAX_EXTRACTED_CHARS", 20)
        rows = [["aaaa", None, None], [None, "bb"], ["ccc"], ["dddd"], ["eeee"], ["ffff"]]
        data = xlsx_with({"Empty": [], "A": rows, "B": [["zzzz"]]})

        text = attachments.extract(data, attachments.SHEET, "stock.xlsx")

        assert text == "# A\naaaa\n | bb\nccc\ndddd\neeee"

    def test_the_next_sheet_is_read_with_what_the_earlier_ones_left_of_the_limit(self, monkeypatch):
        monkeypatch.setattr(attachments, "MAX_EXTRACTED_CHARS", 12)
        data = xlsx_with({"A": [["aaaa"], ["bbbb"]], "B": [["cccc"], ["dddd"], ["eeee"]], "C": [["ffff"]]})

        text = attachments.extract(data, attachments.SHEET, "stock.xlsx")

        assert text == "# A\naaaa\nbbbb\n\n# B\ncccc"

    @pytest.mark.parametrize(("mime", "name"), [("text/plain", "notas.txt"), ("text/csv", "ventas.csv"), ("", "readme.md"), ("application/json", "datos.json")])
    def test_plain_text_kinds_are_read_as_they_are(self, mime, name):
        text = expanded_parts(document("línea uno\nlínea dos".encode(), mime, name))[1]["text"]

        assert "línea uno\nlínea dos" in text

    def test_a_long_document_is_cut_to_what_the_model_can_read(self):
        text = expanded_parts(document(("x" * (attachments.MAX_EXTRACTED_CHARS + 50)).encode(), "text/plain", "long.txt"))[1]["text"]

        assert text.endswith("[…cut…]")
        assert len(text) < attachments.MAX_EXTRACTED_CHARS + 100

    def test_a_model_that_cannot_see_is_told_a_scanned_pdf_has_no_text(self):
        text = seen_parts(document(blank_pdf(), "application/pdf", "escaneo.pdf"), vision=False)[1]["text"]

        assert "no text" in text and "escaneo.pdf" in text

    def test_a_data_uri_document_is_read_too(self):
        part = {"type": "input_file", "filename": "n.txt", "mime_type": "text/plain", "data": "data:text/plain;base64," + b64(b"hola")}

        assert "hola" in expanded_parts(part)[1]["text"]

    def test_nothing_is_written_to_disk(self):
        pdf, docx, xlsx = pdf_with("pdf"), docx_with("doc"), xlsx_with({"S": [["a"]]})
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        with files_written() as written:
            parts = seen_parts(
                document(pdf, "application/pdf", "a.pdf"),
                document(docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "b.docx"),
                document(xlsx, mime, "c.xlsx"),
                vision=False,
            )

        assert written == []
        assert [("pdf" in parts[1]["text"]), ("doc" in parts[2]["text"]), ("a" in parts[3]["text"])] == [True, True, True]

    def test_the_watch_sees_a_file_written_by_a_library(self):
        """The control catches the positive: building a workbook makes openpyxl write a temporary file."""
        with files_written() as written:
            xlsx_with({"S": [["a"]]})

        assert written


class TestAPdfGoesWholeToAModelThatSees:
    @pytest.mark.parametrize(("mime", "name"), [("application/pdf", "albaran.pdf"), ("", "albaran.PDF")])
    def test_a_scanned_pdf_goes_whole_to_a_model_that_sees_images(self, mime, name):
        scan = scanned_pdf()

        part = seen_parts(document(scan, mime, name), vision=True)[1]

        assert part == {"type": "file", "file": {"filename": name, "file_data": f"data:application/pdf;base64,{b64(scan)}"}}

    def test_a_pdf_with_text_goes_whole_too(self):
        data = pdf_with("Carta de vinos 2026")

        part = seen_parts(document(data, "application/pdf", "carta.pdf"), vision=True)[1]

        assert part["file"]["file_data"] == f"data:application/pdf;base64,{b64(data)}"

    def test_a_pdf_sent_as_a_data_address_carries_its_data_once(self):
        scan = scanned_pdf()
        part = {"type": "input_file", "filename": "a.pdf", "mime_type": "application/pdf", "data": f"data:application/pdf;base64,{b64(scan)}"}

        assert seen_parts(part, vision=True)[1]["file"]["file_data"] == f"data:application/pdf;base64,{b64(scan)}"

    def test_a_broken_pdf_is_a_note_even_for_a_model_that_sees(self):
        part = seen_parts(document(b"%PDF-1.4 broken", "application/pdf", "rota.pdf"), vision=True)[1]

        assert part["type"] == "text"
        assert part["text"].startswith("[Attachment rota.pdf: could not be read")

    def test_any_other_document_is_still_its_text_for_a_model_that_sees(self):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        part = seen_parts(document(docx_with("Menú del día"), mime, "menu.docx"), vision=True)[1]

        assert part["type"] == "text"
        assert "Menú del día" in part["text"]


class TestWhatCannotBeReadIsANote:
    @pytest.mark.parametrize(
        ("data", "mime", "name"),
        [
            (b"%PDF-1.4 broken", "application/pdf", "rota.pdf"),
            (b"PK\x03\x04 not a zip", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "rota.docx"),
            (b"PK\x03\x04 not a zip", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "rota.xlsx"),
        ],
    )
    def test_a_corrupt_document_is_a_note_not_a_failed_turn(self, data, mime, name):
        text = expanded_parts(document(data, mime, name))[1]["text"]

        assert text.startswith(f"[Attachment {name}: could not be read")

    def test_an_old_word_document_is_a_note(self):
        text = expanded_parts(document(b"\xd0\xcf\x11\xe0", "application/msword", "viejo.doc"))[1]["text"]

        assert "could not be read" in text

    def test_broken_base64_is_a_note(self):
        part = {"type": "input_file", "filename": "x.txt", "mime_type": "text/plain", "data": "@@not base64@@"}

        assert "could not be read" in expanded_parts(part)[1]["text"]

    def test_a_document_by_address_is_not_downloaded(self, fake_provider):
        part = {"type": "input_file", "filename": "x.pdf", "file_url": f"{fake_provider.url}/x.pdf"}

        assert "could not be read" in expanded_parts(part)[1]["text"]
        assert fake_provider.requests == []

    def test_a_zip_bomb_is_a_note(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/document.xml", b"0" * (attachments.MAX_UNZIPPED_BYTES + 1))
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        assert "unfolds into too much" in expanded_parts(document(out.getvalue(), mime, "bomb.docx"))[1]["text"]

    def test_the_name_of_an_unreadable_file_never_reaches_the_log(self, caplog):
        caplog.set_level(logging.DEBUG)

        expanded_parts(document(b"%PDF broken", "application/pdf", "Nómina de Rosalía.pdf"))
        expanded_parts(document(b"???", "", "Contrato Rosalía.doc"))

        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert "Rosalía" not in logged


class TestImages:
    def image(self, url: str) -> dict:
        return {"type": "image_url", "image_url": {"url": url}}

    def test_an_image_goes_to_a_model_that_sees_as_it_is(self):
        part = self.image(f"data:image/png;base64,{PNG}")

        assert attachments.for_model(asking(part), vision=True)[0]["content"][1] == part

    def test_a_model_that_cannot_see_gets_a_note_instead(self):
        content = attachments.for_model(asking(self.image(f"data:image/png;base64,{PNG}")), vision=False)[0]["content"]

        assert content[1]["type"] == "text"
        assert "cannot see images" in content[1]["text"]

    @pytest.mark.parametrize("url", ["https://example.com/a.png", "http://169.254.169.254/latest", "data:text/html;base64,PGI+"])
    def test_an_image_by_address_or_not_an_image_is_a_note(self, url):
        content = prepare(asking(self.image(url)), "")[1]["content"]

        assert content[1]["type"] == "text"
        assert "could not be read" in content[1]["text"]


class TestLimits:
    def test_an_attachment_over_its_limit_refuses_the_turn(self):
        big = "A" * (attachments.MAX_ATTACHMENT_BYTES + 4)

        with pytest.raises(TurnRefused) as refused:
            prepare(asking({"type": "input_file", "filename": "big.txt", "mime_type": "text/plain", "data": big}), "")

        assert (refused.value.status, refused.value.code) == (413, "payload_too_large")

    def test_too_many_attachments_refuse_the_turn(self):
        parts = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}] * (attachments.MAX_ATTACHMENTS + 1)

        with pytest.raises(TurnRefused) as refused:
            prepare(asking(*parts), "")

        assert refused.value.status == 413

    def test_attachments_do_not_count_in_the_text(self):
        almost = "A" * 900_000
        parts = [{"type": "input_file", "filename": f"{n}.txt", "mime_type": "text/plain", "data": almost} for n in range(2)]

        prepare(asking(*parts), "")

    def test_the_text_is_still_limited_with_an_attachment(self):
        with pytest.raises(TurnRefused):
            prepare([{"role": "user", "content": [{"type": "text", "text": "x" * 1_000_001}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}]}], "")


@pytest.mark.django_db
class TestInTheTurn:
    def sent_parts(self, business, fake_provider, *parts) -> list[dict]:
        fake_provider.reply("POST", COMPLETIONS, sse=openai_answer("Ok"))

        frames(door(Client(), "/internal/assistant/chat/stream", {"hub": business.slug, "messages": asking(*parts)}))

        [sent] = [seen for seen in fake_provider.requests if seen.path.endswith("/chat/completions")]
        return sent.body["messages"][1]["content"]

    def test_the_model_reads_the_documents_text_and_sees_the_image(self, internal, business, answering, fake_provider):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        parts = self.sent_parts(
            business,
            fake_provider,
            document(docx_with("Factura 42"), mime, "factura.docx"),
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}},
        )

        assert "Factura 42" in parts[1]["text"]
        assert parts[2]["type"] == "image_url"

    def test_a_scanned_delivery_note_reaches_a_model_that_sees_whole(self, internal, business, answering, fake_provider):
        scan = scanned_pdf()

        parts = self.sent_parts(business, fake_provider, document(scan, "application/pdf", "albaran.pdf"))

        assert parts[1] == {"type": "file", "file": {"filename": "albaran.pdf", "file_data": f"data:application/pdf;base64,{b64(scan)}"}}

    def test_a_model_that_cannot_see_reads_the_pdfs_text_instead(self, internal, business, answering, fake_provider):
        answering.supports_vision = False
        answering.save(update_fields=["supports_vision"])

        parts = self.sent_parts(business, fake_provider, document(pdf_with("Factura 42"), "application/pdf", "factura.pdf"))

        assert parts[1]["type"] == "text"
        assert "Factura 42" in parts[1]["text"]

    def test_an_attachment_too_big_is_a_413_before_the_model(self, internal, business, answering, fake_provider):
        big = {"type": "input_file", "filename": "big.txt", "mime_type": "text/plain", "data": "A" * (attachments.MAX_ATTACHMENT_BYTES + 4)}

        response = door(Client(), "/internal/assistant/chat", {"hub": business.slug, "messages": asking(big)})

        assert (response.status_code, error_code(response)) == (413, "payload_too_large")
        assert fake_provider.requests == []
