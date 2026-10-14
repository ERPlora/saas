"""Reads of apps: the public catalog of the Hub's apps as operations (spec §5.1–§5.3).

The ninja routes (``test_api.py``), the panel's SPA and the views of ``public/`` call the same
operations, so the operation itself decides what is listed, in which language and how a bad row
(an unknown category, an unusable icon) is painted.
"""

import logging
from datetime import UTC, datetime
from unittest import mock

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import translation
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.markdown import render_markdown
from live.operations import get

from apps import queries
from apps.icons import FALLBACK_ICON_SVG
from apps.schemas import AppByIdIn, AppListIn, AppSitemapIn
from apps.tests.factories import CUBE_SVG, make_app, make_doc, source_hash

pytestmark = pytest.mark.django_db

HUB_STATIC = "https://hubs.example.com/static/"


def visitor(language="en"):
    return OperationContext(
        scope=Scope("user", "anonymous"), actor=None, language=language
    )


def listed(language="en", **filters):
    return queries.app_list(visitor(language), AppListIn(**filters)).apps


def ids(rows):
    return [row.id for row in rows]


@pytest.fixture
def catalog():
    """Three listed apps in three categories, a retired one and the demo, which is never sold."""
    return {
        "invoice": make_app(
            "invoice",
            name_en="Invoices",
            name_es="Facturas",
            summary_en="Bill your customers.",
            summary_es="Factura a tus clientes.",
            category="sales",
            verticals=["hair_salon", "restaurant"],
        ),
        "inventory": make_app(
            "inventory",
            name_en="Stock",
            name_es="Almacén",
            summary_en="Count what you have.",
            summary_es="Cuenta lo que tienes.",
            category="catalog",
        ),
        "whatsapp_inbox": make_app(
            "whatsapp_inbox",
            name_en="WhatsApp Inbox",
            name_es="Bandeja de WhatsApp",
            category="organization",
            premium=True,
            verticals=["hair_salon"],
        ),
        "loyalty": make_app(
            "loyalty", category="people", listed=False, verticals=["retail"]
        ),
        "demo": make_app("demo", category="catalog", listed=False),
    }


@pytest.mark.parametrize(
    "name", ["apps.app.list", "apps.app.get", "apps.app.doc", "apps.app.sitemap"]
)
def test_the_catalog_reads_are_open_queries(name):
    """The store is public: anyone reads it, before any account exists."""
    op = get(name)

    assert (op.kind, op.permission) == ("query", None)


# --- apps.app.list -------------------------------------------------------------------------------


def test_the_list_has_only_the_listed_apps_in_the_order_of_the_categories(catalog):
    """Sales, catalog, people, restaurant, organization (live.meta.Category); a retired app and the
    demo (``listed = False``) are never listed."""
    assert ids(listed()) == ["invoice", "inventory", "whatsapp_inbox"]


def test_each_entry_carries_what_a_card_paints(catalog):
    (invoice,) = [row for row in listed() if row.id == "invoice"]

    assert invoice.model_dump() == {
        "id": "invoice",
        "name": "Invoices",
        "summary": "Bill your customers.",
        "icon_svg": CUBE_SVG,
        "category": "sales",
        "premium": False,
        "verticals": ["hair_salon", "restaurant"],
    }


def test_inside_a_category_the_apps_go_by_their_name_in_the_language(catalog):
    make_app("agenda", name_en="Zeta agenda", name_es="Agenda", category="sales")

    assert ids(listed("en", category="sales")) == ["invoice", "agenda"]
    assert ids(listed("es", category="sales")) == ["agenda", "invoice"]


def test_the_name_order_ignores_case_and_accents(catalog):
    make_app("orders", name_es="órdenes", category="sales")
    make_app("payments", name_es="Pagos", category="sales")

    assert ids(listed("es", category="sales")) == ["invoice", "orders", "payments"]


@pytest.mark.parametrize(
    ("language", "name"),
    [("es", "Facturas"), ("es-ES", "Facturas"), ("en", "Invoices"), ("fr", "Invoices")],
)
def test_the_texts_are_in_the_language_of_the_context(catalog, language, name):
    """``es`` reads the ``_es`` columns, any other language the ``_en`` ones."""
    with translation.override("en"):
        (invoice,) = [row for row in listed(language) if row.id == "invoice"]

    assert invoice.name == name


