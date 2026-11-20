"""What the tests of the public web's templates share: where the templates and their stylesheets live, every
template, a template without its comments, a region of a page and a page of the test URLs."""

import re
from pathlib import Path

from django.conf import settings
from django.urls import reverse

ROOT = Path(settings.BASE_DIR)
PUBLIC_TEMPLATES = ROOT / "public" / "templates"
PUBLIC_STATIC = ROOT / "public" / "static" / "public"
COMPONENTS = PUBLIC_TEMPLATES / "public" / "components"
COMPONENT_CSS = PUBLIC_STATIC / "components"


def without_comments(source: str) -> str:
    source = re.sub(r"\{#.*?#\}", "", source, flags=re.DOTALL)
    source = re.sub(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", source, flags=re.DOTALL
    )
    return re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)


def public_templates() -> list[Path]:
    return sorted(PUBLIC_TEMPLATES.rglob("*.html"))


def region(html: str, start: str, end: str) -> str:
    begin = html.index(start)
    return html[begin : html.index(end, begin)]


def get_page(client, name="test_public_page", **headers):
    response = client.get(reverse(name), **headers)
    assert response.status_code == 200
    return response
