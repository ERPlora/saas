"""The Anexo I model the business downloads, signs and uploads (FISCAL-F06; PLAN-SAAS §4: «el PDF oficial
pre-rellenado (Anexo I, p. 11, + hoja RGPD)»).

Page 1 is the AEAT's official page (p. 11 of agreement 017, ``OFFICIAL_MODEL``), whose text is never touched: «El
texto de este documento normalizado no podrá ser modificado». What is drawn on it is what a person would write in
its blanks: the taxpayer (the business, when the Hub sends its details) in exactly one of the two opening blocks,
chosen by the shape of its tax ID; ERPlora, the representative, in both slots of the granting sentence and its tax
ID; and ERPlora's stamp and signature in the representative's box. A blank with nothing to write keeps its dotted
line, so a printed copy is still completed by hand. Page 2 is ERPlora's own: the data protection information (art.
13 RGPD) that the model's «TRATAMIENTO DE DATOS» obliges the social collaborator to give, which says on its face that
it is not part of the model.

Ported in behaviour from ERPlora/saas ``apps/dashboard/fiscal/services/anexo_model.py`` and ``anexo_i_text.py``
(origin/develop), which printed an HTML copy of the model with WeasyPrint; here the official PDF itself is filled,
so its wording can never drift. The texts of page 2 are the old product's, and they stay in Spanish: this is a
document filed with the Spanish tax agency, not ERPlora's UI.

The slots were measured on ``OFFICIAL_MODEL`` (``pdftotext -bbox``; ``OFFICIAL_SHA256`` pins the file): a value
covers its dotted line with white and is written in Times-Roman (the metrics of the model's Times New Roman), at
``FONT_SIZE`` or smaller to fit whole. Only what Times-Roman can write (``writable``: Windows-1252) is written.
"""

import io
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from billing.nif import is_legal_person_nif

#: The AEAT's official model, p. 11 of agreement 017 (copied from ``knowledge/company/aeat-agreement-017``).
OFFICIAL_MODEL = Path(__file__).resolve().parent / "static" / "fiscal" / "representation-model.pdf"
#: The file the slots were measured on.
OFFICIAL_SHA256 = "f91bedb37871493e1289550d009e7b4d8dd61fe1918f3637f5f7ffc87b024455"
FONT = "Times-Roman"
FONT_BOLD = "Times-Bold"
#: The size a value is written at, if it fits its blank; smaller if not.
FONT_SIZE = 10.0
#: The data protection contact of ERPlora, as its privacy policy names it (``public/legal/privacy.html``).
PRIVACY_EMAIL = "privacy@erplora.com"


@dataclass(frozen=True)
class Party:
    """The taxpayer who grants the representation: the business, as the Hub knows it."""

    name: str = ""
    tax_id: str = ""
    municipality: str = ""
    street: str = ""
    number: str = ""


@dataclass(frozen=True)
class Representative:
    """ERPlora, who receives the representation and answers for the data (``billing.CompanyConfig``)."""

    name: str
    tax_id: str
    address: str


@dataclass(frozen=True)
class Slot:
    """A blank of the official page: from ``x0`` to ``x1`` on the line whose baseline is ``baseline``."""

    x0: float
    x1: float
    baseline: float


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float


SLOTS: dict[str, Slot] = {
    # «D/Dña … N.I.F. …, con domicilio fiscal en (municipio) … (vía pública) … nº …»: a natural person.
    "person_name": Slot(88.8, 438.2, 678.6),
    "person_tax_id": Slot(469.6, 535.5, 678.6),
    "person_municipality": Slot(214.6, 302.6, 665.9),
    "person_street": Slot(364.0, 504.5, 665.9),
    "person_number": Slot(518.8, 538.0, 665.9),
    # «La Entidad (razón social) … N.I.F. …, con domicilio fiscal en …»: a legal person.
    "company_name": Slot(171.0, 437.7, 640.5),
    "company_tax_id": Slot(469.2, 535.2, 640.5),
    "company_municipality": Slot(214.6, 299.9, 627.9),
    "company_street": Slot(359.5, 501.8, 627.9),
    "company_number": Slot(516.2, 538.2, 627.9),
    # «OTORGA SU REPRESENTACIÓN a … N.I.F. …, como firmante o adherido al Acuerdo de colaboración entre la Agencia
    # Estatal de Administración Tributaria y …»: both name the representative.
    "representative_name": Slot(228.8, 537.1, 564.7),
    "representative_tax_id": Slot(87.7, 143.0, 552.0),
    "agreement_party": Slot(183.8, 535.0, 539.4),
}
#: Where ERPlora's stamp and signature go: beside «REPRESENTANTE (2)», between the place-and-date line and the
#: footnotes.
STAMP_BOX = Box(412.0, 90.0, 538.0, 126.0)

