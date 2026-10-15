"""fiscal's Spanish catalog (``fiscal/locale/es/LC_MESSAGES/django.mo``) covers every message of fiscal.

UI in ``en`` + ``es`` (PLAN §5): a ``gettext`` literal or a ``{% translate %}`` of the review page without its
Spanish entry reaches a Spanish member of the staff, or a Spanish customer, in English. This reads the compiled
catalog, so a ``.po`` edited without ``compilemessages`` fails too. Same scans as ``billing/tests/test_locale.py``
(Python) and ``public/tests/test_legal.py`` (templates), over fiscal's own catalog.
"""

import gettext

import pytest
from django.conf import settings

from base.tests.test_locale import messages_of
from public.tests.test_legal import template_messages

CATALOG = settings.BASE_DIR / "fiscal" / "locale" / "es" / "LC_MESSAGES" / "django.mo"
TEMPLATES = sorted((settings.BASE_DIR / "fiscal" / "templates").rglob("*.html"))


class _Untranslated(gettext.NullTranslations):
    def gettext(self, message):
        return None


def spanish():
    with CATALOG.open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)
    catalog.add_fallback(_Untranslated())
    return catalog


def test_the_scan_finds_the_messages_of_fiscal():
    found = {message for _, message in messages_of("fiscal")}

    assert {
        "Fiscal documentation",
        "Attach the signed model.",
        "Under review",
        "Write the reason: the customer reads it.",
    } <= found


def test_every_message_of_fiscal_has_its_spanish_translation():
    catalog = spanish()
    missing = [
        f"{where}: {message!r}"
        for where, message in messages_of("fiscal")
        if not catalog.gettext(message)
    ]

    assert missing == []


def test_the_review_page_is_scanned():
    assert [path.name for path in TEMPLATES] == ["review.html"]


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_every_message_of_a_fiscal_template_has_its_spanish_entry(template):
    catalog = spanish()
    messages = template_messages(template)

    assert messages, f"{template.name} has no translatable message"
    assert [m for m in messages if not catalog.gettext(m)] == [], (
        "add the msgid/msgstr to fiscal/locale/es/LC_MESSAGES/django.po and compile"
    )
