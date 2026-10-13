"""``{% public_assets %}``: the public pages load the Vite entry ``frontend/public.ts`` (spec §8.4).

The same contract as the SPA's HTML (``live/templates/live/spa.html``): the build's files under
``{STATIC_URL}spa/`` from the manifest, every ``<script>`` and ``modulepreload`` with the response's
CSP nonce (``'strict-dynamic'`` runs only what a nonce let in), and with DEBUG the dev server's HMR
client and entry. Read through ``live.spa.spa_assets(request, entry=…)``.
"""

import json

import pytest
from django.template import Context, Template
from django.test import RequestFactory

from public.templatetags.public_assets import PUBLIC_ENTRY


def render(**context) -> str:
    context.setdefault("request", RequestFactory().get("/"))
    context.setdefault("csp_nonce", "n0nce")
    return Template("{% load public_assets %}{% public_assets %}").render(
        Context(context)
    )


@pytest.fixture
def public_manifest(settings, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                PUBLIC_ENTRY: {
                    "file": "assets/public-abc.js",
                    "src": PUBLIC_ENTRY,
                    "isEntry": True,
                    "css": ["assets/public-def.css"],
                    "imports": ["_ionic-123.js"],
                },
                "_ionic-123.js": {
                    "file": "assets/ionic-123.js",
                    "css": ["assets/ionic-456.css"],
                },
            }
        )
    )
    settings.LIVE = {
        **settings.LIVE,
        "spa": {**settings.LIVE["spa"], "manifest": manifest, "dev_server": None},
    }
    settings.DEBUG = False
    return manifest


def test_the_entry_is_the_public_one():
    assert PUBLIC_ENTRY == "frontend/public.ts"


def test_production_links_the_build_from_the_manifest_with_the_nonce(public_manifest):
    html = render()

    assert '<link rel="stylesheet" href="/static/spa/assets/public-def.css">' in html
    assert '<link rel="stylesheet" href="/static/spa/assets/ionic-456.css">' in html
    assert (
        '<link rel="modulepreload" href="/static/spa/assets/ionic-123.js" nonce="n0nce">'
        in html
    )
    assert (
        '<script type="module" src="/static/spa/assets/public-abc.js" nonce="n0nce"></script>'
        in html
    )
    assert "main" not in html


def test_debug_loads_the_dev_server_client_and_the_public_entry(settings):
    settings.DEBUG = True
    settings.LIVE = {
        **settings.LIVE,
        "spa": {**settings.LIVE["spa"], "dev_server": "http://localhost:5174"},
    }

    html = render()

    assert (
        '<script type="module" src="http://localhost:5174/static/spa/@vite/client" nonce="n0nce"></script>'
        in html
    )
    assert (
        '<script type="module" src="http://localhost:5174/static/spa/frontend/public.ts" nonce="n0nce"></script>'
        in html
    )


def test_without_a_nonce_it_refuses_to_render(public_manifest):
    """Without Django's CSP middleware the scripts would be blocked by 'strict-dynamic' with no error."""
    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured, match="nonce"):
        render(csp_nonce=None)
