"""Every «…» the WORKBOOK quotes from the web is the web's text, letter by letter (hub#152: the lint does not look).

The customer's part of ``public/WORKBOOK.md`` (its flows, up to «## Para quien lo mantiene») quotes buttons, notices
and headings in Spanish. A quote that drifts from the catalog sends QA and the assistant after a text that is not on
screen: the APP-PUBLIC-3 review found «¿Dónde se guardan mis datos?» where the FAQ says «¿Dónde se almacenan mis
datos?» and «Sobre nosotros» where the menu says «Sobre Nosotros». A quote matches a Spanish ``msgstr`` of the SaaS's
catalogs, or a part of one; a placeholder (``%(minutes)s``) stands for any value, so «Termina en 12 minutos.» is
«Termina en %(minutes)s minutos.», and a figure in a part of one stands for its number placeholder («En un plazo de 4
horas laborables» in «…en un plazo de %(hours)d horas laborables.»).
"""

import re
from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR)
WORKBOOK = ROOT / "public" / "WORKBOOK.md"
CATALOGS = sorted(ROOT.glob("*/locale/es/LC_MESSAGES/django.po")) + [ROOT / "locale" / "es" / "LC_MESSAGES" / "django.po"]

#: Quotes that are not a text of this project's catalogs, each with why.
NOT_THE_WEBS = {
    # Examples of what a visitor types, and the address it proposes (PUBLIC-F37).
    "Demo Bar": "a business name typed by a customer",
    "demobar": "the address that name proposes",
    "demo-": "the beginning of a demo's address",
    # The footer names each language in its own language (Django's LANGUAGES), never through the catalog (PUBLIC-F13).
    "English": "a language's own name",
    # What the web must never say (PUBLIC-F08).
    "tus datos nunca salen de la UE": "a promise the web is forbidden to make",
    # The Hub's own pages (its catalog lives in ERPlora/hub): the ended demo's page (PUBLIC-F33).
    "La demo ha terminado": "the Hub's page of an ended demo",
    "Crear otra demo": "the Hub's page of an ended demo",
}

MSGSTR = re.compile(r'^msgstr(?:\[\d+\])? ((?:"(?:[^"\\]|\\.)*"\s*)+)', re.M)
PART = re.compile(r'"((?:[^"\\]|\\.)*)"')
PLACEHOLDER = re.compile(r"%\(\w+\)[sd]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def spanish_texts() -> list[str]:
    texts = []
    for catalog in CATALOGS:
        for match in MSGSTR.finditer(catalog.read_text()):
            text = "".join(PART.findall(match.group(1))).replace('\\"', '"').replace("\\n", "\n")
            if text:
                texts.append(text)
    return texts


def as_pattern(text: str) -> re.Pattern:
    """``text`` with each placeholder standing for any value."""
    pieces = PLACEHOLDER.split(text)
    return re.compile(r".+?".join(re.escape(piece) for piece in pieces))


def figures_blind(text: str) -> str:
    """``text`` with every placeholder and every figure as ``#``."""
    return NUMBER.sub("#", PLACEHOLDER.sub("#", text))


def is_the_webs(quote: str, texts: list[str]) -> bool:
    """A part of a text, a whole text with any value in its placeholders, or a part of one with other figures."""
    return (
        any(quote in text for text in texts)
        or any(as_pattern(text).fullmatch(quote) for text in texts if PLACEHOLDER.search(text))
        or any(figures_blind(quote) in figures_blind(text) for text in texts if PLACEHOLDER.search(text))
    )


def customer_quotes() -> set[str]:
    text = WORKBOOK.read_text()
    flows = text.split("\n## Flujos\n", 1)[1].split("\n## Para quien lo mantiene\n", 1)[0]
    return set(re.findall(r"«([^«»]+)»", flows))


def test_every_quote_of_the_flows_is_a_text_of_the_web():
    texts = spanish_texts()

    unknown = sorted(quote for quote in customer_quotes() - NOT_THE_WEBS.keys() if not is_the_webs(quote, texts))

    assert unknown == []


def test_a_placeholder_stands_for_any_value():
    texts = ["Termina en %(minutes)s minutos.", "Te respondemos en un plazo de %(hours)d horas laborables."]

    assert is_the_webs("Termina en 12 minutos.", texts)
    assert is_the_webs("en un plazo de 4 horas laborables", texts)
    assert not is_the_webs("Termina en 12 horas.", texts)
    assert not is_the_webs("en un plazo de 4 días laborables", texts)


def test_the_exemptions_are_still_quoted():
    """An exemption the WORKBOOK no longer quotes has to leave the list."""
    assert set(NOT_THE_WEBS) <= customer_quotes()
