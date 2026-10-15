"""The spelling of a tax id, and the shape of a Spanish one (saas#1725).

Ported from ERPlora/saas ``apps/dashboard/fiscal/nif.py`` (origin/develop).

``normalise_nif`` is the single spelling of every tax id billing reads, VAT numbers included
(``billing.vies.normalise``): ``b-12.345.678`` and ``B12345678`` are the same taxpayer, and dots, dashes
and spaces are typography, not identity (saas#1740).

``is_spanish_tax_id`` says whether a tax id has the shape the AEAT gives (the taxpayer of an Anexo I, plan
2026-10-15): a shape again, never the control digit.

``is_legal_person_nif`` answers the two questions of the Anexo I of the AEAT's collaboration agreement 017
(a natural person or «La Entidad … y en su nombre D/Dña …», and whether a proof of representation is
needed). ⚠️ A **shape** check, not a validity check: it reads the first character and nothing else, never
the control digit (the AEAT validates NIFs; refusing one it accepts would be ours). The Hub implements
the same function under the same name, and the two must agree letter for letter.
"""

import re

#: First letters the AEAT gives legal persons and entities without legal personality (Orden EHA/451/2008
#: art. 3). Everything else — a digit (DNI), X/Y/Z (NIE) and the residual K/L/M — is a natural person.
LEGAL_PERSON_LETTERS = frozenset("ABCDEFGHJNPQRSUVW")


def normalise_nif(value: str | None) -> str:
    """Canonical spelling of a tax id: upper case, ASCII letters and digits only (no ``º`` nor other
    script's digits, which ``str.isalnum`` would keep)."""
    return "".join(char for char in (value or "") if char.isascii() and char.isalnum()).upper()


def is_legal_person_nif(value: str | None) -> bool:
    """Is this NIF a company or entity (as opposed to a natural person)? An empty NIF is not: unknown is
    not «company»."""
    nif = normalise_nif(value)
    return bool(nif) and nif[0] in LEGAL_PERSON_LETTERS


#: The nine characters of a Spanish tax id: a DNI (eight digits and a letter), a NIE (X/Y/Z), a residual natural
#: person (K/L/M; seven digits and a letter) or an entity (its letter, seven digits and a digit or A-J).
_SPANISH_TAX_ID = re.compile(r"^(?:[0-9]{8}[A-Z]|[XYZKLM][0-9]{7}[A-Z]|[ABCDEFGHJNPQRSUVW][0-9]{7}[0-9A-J])$")


def is_spanish_tax_id(value: str | None) -> bool:
    """Has this tax id (normalised) the shape the AEAT gives? Never its control digit."""
    return bool(_SPANISH_TAX_ID.match(normalise_nif(value)))
