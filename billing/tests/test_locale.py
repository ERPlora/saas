"""billing's Spanish catalog (``billing/locale/es/LC_MESSAGES/django.mo``) covers every message of billing.

UI in ``en`` + ``es`` (PLAN §5): a ``gettext`` literal without its Spanish entry reaches a Spanish account
in English. This reads the compiled catalog, so a ``.po`` edited without ``compilemessages`` fails too.
Same scan as ``base/tests/test_locale.py``, over billing's own catalog.
"""

import gettext

from django.conf import settings

from base.tests.test_locale import messages_of

CATALOG = settings.BASE_DIR / "billing" / "locale" / "es" / "LC_MESSAGES" / "django.mo"


class _Untranslated(gettext.NullTranslations):
    def gettext(self, message):
        return None


def spanish():
    with CATALOG.open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)
    catalog.add_fallback(_Untranslated())
    return catalog


def test_the_scan_finds_the_messages_of_billing():
    found = {message for _, message in messages_of("billing")}

    assert {"Billing", "Check now in VIES", "Enter a VAT number."} <= found


def test_every_message_of_billing_has_its_spanish_translation():
    catalog = spanish()
    missing = [
        f"{where}: {message!r}"
        for where, message in messages_of("billing")
        if not catalog.gettext(message)
    ]

    assert missing == []
