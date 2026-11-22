"""Every permission of the SaaS's apps has its phrase, and Spanish reads it from the app's own catalogue.

An app declares its permissions as ``{permission: phrase}`` (``LiveAppConfig.permissions``): the phrase says in business
words what the permission lets a person do. It is written in English, as the source of i18n, and its Spanish lives in
the app's own compiled catalogue (``<app>/locale/es/LC_MESSAGES/django.mo``, or the project's ``locale/`` for an app
without one). What Spanish shows is compared with that entry, so a phrase left out of the catalogue, not compiled, or
that an earlier catalogue translates otherwise (Django keeps the first one's words) fails here, naming the permission.
"""

import gettext
from collections.abc import Mapping
from pathlib import Path

from django.conf import settings
from django.utils import translation
from live.meta import all_live_app_configs

SPANISH = Path("locale", "es", "LC_MESSAGES", "django.mo")


def saas_configs() -> list:
    """The apps of the SaaS's own code that declare permissions."""
    root = Path(settings.BASE_DIR).resolve()
    return [
        config
        for config in all_live_app_configs()
        if config.permissions and Path(config.path).resolve().is_relative_to(root)
    ]


def own_catalogue(config) -> dict[str, str]:
    """The compiled Spanish entries of the app's catalogue, by message."""
    path = Path(config.path, SPANISH)
    if not path.exists():
        path = Path(settings.BASE_DIR, SPANISH)
    with path.open("rb") as compiled:
        return gettext.GNUTranslations(compiled)._catalog


def phrases() -> list[tuple[object, str, object]]:
    """``(app, permission, phrase)`` of every permission of the SaaS's apps; one declared without its phrase (a list)
    has ``None``."""
    return [
        (config, permission, config.permissions[permission] if isinstance(config.permissions, Mapping) else None)
        for config in saas_configs()
        for permission in config.permissions
    ]


def test_every_app_with_permissions_is_read():
    labels = {config.label for config in saas_configs()}

    assert {"accounts", "billing", "hubs"} <= labels
    assert len(phrases()) > 10


def test_every_app_declares_its_permissions_with_their_phrases():
    assert [config.label for config in saas_configs() if not isinstance(config.permissions, Mapping)] == []


def test_spanish_reads_every_phrase_from_its_own_catalogue():
    wrong = []
    for config, permission, phrase in phrases():
        if phrase is None:
            wrong.append(f"{permission}: no phrase")
            continue
        with translation.override("en"):
            english = str(phrase)
        own = own_catalogue(config).get(english, "")
        with translation.override("es"):
            said = str(phrase)
        if not own or said != own:
            wrong.append(f"{permission}: {english!r} says «{said}», its catalogue «{own}»")
    assert wrong == []
