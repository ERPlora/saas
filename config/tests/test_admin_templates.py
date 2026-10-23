"""Every admin page of our own looks like the rest of Django 6.1's admin.

Django 6.1 styles its breadcrumbs as an ``<ol>`` of ``<li>`` and its aligned forms with ``forms.css``. A page of our
own that kept the older ``<div class="breadcrumbs">`` showed a bare line of links, and one with aligned fields
without ``forms.css`` showed them out of line. This walks every admin template of the SaaS's own apps, so a new page
cannot bring the old markup back.
"""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR).resolve()

# The pages known to override the breadcrumbs: if the walk stops finding them, it is walking the wrong place.
KNOWN = {
    "accounts/templates/admin/accounts/apikey/issued.html",
    "accounts/templates/admin/accounts/hubs.html",
    "assistant/templates/admin/assistant/aiprovider/models.html",
    "assistant/templates/admin/assistant/airoutingpolicy/policy.html",
    "assistant/templates/admin/assistant/airoutingpolicy/try.html",
    "fiscal/templates/admin/fiscal/representationgrant/review.html",
    "fiscal/templates/admin/fiscal/representationgrant/stamp.html",
}

BREADCRUMBS_BLOCK = re.compile(r"{%\s*block breadcrumbs\s*%}(.*?){%\s*endblock", re.S)


def own_admin_templates():
    """The admin templates of every installed app that lives at the root of the SaaS (no third party, no package)."""
    found = []
    for config in apps.get_app_configs():
        app_dir = Path(config.path).resolve()
        if app_dir.parent != BASE_DIR:
            continue
        found += sorted((app_dir / "templates" / "admin").rglob("*.html"))
    return [path.relative_to(BASE_DIR).as_posix() for path in found]


TEMPLATES = own_admin_templates()


def test_the_walk_finds_every_page_of_our_own():
    assert KNOWN <= set(TEMPLATES)


@pytest.mark.parametrize("template", TEMPLATES)
def test_no_page_keeps_the_old_breadcrumbs(template):
    source = (BASE_DIR / template).read_text()

    assert 'class="breadcrumbs"' not in source.replace('<ol class="breadcrumbs">', "")


@pytest.mark.parametrize("template", TEMPLATES)
def test_its_own_breadcrumbs_are_the_admins_list_ending_on_the_current_page(template):
    source = (BASE_DIR / template).read_text()
    block = BREADCRUMBS_BLOCK.search(source)
    if block is None:
        pytest.skip("keeps the breadcrumbs of the page it extends")

    crumbs = block.group(1).strip()
    assert crumbs.startswith('<ol class="breadcrumbs">') and crumbs.endswith("</ol>")
    items = re.findall(r"<li[ >].*?</li>", crumbs, re.S)
    assert len(items) >= 2 and "{% url 'admin:index' %}" in items[0].replace('"', "'")
    assert items[-1].startswith('<li aria-current="page">') and "<a " not in items[-1]
    assert crumbs.count("<li") == len(items), "every crumb is a list item"


@pytest.mark.parametrize("template", TEMPLATES)
def test_a_page_with_aligned_fields_loads_the_admins_form_styles(template):
    source = (BASE_DIR / template).read_text()
    if not re.search(r'class="[^"]*\b(aligned|form-row)\b', source):
        pytest.skip("no aligned fields")
    if '{% extends "admin/base_site.html" %}' not in source:
        pytest.skip("the change form it extends loads them")

    assert '{% static "admin/css/forms.css" %}' in source
