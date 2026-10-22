"""The Anexo I model the business downloads (FISCAL-F06): the AEAT's official page, untouched, with its blanks
filled in (the business's, when the Hub sends them, and ERPlora's as representative), ERPlora's stamp and
signature in the representative's box, and a page of ERPlora's own with the data protection information
(art. 13 RGPD) the model's «TRATAMIENTO DE DATOS» asks the social collaborator for.

Cases from ERPlora/saas ``apps/dashboard/fiscal/tests/test_anexo_model.py`` (origin/develop): exactly one of the
two opening blocks is filled, chosen by the shape of the taxpayer's tax ID; an empty field keeps the model's dotted
line; ERPlora fills both slots of the granting sentence; the RGPD page says it is not part of the model. Every party
here is synthetic: no real data of ERPlora, and the stamp is an image drawn by the test.
"""

import hashlib
import io

import pytest
from PIL import Image
from pypdf import PdfReader

from fiscal import anexo

ACME = anexo.Representative(
    name="ACME FISCAL SL", tax_id="B00000000", address="Calle Falsa 1, 28000 Madrid"
)
PERSON = anexo.Party(
    name="Manuela Prueba", tax_id="12345678Z", municipality="Getafe", street="Calle Mayor", number="7"
)
COMPANY = anexo.Party(
    name="Bar Prueba SL", tax_id="B12345674", municipality="Leganés", street="Avenida Sur", number="12"
)


