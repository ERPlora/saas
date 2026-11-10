"""Fixtures of the public web's tests."""

import json
import re

import pytest

from hubs.tests.conftest import no_plans  # noqa: F401 - an empty plan table, for a test that builds its own
from public.templatetags.public_assets import PUBLIC_ENTRY

#: The files `{% public_assets %}` links for the public entry in these tests.
PUBLIC_JS = "assets/public-abc123.js"
PUBLIC_CSS = "assets/public-def456.css"

#: Where a page writes its per-response tokens: the CSP nonce and the CSRF token.
RESPONSE_TOKEN = re.compile(
    r"""(nonce="|name="csrfmiddlewaretoken" value="|var CSRF = "|'X-CSRFToken': ')[^"']+"""
)


@pytest.fixture(autouse=True)
def public_indexing(settings):
    settings.PUBLIC_INDEXING_ENABLED = True


def without_tokens(html: str) -> str:
    """The page without its per-response tokens: random strings, not what the page says."""
    return RESPONSE_TOKEN.sub(r"\1", html)


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


@pytest.fixture(autouse=True)
def fixed_response_tokens(monkeypatch):
    """Every test here gets one CSRF token and one CSP nonce that mean nothing, not a random draw.

    A random token can hold whatever a test scans the raw page for, so no test may depend on the
    draw (saas#264). Only the value is fixed: a page that stops asking for a token goes on without
    it. ``test_response_tokens.py`` keeps the real ones, to say that this hides nothing, and so does
    ``test_template_tokens.py``, to hold each template's tokens against the server's.
    """
    monkeypatch.setattr("django.utils.csp.generate_nonce", lambda: "a" * 22)
    monkeypatch.setattr("django.middleware.csrf._get_new_csrf_string", lambda: "a" * 32)


@pytest.fixture
def tokens_spelling(monkeypatch):
    """Make the per-response tokens spell some words, as a random one does now and then.

    Every public page carries a CSP nonce and, since the language forms of its footer (PUBLIC-F13),
    a CSRF token: random strings, not copy. A 64-character token holds three given letters about
    once in four thousand renders, which made scans of the raw page fail by chance and stopped a
    deploy of main (saas#261). A test that scans a page for a short word reads it with
    :func:`without_tokens`, which keeps everything else the page says, and asks for this fixture.
    It patches the same two functions as :func:`fixed_response_tokens`, later, so it wins.

    The words must be alphanumeric and fit in a CSRF secret (32 characters): Django ciphers the
    secret with the mask, character by character, in its own alphabet.
    """

    def spell(*words: str) -> None:
        monkeypatch.setattr("django.utils.csp.generate_nonce", lambda: "-".join((*words, "x")))
        monkeypatch.setattr(
            "django.middleware.csrf._get_new_csrf_string",
            lambda: "".join(words).ljust(32, "a"),
        )

    return spell
