"""Every icon a template of saas-next paints is in the offline Iconify bundle (ported from
ERPlora/saas ``apps/public/landing/tests/test_icon_bundle_coverage.py``).

Today's SaaS falls back to api.iconify.design for a missing icon; saas-next's CSP admits no such
host (`connect-src 'self'`), so a missing icon is not slow here: it is an empty square.
"""

import re
from pathlib import Path

from django.apps import apps

SAAS_NEXT = Path(__file__).resolve().parents[2]
BUNDLE = SAAS_NEXT / "static" / "vendor" / "iconify-data" / "icons-offline.js"
#: `<iconify-icon icon="lucide:arrow-left">` and `<span class="iconify" data-icon="ion:logo-google">`.
ICON_ATTRIBUTE = re.compile(r'(?:\bicon|data-icon)="([a-z0-9-]+:[a-z0-9-]+)"')
BUNDLE_KEY = re.compile(r'"([a-z0-9-]+:[a-z0-9-]+)":\{')


def _templates():
    yield from (SAAS_NEXT / "templates").rglob("*.html")
    # The templates of every app of saas-next (``base/``, ``accounts/``…, at the project root).
    for config in apps.get_app_configs():
        if Path(config.path).is_relative_to(SAAS_NEXT):
            yield from (Path(config.path) / "templates").rglob("*.html")


def test_the_templates_of_the_apps_at_the_project_root_are_scanned():
    """Positive control: a layout change must not leave the apps' templates out silently."""
    assert any(path.is_relative_to(SAAS_NEXT / "accounts" / "templates") for path in _templates())


def test_every_static_icon_of_the_templates_is_bundled():
    used = {icon for path in _templates() for icon in ICON_ATTRIBUTE.findall(path.read_text(encoding="utf-8"))}
    bundled = set(BUNDLE_KEY.findall(BUNDLE.read_text(encoding="utf-8")))

    assert used, "no static icon found: did the template layout change?"
    assert sorted(used - bundled) == []
