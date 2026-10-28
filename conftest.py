"""Fixtures shared by every saas-next test."""

import json
import logging

import pytest
from django.conf import settings as django_settings
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


def _log_streams() -> dict[str, list]:
    """The stream each console handler of ``settings.LOGGING`` writes to, per logger (the root as ``""``).

    Only ``logging.StreamHandler`` itself: pytest's own handlers are subclasses and change at every phase."""
    names = ["", *django_settings.LOGGING.get("loggers", {})]
    return {
        name: [h.stream for h in logging.getLogger(name).handlers if type(h) is logging.StreamHandler]
        for name in names
    }


@pytest.fixture(autouse=True)
def _log_stays_on_its_stream():
    """Every test leaves the process's log writing where it found it.

    Rebuilding the logging (``dictConfig``, ``django.setup()``, a ``LOGGING`` override) inside a capture ties the
    console handler to that capture's stream, which pytest closes when the test ends: every later line of every
    test comes out as a logging error on a closed file (FIX-SAAS-LOGGING-TEST-LEAVES-CLOSED-STREAM).
    """
    before = _log_streams()
    yield
    assert _log_streams() == before, (
        "this test left the log writing to another stream; point the console handler back "
        "(logging.getHandlerByName('console').setStream) instead of rebuilding the logging inside a capture"
    )


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
def _no_real_vies(settings):
    """No test reaches the European Commission's VIES (billing/vies.py): a call nobody faked goes to a
    closed port and is ``unavailable`` at once. Tests fake the network with billing/tests/vies_double.py."""
    settings.VIES_ENDPOINT = "http://127.0.0.1:9/check-vat-number"
    settings.VIES_CONNECT_TIMEOUT_SECONDS = 1.0
    settings.VIES_TIMEOUT_SECONDS = 1.0


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


class FakeGoogleRecaptcha:
    """Google's reCAPTCHA assessments, played in the tests (``live.recaptcha.urlopen``).

    A token reads ``human:<action>`` (valid, made for ``<action>``, score 0.9) or ``bot:<action>`` (valid, score
    0.1); anything else is malformed. ``down = True`` makes Google unreachable, ``refusing = <4xx>`` makes it refuse
    the key (a bad key, the quota, the billing). ``asked`` keeps each ``(token, expectedAction)`` it was asked about.
    """

    def __init__(self):
        self.asked: list[tuple[str, str]] = []
        self.down = False
        self.refusing: int | None = None

    def __call__(self, request, timeout=None):
        import io
        import urllib.error

        event = json.loads(request.data)["event"]
        self.asked.append((event["token"], event["expectedAction"]))
        if self.down:
            raise urllib.error.URLError("unreachable")
        if self.refusing:
            raise urllib.error.HTTPError(request.full_url, self.refusing, "Client Error", {}, io.BytesIO(b"{}"))
        kind, _, action = event["token"].partition(":")
        if kind not in ("human", "bot"):
            answer = {"tokenProperties": {"valid": False, "invalidReason": "MALFORMED"}, "riskAnalysis": {"score": 0.0}}
        else:
            answer = {
                "tokenProperties": {"valid": True, "action": action},
                "riskAnalysis": {"score": 0.9 if kind == "human" else 0.1, "reasons": []},
            }
        return io.BytesIO(json.dumps(answer).encode())


@pytest.fixture
def recaptcha(settings, monkeypatch):
    """reCAPTCHA switched on (``LIVE["recaptcha"]``, as RECAPTCHA_* do outside the tests), Google played by
    ``FakeGoogleRecaptcha``. The test run keeps it off (config/settings_pytest.py) unless a test asks for this."""
    from live import recaptcha as live_recaptcha

    settings.LIVE = {
        **settings.LIVE,
        "recaptcha": {
            "enabled": True,
            "project": "erplora",
            "site_key": "test-site-key",
            "api_key": "test-api-key",
            "min_score": 0.5,
        },
    }
    google = FakeGoogleRecaptcha()
    monkeypatch.setattr(live_recaptcha, "urlopen", google)
    return google
