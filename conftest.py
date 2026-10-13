"""Fixtures shared by every saas-next test."""

import json

import pytest
from django.contrib.auth import get_user_model
from django.utils import translation

PASSWORD = "correct horse battery staple"
GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com"
SPA_ENTRY = "frontend/main.ts"
PUBLIC_ENTRY = "frontend/public.ts"


@pytest.fixture(autouse=True)
def _default_language():
    """Every test ends in the default language.

    LocaleMiddleware activates the language of a request (``Accept-Language: es``) in the thread
    and nothing deactivates it, so the next test would otherwise run in Spanish.
    """
    yield
    translation.deactivate()


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def google(settings):
    """Google sign-in configured, as GOOGLE_OAUTH_CLIENT_ID/_SECRET do outside the tests.

    The tests run without Google credentials, so the button is hidden and the routes answer 404
    unless a test asks for this fixture.
    """
    provider = dict(settings.SOCIALACCOUNT_PROVIDERS["google"])
    provider["APP"] = {
        "client_id": GOOGLE_CLIENT_ID,
        "secret": "test-secret",
        "key": "",
    }
    settings.SOCIALACCOUNT_PROVIDERS = {
        **settings.SOCIALACCOUNT_PROVIDERS,
        "google": provider,
    }
    settings.GOOGLE_OAUTH_ENABLED = True
    return provider["APP"]


@pytest.fixture
def ana(db):
    """An active account with a password, no hub yet."""
    return get_user_model().objects.create_user(
        email="ana@example.com",
        password=PASSWORD,
        first_name="Ana",
        last_name="García",
        language="es",
    )


@pytest.fixture(autouse=True)
def _empty_cache():
    """Every test starts with an empty cache: rate-limit counters must not cross tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def spa_manifest(settings, tmp_path):
    """A Vite build manifest for the SPA entry and the public web's (`frontend/public.ts`), as
    `vite build` writes it (the files need not exist)."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                SPA_ENTRY: {
                    "file": "assets/main-abc123.js",
                    "src": SPA_ENTRY,
                    "isEntry": True,
                    "css": ["assets/main-def456.css"],
                    "imports": ["_vendor-789.js"],
                },
                "_vendor-789.js": {"file": "assets/vendor-789.js"},
                PUBLIC_ENTRY: {
                    "file": "assets/public-abc123.js",
                    "src": PUBLIC_ENTRY,
                    "isEntry": True,
                    "css": ["assets/public-def456.css"],
                },
            }
        )
    )
    settings.LIVE = {
        **settings.LIVE,
        "spa": {**settings.LIVE["spa"], "manifest": manifest},
    }
    return manifest
