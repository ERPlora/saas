"""Fixtures of the public web's tests."""

import json

import pytest

from public.templatetags.public_assets import PUBLIC_ENTRY

#: The files `{% public_assets %}` links for the public entry in these tests.
PUBLIC_JS = "assets/public-abc123.js"
PUBLIC_CSS = "assets/public-def456.css"


@pytest.fixture(autouse=True)
def public_manifest(settings, tmp_path):
    """A Vite manifest with the public entry, as `vite build` writes it (the files need not exist).

    The tests run with DEBUG off, so every page that extends the public base reads the manifest:
    this one keeps them independent of whether `pnpm build` ran.
    """
    manifest = tmp_path / "public-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "frontend/main.ts": {
                    "file": "assets/main-abc123.js",
                    "src": "frontend/main.ts",
                    "isEntry": True,
                },
                PUBLIC_ENTRY: {
                    "file": PUBLIC_JS,
                    "src": PUBLIC_ENTRY,
                    "isEntry": True,
                    "css": [PUBLIC_CSS],
                },
            }
        )
    )
    settings.LIVE = {
        **settings.LIVE,
        "spa": {**settings.LIVE["spa"], "manifest": manifest},
    }
    return manifest
