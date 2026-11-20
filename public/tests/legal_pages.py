"""What the tests of the legal pages share: their paths, the Spanish page and the pieces of a page they read."""

import re
from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR)
LEGAL_TEMPLATES = ROOT / "public" / "templates" / "public" / "legal"

PAGES = {
    "public:privacy": "/legal/privacy/",
    "public:cookies": "/legal/cookies/",
    "public:legal_notice": "/legal/legal-notice/",
    # It reads Plan (the trial of section 4).
    "public:terms": "/legal/terms/",
}


def spanish(client, path: str) -> str:
    # English is the source language (real i18n via {% trans %}), so the Spanish page has to be
    # asked for with the language cookie.
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
    return client.get(path).content.decode()


def list_items_naming(html: str, name: str) -> list[str]:
    """The ``<li>`` of a page that mention ``name``: one processor per item in section 5."""
    return [
        item for item in re.findall(r"<li>(.*?)</li>", html, re.DOTALL) if name in item
    ]


def section(html: str, number: int) -> str:
    """Section ``number`` of a legal page, up to the next heading."""
    match = re.search(rf"<h2>{number}\. .*?</h2>(.*?)(?=<h2>|</article>)", html, re.S)
    assert match, f"the page has no section {number}"
    return match.group(1)


def paragraphs_of(html: str) -> list[str]:
    return [" ".join(text.split()) for text in re.findall(r"<p>(.*?)</p>", html, re.DOTALL)]
