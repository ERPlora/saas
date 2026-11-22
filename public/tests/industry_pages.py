"""What the tests of ``/industries/`` and ``/industries/<slug>/`` (public/industries.py) share: the host they ask,
the taxonomy rows they create, the detail page they read and the page's own content without its footer.
"""

from __future__ import annotations

from hubs.models import BusinessType, Sector

HOST = "localhost:8001"
INDEX = "/industries/"


def make_sector(code: str = "beauty", **fields) -> Sector:
    defaults = {"name_en": code.replace("_", " ").title(), "is_active": True}
    return Sector.objects.create(code=code, **{**defaults, **fields})


def make_business_type(code: str = "hair_salon", **fields) -> BusinessType:
    defaults = {"name_en": code.replace("_", " ").title(), "is_active": True}
    return BusinessType.objects.create(code=code, **{**defaults, **fields})

def _page(client, slug="hair_salon", **headers):
    response = client.get(f"/industries/{slug}/", HTTP_HOST=HOST, **headers)
    assert response.status_code == 200
    return response


def _main(html: str) -> str:
    """Only the page's own content: the footer links to /industries/ from EVERY page, so asserting
    against the whole document proves nothing."""
    return html[html.index("<main>") : html.index("</main>")]
