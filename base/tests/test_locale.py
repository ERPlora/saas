"""The Spanish catalog (``locale/es/LC_MESSAGES/django.mo``) covers every message of ``base`` and ``accounts``.

UI in ``en`` + ``es`` (PLAN §5): a ``gettext`` literal without its Spanish entry reaches a Spanish
visitor in English, and nothing else notices. This reads the compiled catalog, so a ``.po`` edited
without ``compilemessages`` (``msgfmt``) fails too. Django's and allauth's catalogs do not count: a
message of ours that only happens to match one of theirs would change meaning with their next
release.
"""

import ast
import gettext
from pathlib import Path

import pytest
from django.conf import settings

CATALOG = Path(settings.BASE_DIR) / "locale" / "es" / "LC_MESSAGES" / "django.mo"
PACKAGES = ("base", "accounts")
GETTEXT_CALLS = {
    "_",
    "gettext",
    "gettext_lazy",
    "gettext_noop",
    "ngettext",
    "ngettext_lazy",
}


def messages_of(package: str) -> list[tuple[str, str]]:
    """``(file:line, msgid)`` of every gettext call with a literal in ``package`` (not its tests)."""
    root = Path(settings.BASE_DIR) / package
    found = []
    for path in sorted(root.rglob("*.py")):
        if {"tests", "migrations"} & set(path.relative_to(root).parts):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            first = node.args[0]
            if (
                name in GETTEXT_CALLS
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                found.append(
                    (
                        f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}",
                        first.value,
                    )
                )
    return found


class _Untranslated(gettext.NullTranslations):
    def gettext(self, message):
        return None

    def ngettext(self, singular, plural, n):
        return None


def spanish():
    with CATALOG.open("rb") as handle:
        catalog = gettext.GNUTranslations(handle)
    catalog.add_fallback(_Untranslated())
    return catalog


def test_the_scan_finds_the_messages_of_the_apps():
    found = {message for package in PACKAGES for _, message in messages_of(package)}

    assert {
        "Base",
        "Accounts",
        "Sign in to see your businesses.",
        "The account is no longer active.",
    } <= found


@pytest.mark.parametrize("package", PACKAGES)
def test_every_message_has_its_spanish_entry(package):
    catalog = spanish()

    missing = [
        f"{where} {message!r}"
        for where, message in messages_of(package)
        if catalog.gettext(message) is None
    ]

    assert missing == []
