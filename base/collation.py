"""The alphabetical order of names shown to a person, whatever their language."""

import unicodedata


def collation_key(name: str) -> str:
    """«Österreich» next to «Oman», «Óptica» before «Peluquería»: accents and capitals do not move a name."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
