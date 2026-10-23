"""The assistant's Spanish catalog (``assistant/locale/es/LC_MESSAGES/django.mo``) covers every message of the app.

UI in ``en`` + ``es`` (PLAN §5): a ``gettext`` literal or a ``{% translate %}`` of an admin page without its Spanish
entry reaches a Spanish member of the staff in English (saas#2489 of the old product: the sections of the admin came
out in English). This reads the compiled catalog, so a ``.po`` edited without ``compilemessages`` fails too. Same
scans as ``fiscal/tests/test_locale.py``.
"""

import gettext

from django.conf import settings

from base.tests.test_locale import messages_of
from public.tests.test_legal import template_messages

CATALOG = settings.BASE_DIR / "assistant" / "locale" / "es" / "LC_MESSAGES" / "django.mo"
TEMPLATES = sorted((settings.BASE_DIR / "assistant" / "templates").rglob("*.html"))


class _Untranslated(gettext.NullTranslations):
    def gettext(self, message):
        return None


def spanish():
    with CATALOG.open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)
    catalog.add_fallback(_Untranslated())
    return catalog


def test_the_scan_finds_the_messages_of_the_assistant():
    found = {message for _, message in messages_of("assistant")}

    assert {"AI assistant", "AI providers", "Unreadable: type the key again"} <= found


def test_every_message_of_the_assistant_has_its_spanish_translation():
    catalog = spanish()
    missing = [f"{where}: {message!r}" for where, message in messages_of("assistant") if not catalog.gettext(message)]

    assert missing == []


def test_every_message_of_its_admin_pages_has_its_spanish_translation():
    catalog = spanish()
    missing = [
        f"{template.name}: {message!r}"
        for template in TEMPLATES
        for message in template_messages(template)
        if not catalog.gettext(message)
    ]

    assert missing == []