PRIVACY_HEADING = "Información básica sobre protección de datos (art. 13 RGPD)"
PRIVACY_PARAGRAPHS = (
    "Esta página la añade ERPlora para cumplir el artículo 13 del RGPD, tal y como exige el apartado TRATAMIENTO DE "
    "DATOS del modelo. No forma parte del modelo normalizado y no modifica su texto.",
    "Responsable: {name}, N.I.F. {tax_id}, con domicilio en {address}. Contacto en materia de protección de datos: "
    "{email}.",
    "Finalidad: remitir en su nombre, por medios telemáticos, los ficheros con los registros de facturación que "
    "genera su sistema de emisión de facturas a la Sede electrónica de la Agencia Estatal de Administración "
    "Tributaria, y custodiar el presente otorgamiento como prueba de que estaba autorizado a hacerlo.",
    "Base jurídica: el otorgamiento de representación que usted firma en este documento (artículo 6.1.b del RGPD, "
    "ejecución del contrato de suministro de software), y el cumplimiento de las obligaciones legales que "
    "corresponden a ERPlora como colaborador social (artículo 6.1.c del RGPD).",
    "Destinatarios: la Agencia Estatal de Administración Tributaria. No se ceden datos a otros terceros ni se "
    "realizan transferencias internacionales.",
    "Conservación: mientras la representación esté vigente y, después, durante los plazos de prescripción "
    "tributaria que obligan a ERPlora a poder acreditarla ante la Administración.",
    "Derechos: puede ejercer los derechos de acceso, rectificación, supresión, limitación, portabilidad y oposición "
    "escribiendo a {email}, y presentar una reclamación ante la Agencia Española de Protección de Datos "
    "(www.aepd.es).",
    "Revocación: puede retirar esta representación en cualquier momento escribiendo a {email}; desde entonces "
    "ERPlora deja de remitir en su nombre. La retirada no afecta a los envíos ya realizados.",
)
#: What a party ERPlora does not know reads as: the model's own dotted line.
DOTS = "." * 30


def writable(text: str) -> bool:
    """Whether the model's font can write ``text`` (Times-Roman: Windows-1252, which has every Spanish letter)."""
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def stamp_rect(width: int, height: int) -> tuple[float, float, float, float]:
    """``(x, y, w, h)`` of an image of ``width`` × ``height`` pixels as big as ``STAMP_BOX`` lets it, keeping its
    shape, centred in it."""
    box_width, box_height = STAMP_BOX.x1 - STAMP_BOX.x0, STAMP_BOX.y1 - STAMP_BOX.y0
    scale = min(box_width / width, box_height / height)
    w, h = width * scale, height * scale
    return (
        STAMP_BOX.x0 + (box_width - w) / 2,
        STAMP_BOX.y0 + (box_height - h) / 2,
        w,
        h,
    )


def render(*, taxpayer: Party | None, representative: Representative | None, stamp: bytes | None) -> bytes:
    """The model to sign: the official page with what is known written in its blanks, and the RGPD page.

    ``stamp`` is a PNG (``fiscal.services`` checks it on upload). Raises ``ValueError`` for a text the font
    cannot write (``writable``), never writing it half."""
    width, height = (float(side) for side in PdfReader(OFFICIAL_MODEL).pages[0].mediabox[2:])
    layers = io.BytesIO()
    canvas = Canvas(layers, pagesize=(width, height))
    for slot, value in _values(taxpayer, representative).items():
        _write(canvas, SLOTS[slot], value)
    if stamp:
        image = ImageReader(io.BytesIO(stamp))
        x, y, w, h = stamp_rect(*image.getSize())
        canvas.drawImage(image, x, y, w, h, mask="auto")
    canvas.showPage()
    _privacy_page(canvas, representative, width, height)
    canvas.showPage()
    canvas.save()

    drawn = PdfReader(io.BytesIO(layers.getvalue())).pages
    writer = PdfWriter(clone_from=OFFICIAL_MODEL)
    writer.pages[0].merge_page(drawn[0])
    writer.add_page(drawn[1])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _values(taxpayer: Party | None, representative: Representative | None) -> dict[str, str]:
    values = {}
    if taxpayer is not None:
        block = "company" if is_legal_person_nif(taxpayer.tax_id) else "person"
        for field in ("name", "tax_id", "municipality", "street", "number"):
            values[f"{block}_{field}"] = getattr(taxpayer, field)
    if representative is not None:
        values["representative_name"] = representative.name
        values["representative_tax_id"] = representative.tax_id
        values["agreement_party"] = representative.name
    return {slot: value.strip() for slot, value in values.items() if value and value.strip()}


def _write(canvas: Canvas, slot: Slot, value: str) -> None:
    """``value`` over the dotted line of ``slot``, whole: at ``FONT_SIZE`` or as small as it takes to fit."""
    if not writable(value):
        raise ValueError("The model's font cannot write this value.")
    room = slot.x1 - slot.x0 - 2
    size = min(FONT_SIZE, room / stringWidth(value, FONT, 1))
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(slot.x0, slot.baseline - 2.5, slot.x1 - slot.x0, 11, stroke=0, fill=1)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(FONT, size)
    canvas.drawString(slot.x0 + 1, slot.baseline, value)


def _privacy_page(canvas: Canvas, representative: Representative | None, width: float, height: float) -> None:
    margin = 56.7
    room = width - 2 * margin
    y = height - margin - 12
    canvas.setFont(FONT_BOLD, 12)
    canvas.drawString(margin, y, PRIVACY_HEADING)
    y -= 24
    party = {
        "name": representative.name if representative else DOTS,
        "tax_id": representative.tax_id if representative else DOTS,
        "address": representative.address if representative else DOTS,
        "email": PRIVACY_EMAIL,
    }
    canvas.setFont(FONT, 11)
    for paragraph in PRIVACY_PARAGRAPHS:
        for line in simpleSplit(paragraph.format(**party), FONT, 11, room):
            canvas.drawString(margin, y, line)
            y -= 14
        y -= 8
