"""The index of erplora.com's admin names each section once and speaks the staff's language.

allauth's ``account`` and our ``accounts`` were both «Accounts» («Cuentas»), and in Spanish the models whose name
comes from their class (allauth's authenticators and sessions, live's outbox) or from a package without Spanish
(Cookie consent) kept their English. This walks every section and model a superuser sees, so a new app cannot bring either back.
"""

import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.utils import translation

# The same word in both languages, on purpose: a name, a brand, or the word Spanish uses (allauth's own Spanish keeps
# «MFA»).
SAME_IN_BOTH = {"Apps", "Base", "Cookies", "MFA", "WhatsApp"}



@pytest.fixture
def index(admin_user):
    """``{language: [(app_label, section, {object_name: model})]}`` as the index shows them to a superuser."""
    request = RequestFactory().get("/admin/")
    request.user = admin_user
    shown = {}
    for language in ("en", "es"):
        with translation.override(language):
            shown[language] = [
                (app["app_label"], str(app["name"]), {model["object_name"]: str(model["name"]) for model in app["models"]})
                for app in admin.site.get_app_list(request)
            ]
    return shown


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_every_section_of_the_index_has_a_name_of_its_own(index, language):
    names = [section for _, section, _ in index[language]]

    assert sorted(name for name in names if names.count(name) > 1) == []


@pytest.mark.django_db
def test_every_section_and_model_of_the_index_speaks_spanish(index):
    english = {label: (section, models) for label, section, models in index["en"]}
    untranslated = []
    for label, section, models in index["es"]:
        en_section, en_models = english[label]
        if section == en_section and section not in SAME_IN_BOTH:
            untranslated.append(f"{label}: {section}")
        untranslated += [
            f"{label}.{name}" for key, name in models.items() if name == en_models[key] and name not in SAME_IN_BOTH
        ]

    assert untranslated == []
