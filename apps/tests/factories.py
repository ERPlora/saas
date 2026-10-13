"""Rows of the catalog for the tests, as the Hub's ``register_apps`` writes them (spec §3.1).

The tests are the only code outside ``apps/{models,queries,admin,checks}.py`` that names ``App`` and
``AppDoc`` (``test_lint.py``): the SaaS never writes them, the Hub does.
"""

import hashlib

from django.utils import timezone

from apps.models import App, AppDoc

#: ionicons' cube-outline, as the Hub bakes it (spec §4.6).
CUBE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="ionicon">'
    '<path d="m69 153.99 187 110 187-110M256 463.99v-200" fill="none" stroke="currentColor" '
    'stroke-linecap="round" stroke-linejoin="round" stroke-width="32px"></path></svg>'
)


def make_app(app_id: str = "inventory", **overrides) -> App:
    """A registered app; its names and texts derive from ``app_id`` unless overridden."""
    title = app_id.replace("_", " ").title()
    fields = {
        "name_en": title,
        "name_es": f"{title} (es)",
        "summary_en": f"{title} in one line.",
        "summary_es": f"{title} en una línea.",
        "description_en": f"{title} in a paragraph.",
        "description_es": f"{title} en un párrafo.",
        "icon": "ion:cube-outline",
        "icon_svg": CUBE_SVG,
        "category": "catalog",
        "premium": False,
        "requires": [],
        "verticals": [],
        "listed": True,
        "hub_version": "dev",
        "registered_at": timezone.now(),
        **overrides,
    }
    return App.objects.create(id=app_id, **fields)


def source_hash(markdown: str) -> str:
    return hashlib.sha256(markdown.encode()).hexdigest()


def make_doc(
    app: App, lang: str = "es", markdown: str = "# Doc\n\nText.\n", **overrides
) -> AppDoc:
    """The user documentation of ``app`` in ``lang``, with the hash the Hub computes."""
    fields = {
        "markdown": markdown,
        "source_hash": source_hash(markdown),
        "updated_at": timezone.now(),
        **overrides,
    }
    return AppDoc.objects.create(app=app, lang=lang, **fields)