def stamp_png(width=300, height=120) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for x in range(10, width - 10):
        for y in range(height // 2 - 3, height // 2 + 3):
            image.putpixel((x, y), (20, 40, 160, 255))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def pages(pdf: bytes):
    return PdfReader(io.BytesIO(pdf)).pages


def texts_at(page, baseline: float) -> str:
    """Every piece of text the page draws on ``baseline`` (± 1 pt), in drawing order."""
    found = []

    def visit(text, cm, tm, font, size):
        if text.strip() and abs(tm[5] - baseline) <= 1:
            found.append(text)

    page.extract_text(visitor_text=visit)
    return " ".join(found)


def sizes_of(page, value: str) -> list[float]:
    found = []

    def visit(text, cm, tm, font, size):
        if value in text:
            found.append(size * tm[0] if tm[0] else size)

    page.extract_text(visitor_text=visit)
    return found


def test_the_official_page_is_kept_whole_and_a_data_protection_page_follows():
    model, privacy = pages(anexo.render(taxpayer=None, representative=ACME, stamp=None))

    official = model.extract_text()
    assert "OTORGA SU REPRESENTACIÓN a" in official
    assert "ACEPTACIÓN DE LA REPRESENTACIÓN" in official
    assert "El texto de este documento normalizado no podrá ser modificado" in official
    text = privacy.extract_text()
    assert "Información básica sobre protección de datos (art. 13 RGPD)" in text
    assert "No forma parte del modelo normalizado" in text


def test_erplora_fills_both_slots_of_the_granting_sentence_and_its_tax_id():
    (model, _privacy) = pages(anexo.render(taxpayer=None, representative=ACME, stamp=None))

    assert "ACME FISCAL SL" in texts_at(model, anexo.SLOTS["representative_name"].baseline)
    assert "B00000000" in texts_at(model, anexo.SLOTS["representative_tax_id"].baseline)
    assert "ACME FISCAL SL" in texts_at(model, anexo.SLOTS["agreement_party"].baseline)


def test_a_person_fills_the_first_opening_block_and_leaves_the_company_one_dotted():
    (model, _privacy) = pages(anexo.render(taxpayer=PERSON, representative=ACME, stamp=None))

    first = texts_at(model, anexo.SLOTS["person_name"].baseline)
    assert "Manuela Prueba" in first and "12345678Z" in first
    address = texts_at(model, anexo.SLOTS["person_municipality"].baseline)
    assert all(part in address for part in ("Getafe", "Calle Mayor", "7"))
    assert "Manuela Prueba" not in texts_at(model, anexo.SLOTS["company_name"].baseline)


def test_a_company_fills_the_second_opening_block_and_leaves_the_person_one_dotted():
    (model, _privacy) = pages(anexo.render(taxpayer=COMPANY, representative=ACME, stamp=None))

    second = texts_at(model, anexo.SLOTS["company_name"].baseline)
    assert "Bar Prueba SL" in second and "B12345674" in second
    address = texts_at(model, anexo.SLOTS["company_municipality"].baseline)
    assert all(part in address for part in ("Leganés", "Avenida Sur", "12"))
    assert "Bar Prueba SL" not in texts_at(model, anexo.SLOTS["person_name"].baseline)


def test_without_a_taxpayer_nor_a_representative_only_the_official_text_is_drawn():
    blank = pages(anexo.render(taxpayer=None, representative=None, stamp=None))[0]
    official = PdfReader(str(anexo.OFFICIAL_MODEL)).pages[0]

    for slot in anexo.SLOTS.values():
        assert texts_at(blank, slot.baseline) == texts_at(official, slot.baseline)


def test_the_stamp_goes_on_the_model_and_only_with_one():
    with_stamp = pages(anexo.render(taxpayer=None, representative=ACME, stamp=stamp_png()))[0]
    without = pages(anexo.render(taxpayer=None, representative=ACME, stamp=None))[0]

    assert len(with_stamp.images) == 1
    assert len(without.images) == 0


@pytest.mark.parametrize(("width", "height"), [(300, 120), (120, 300), (2000, 40)])
def test_the_stamp_fits_the_representatives_box_keeping_its_shape(width, height):
    box = anexo.STAMP_BOX
    x, y, w, h = anexo.stamp_rect(width, height)

    assert box.x0 <= x and x + w <= box.x1 + 0.01
    assert box.y0 <= y and y + h <= box.y1 + 0.01
    assert w / h == pytest.approx(width / height)
    assert w == pytest.approx(box.x1 - box.x0) or h == pytest.approx(box.y1 - box.y0)


def test_the_stamp_box_sits_under_the_representatives_label_and_above_the_footnotes():
    official = PdfReader(str(anexo.OFFICIAL_MODEL)).pages[0]

    assert "REPRESENTANTE" in texts_at(official, 117.2)
    assert anexo.STAMP_BOX.y1 < 127.6  # the place-and-date line's dots
    assert anexo.STAMP_BOX.y0 > 84.2 + 4  # the first footnote's cap height


def test_the_data_protection_page_names_the_controller():
    (_model, privacy) = pages(anexo.render(taxpayer=None, representative=ACME, stamp=None))

    text = " ".join(privacy.extract_text().split())
    assert "Responsable: ACME FISCAL SL, N.I.F. B00000000, con domicilio en Calle Falsa 1, 28000 Madrid." in text
    assert anexo.PRIVACY_EMAIL in text
    assert "Agencia Española de Protección de Datos" in text


def test_a_long_name_is_written_whole_in_a_smaller_size():
    long_name = "Asociación Cultural y Deportiva de Hostelería del Barrio de la Estación SL"
    party = anexo.Party(name=long_name, tax_id="B12345674")

    (model, _privacy) = pages(anexo.render(taxpayer=party, representative=None, stamp=None))

    assert long_name in " ".join(texts_at(model, anexo.SLOTS["company_name"].baseline).split())
    (size,) = sizes_of(model, "Asociación Cultural")
    assert size < anexo.FONT_SIZE


def test_every_slot_is_inside_the_page_and_left_of_its_end():
    for name, slot in anexo.SLOTS.items():
        assert 56 < slot.x0 < slot.x1 < 540, name


@pytest.mark.parametrize(("text", "writable"), [("Peñíscola, nº 3", True), ("名前", False), ("🙂", False)])
def test_only_what_the_model_font_can_write_is_writable(text, writable):
    assert anexo.writable(text) is writable


def test_the_official_pdf_is_the_one_the_slots_were_measured_on():
    """The slots are measured on this file (``pdftotext -bbox``): another file needs them measured again."""
    assert hashlib.sha256(anexo.OFFICIAL_MODEL.read_bytes()).hexdigest() == anexo.OFFICIAL_SHA256