def test_the_search_looks_in_the_name_and_the_summary_of_the_language(catalog):
    assert ids(listed("en", q="stock")) == ["inventory"]
    assert ids(listed("en", q="CUSTOMERS")) == ["invoice"]
    assert ids(listed("es", q="almac")) == ["inventory"]
    # The Spanish name is not searched in English.
    assert ids(listed("en", q="almac")) == []


def test_the_filters_by_category_premium_and_vertical(catalog):
    assert ids(listed(category="catalog")) == ["inventory"]
    assert ids(listed(premium=True)) == ["whatsapp_inbox"]
    assert ids(listed(premium=False)) == ["invoice", "inventory"]
    assert ids(listed(vertical="hair_salon")) == ["invoice", "whatsapp_inbox"]
    # A retired app's vertical lists nothing: it is not in the store.
    assert ids(listed(vertical="retail")) == []
    assert ids(listed(vertical="hair_salon", premium=False, q="bill")) == ["invoice"]


def test_a_category_or_premium_that_is_not_understood_is_ignored(catalog):
    assert ids(listed(category="marketing", premium="maybe")) == [
        "invoice",
        "inventory",
        "whatsapp_inbox",
    ]


def test_an_unknown_category_is_listed_without_a_section_and_logged_once(
    catalog, caplog
):
    """The Hub went ahead of this SaaS's live.meta: the app is listed after the known sections,
    without a category, and the category filter never finds it (spec §5.3)."""
    make_app("bookings", name_en="Bookings", category="scheduling")
    make_app("chat", name_en="Chat", category="messaging")

    with caplog.at_level(logging.WARNING, logger="apps.queries"):
        rows = listed()

    assert ids(rows) == ["invoice", "inventory", "whatsapp_inbox", "bookings", "chat"]
    assert [row.category for row in rows[-2:]] == [None, None]
    warnings = [
        record for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert "bookings" in warnings[0].getMessage()
    assert "chat" in warnings[0].getMessage()
    assert ids(listed(category="sales")) == ["invoice"]
    assert ids(listed(category="scheduling")) == [
        "invoice",
        "inventory",
        "whatsapp_inbox",
        "bookings",
        "chat",
    ]


def test_the_icon_is_painted_clean():
    make_app("invoice", icon_svg=CUBE_SVG.replace("<path ", '<path onclick="steal()" '))

    (row,) = listed()

    assert row.icon_svg == CUBE_SVG


@pytest.mark.parametrize(
    "icon_svg", ["", "<p>not an icon</p>", "<svg><script>steal()</script></svg>"]
)
def test_an_unusable_icon_is_replaced_by_the_fallback_and_logged(caplog, icon_svg):
    make_app("invoice", icon_svg=icon_svg)

    with caplog.at_level(logging.WARNING, logger="apps.queries"):
        (row,) = listed()

    assert row.icon_svg == FALLBACK_ICON_SVG
    assert any(
        "invoice" in record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    )


def test_an_empty_catalog_is_an_empty_list():
    """A new database, before any release of the Hub registered its apps (spec §5.3)."""
    assert listed() == []


# --- apps.app.get --------------------------------------------------------------------------------


def detail(app_id, language="en"):
    return queries.app_get(visitor(language), AppByIdIn(id=app_id))


def test_the_detail_adds_the_description_the_requires_and_the_docs(catalog):
    app = make_app(
        "appointments",
        name_en="Appointments",
        description_en="Book every chair.",
        description_es="Reserva cada silla.",
        category="people",
        requires=["invoice", "loyalty", "gone"],
    )
    make_doc(app, "es")

    english = detail("appointments")
    spanish = detail("appointments", "es")

    assert (english.name, english.description, english.has_docs) == (
        "Appointments",
        "Book every chair.",
        True,
    )
    assert spanish.description == "Reserva cada silla."
    # In the order of `requires`, each with its name and whether its page exists (listed); one the
    # catalog does not know is shown by its id and never linked.
    assert [required.model_dump() for required in spanish.requires] == [
        {"id": "invoice", "name": "Facturas", "listed": True},
        {"id": "loyalty", "name": "Loyalty (es)", "listed": False},
        {"id": "gone", "name": "gone", "listed": False},
    ]


def test_the_detail_carries_the_card_too(catalog):
    invoice = detail("invoice")

    assert (
        invoice.id,
        invoice.summary,
        invoice.icon_svg,
        invoice.category,
        invoice.premium,
    ) == (
        "invoice",
        "Bill your customers.",
        CUBE_SVG,
        "sales",
        False,
    )
    assert invoice.requires == []


def test_has_docs_follows_what_the_documentation_would_serve(catalog):
    """English falls back to Spanish (the WORKBOOK's language); an empty markdown is no document."""
    make_doc(catalog["invoice"], "es", markdown="")
    make_doc(catalog["inventory"], "es")

    assert (detail("invoice").has_docs, detail("invoice", "es").has_docs) == (
        False,
        False,
    )
    assert (detail("inventory").has_docs, detail("inventory", "es").has_docs) == (
        True,
        True,
    )
    assert detail("whatsapp_inbox").has_docs is False


@pytest.mark.parametrize("app_id", ["nope", "loyalty", "demo"])
def test_an_unknown_or_unlisted_app_is_a_404(catalog, app_id):
    with pytest.raises(OperationError) as error:
        detail(app_id)

    assert (error.value.status, error.value.code) == (404, "apps.app_not_found")


def test_the_404_speaks_the_language_of_the_context(catalog):
    with pytest.raises(OperationError) as error, translation.override("es"):
        detail("nope", "es")

    assert error.value.message == "No hay ninguna app «nope» en el catálogo."


def test_an_unknown_category_on_the_detail_is_logged_and_shown_without_a_section(
    caplog,
):
    make_app("bookings", category="scheduling")

    with caplog.at_level(logging.WARNING, logger="apps.queries"):
        bookings = detail("bookings")

    assert bookings.category is None
    assert any("bookings" in record.getMessage() for record in caplog.records)


# --- apps.app.doc --------------------------------------------------------------------------------


def documentation(app_id, language="en"):
    return queries.app_doc(visitor(language), AppByIdIn(id=app_id))


@pytest.fixture
def documented(catalog, settings):
    settings.HUB_STATIC_BASE_URL = HUB_STATIC
    invoice = catalog["invoice"]
    make_doc(invoice, "es", markdown="# Facturas\n\n![Pantalla](docs/img/list.png)\n")
    make_doc(invoice, "en", markdown="# Invoices\n\nThe list.\n")
    return invoice


def test_the_documentation_in_spanish(documented):
    doc = documentation("invoice", "es")

    assert (doc.lang, doc.fallback) == ("es", False)
    assert '<h1 id="facturas">Facturas</h1>' in doc.html


def test_the_documentation_in_english(documented):
    doc = documentation("invoice", "en")

    assert (doc.lang, doc.fallback) == ("en", False)
    assert '<h1 id="invoices">Invoices</h1>' in doc.html


@pytest.mark.parametrize("english", [None, ""])
def test_without_english_the_spanish_one_with_a_fallback(catalog, english):
    """``en`` missing, or empty because it was retired (spec §4.2): Spanish, never empty."""
    make_doc(catalog["inventory"], "es", markdown="# Almacén\n")
    if english is not None:
        make_doc(catalog["inventory"], "en", markdown=english)

    doc = documentation("inventory", "en")

    assert (doc.lang, doc.fallback) == ("es", True)
    assert "Almacén" in doc.html


def test_the_images_point_at_the_hubs_static_files(documented):
    doc = documentation("invoice", "es")

    assert f'src="{HUB_STATIC}catalog/invoice/img/list.png"' in doc.html
    assert 'alt="Pantalla"' in doc.html


def test_the_second_read_comes_from_the_cache(documented):
    with mock.patch("apps.queries.render_markdown", wraps=render_markdown) as renderer:
        first = documentation("invoice", "es")
        second = documentation("invoice", "es")

    assert renderer.call_count == 1
    assert second.html == first.html
    key = f"apps:doc:v2:invoice:es:{source_hash(documented.docs.get(lang='es').markdown)}"
    assert cache.get(key) == first.html


def test_html_rendered_by_an_older_renderer_is_never_served(documented):
    """``render_markdown`` tightened what it lets through (live 387d04f: image paths): the key
    carries the renderer's version, so a day-long entry rendered before the deploy is not reused."""
    markdown = documented.docs.get(lang="es").markdown
    cache.set(f"apps:doc:invoice:es:{source_hash(markdown)}", "<p>stale</p>", 60)

    doc = documentation("invoice", "es")

    assert "stale" not in doc.html
    assert '<h1 id="facturas">Facturas</h1>' in doc.html


def test_the_html_is_cached_for_a_day(documented):
    with mock.patch.object(queries.cache, "set", wraps=queries.cache.set) as cache_set:
        documentation("invoice", "es")

    ((key, html, timeout), _kwargs) = cache_set.call_args
    assert key.startswith("apps:doc:v2:invoice:es:")
    assert timeout == 60 * 60 * 24


def test_a_new_document_is_a_new_key(documented):
    """The Hub writes a new markdown with its new hash: the next read renders it at once."""
    with mock.patch("apps.queries.render_markdown", wraps=render_markdown) as renderer:
        documentation("invoice", "es")
        markdown = "# Facturas v2\n"
        documented.docs.filter(lang="es").update(
            markdown=markdown, source_hash=source_hash(markdown)
        )
        doc = documentation("invoice", "es")

    assert renderer.call_count == 2
    assert "Facturas v2" in doc.html


@pytest.mark.parametrize("app_id", ["nope", "loyalty"])
def test_the_documentation_of_an_unknown_or_unlisted_app_is_a_404(catalog, app_id):
    make_doc(catalog["loyalty"], "es")

    with pytest.raises(OperationError) as error:
        documentation(app_id)

    assert (error.value.status, error.value.code) == (404, "apps.app_not_found")


def test_an_app_without_documentation_is_a_404_of_its_own(catalog):
    """Spanish is the source: no Spanish document, nothing to serve (``has_docs`` is False)."""
    make_doc(catalog["invoice"], "en", markdown="# Invoices\n")

    with pytest.raises(OperationError) as error:
        documentation("invoice", "es")

    assert (error.value.status, error.value.code) == (404, "apps.doc_not_found")
    assert detail("invoice", "es").has_docs is False


# --- apps.app.sitemap: the store's entries of /sitemap.xml (spec §8.2) ---------------------------


def sitemap_entries():
    return queries.app_sitemap(visitor(), AppSitemapIn()).apps


def test_the_sitemap_has_the_listed_apps_by_id(catalog):
    """A retired app and the demo (``listed = False``) have no page, so they are not announced."""
    assert ids(sitemap_entries()) == ["inventory", "invoice", "whatsapp_inbox"]


def test_the_sitemap_dates_an_app_by_its_spanish_documentation(catalog):
    """``lastmod`` = ``updated_at`` of the Spanish ``app_doc``, the source every language falls
    back to; the English one does not date the pages."""
    spanish_at = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
    make_doc(catalog["invoice"], "es", updated_at=spanish_at)
    make_doc(
        catalog["invoice"], "en", updated_at=datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    )

    entries = {entry.id: entry for entry in sitemap_entries()}

    assert entries["invoice"].model_dump() == {
        "id": "invoice",
        "has_docs": True,
        "updated_at": spanish_at,
    }
    assert entries["inventory"].model_dump() == {
        "id": "inventory",
        "has_docs": False,
        "updated_at": None,
    }


def test_without_a_spanish_document_the_sitemap_announces_no_documentation(catalog):
    """An empty Spanish markdown is no document (spec §4.2), and an English one alone is a page
    that answers 404 in Spanish: neither ``/docs/`` is announced, nor dated."""
    make_doc(catalog["invoice"], "es", markdown="")
    make_doc(catalog["inventory"], "en", markdown="# Stock\n")

    entries = {entry.id: entry for entry in sitemap_entries()}

    for app_id in ("invoice", "inventory"):
        assert (entries[app_id].has_docs, entries[app_id].updated_at) == (False, None)


def test_the_sitemap_reads_every_app_at_once(catalog):
    """No read per app: a crawler fetching the sitemap costs the same with three apps or thirty."""
    make_doc(catalog["invoice"], "es")
    with CaptureQueriesContext(connection) as three_apps:
        sitemap_entries()
    for number in range(5):
        make_doc(make_app(f"extra_{number}"), "es")

    with CaptureQueriesContext(connection) as eight_apps:
        assert len(sitemap_entries()) == 8

    assert len(eight_apps.captured_queries) == len(three_apps.captured_queries)


def test_an_empty_catalog_has_no_sitemap_entries():
    assert sitemap_entries() == []


# --- known_verticals: what BusinessType.clean() checks a vertical against (spec §5.4) -----------


def test_known_verticals_is_the_sorted_union_of_every_app(catalog):
    """Retired apps included: a vertical stays known while a row of shared.app declares it."""
    assert queries.known_verticals() == ["hair_salon", "restaurant", "retail"]


def test_no_app_no_vertical():
    assert queries.known_verticals() == []
