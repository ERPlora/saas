"""Input and output schemas of the catalog's reads (spec §5.1; OpenAPI and the SPA's typed client).

Every filter is optional and lenient: a ``category`` or a ``premium`` that is not understood is
ignored (spec §5.1), so an old or mistyped link of the store still lists apps instead of a 422.
"""

from datetime import datetime
from typing import Any, Literal

from live.meta import Category
from ninja import Schema
from pydantic import field_validator

#: Longest search the store sends: a name and a summary are at most 80 and 120 characters.
SEARCH_MAX_LENGTH = 120
#: Longest vertical id: an app label (spec §3.1).
VERTICAL_MAX_LENGTH = 63
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


#: The C0 control characters (below the space): never part of a search or a vertical id, and a NUL
#: among them is refused by psycopg (``DataError``), a 500 on a public door (``?q=%00``).
_CONTROL_CHARACTERS = dict.fromkeys(range(0x20))


def _trimmed(value: Any, max_length: int) -> str | None:
    """``value`` without control characters, stripped and cut to ``max_length``; ``None`` if empty."""
    if value is None:
        return None
    text = str(value).translate(_CONTROL_CHARACTERS).strip()[:max_length]
    return text or None


# Inputs


class AppListIn(Schema):
    q: str | None = None
    category: Category | None = None
    premium: bool | None = None
    vertical: str | None = None

    @field_validator("q", mode="before")
    @classmethod
    def _search(cls, value: Any) -> str | None:
        return _trimmed(value, SEARCH_MAX_LENGTH)

    @field_validator("vertical", mode="before")
    @classmethod
    def _vertical(cls, value: Any) -> str | None:
        return _trimmed(value, VERTICAL_MAX_LENGTH)

    @field_validator("category", mode="before")
    @classmethod
    def _known_category(cls, value: Any) -> str | None:
        return value if value in Category.values else None

    @field_validator("premium", mode="before")
    @classmethod
    def _understood_premium(cls, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower() if value is not None else ""
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        return None


class AppByIdIn(Schema):
    """An app by its id (its label in the Hub); one that is not listed is a 404, never a 422."""

    id: str


class AppSitemapIn(Schema):
    pass


# Outputs


class AppSummaryOut(Schema):
    """A card of the store. ``category`` is ``None`` when this SaaS does not know it yet."""

    id: str
    name: str
    summary: str
    icon_svg: str
    category: str | None
    premium: bool
    verticals: list[str]


class AppListOut(Schema):
    apps: list[AppSummaryOut]


class RequiredAppOut(Schema):
    """An app the app requires: its name, and ``listed`` to know whether its page exists."""

    id: str
    name: str
    listed: bool


class AppOut(AppSummaryOut):
    description: str
    requires: list[RequiredAppOut]
    has_docs: bool


class AppDocOut(Schema):
    """The documentation as safe HTML; ``fallback`` = served in Spanish for want of English."""

    html: str
    lang: Literal["es", "en"]
    fallback: bool


class AppSitemapEntryOut(Schema):
    """A listed app's page for ``/sitemap.xml`` (spec §8.2): ``has_docs`` = its ``docs/`` exists in
    every language; ``updated_at`` = when its Spanish document changed (``None`` without one)."""

    id: str
    has_docs: bool
    updated_at: datetime | None


class AppSitemapOut(Schema):
    apps: list[AppSitemapEntryOut]


class AppDocListIn(Schema):
    pass


class AppDocSourceOut(Schema):
    """A listed app's user documentation in one language, as written (markdown): what the panel's assistant
    indexes."""

    app: str
    #: The app's name in the document's language.
    name: str
    lang: Literal["es", "en"]
    markdown: str


class AppDocListOut(Schema):
    docs: list[AppDocSourceOut]
