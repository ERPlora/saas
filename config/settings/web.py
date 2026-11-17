from django.utils.csp import CSP
from live.csp import base_policy, debug_policy
from live.recaptcha import with_recaptcha

from config.settings.accounts import (
    RECAPTCHA_API_KEY,
    RECAPTCHA_ENABLED,
    RECAPTCHA_ENDPOINT,
    RECAPTCHA_MIN_SCORE,
    RECAPTCHA_PROJECT,
    RECAPTCHA_SITE_KEY,
)
from config.settings.core import BASE_DIR, DEBUG, VITE_DEV_PORT, VITE_DEV_SERVER, config
from config.settings.hub_contract import HUB_ADMIN_ORIGIN, HUB_ORIGIN_PATTERN

# Internationalization: English is the source, Spanish the translation.

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("es", "Español")]
LOCALE_PATHS = [BASE_DIR / "locale"]
# LocaleMiddleware reads this cookie, then Accept-Language, then `en`. The public web's switcher
# (`POST /set-language/`, public/language.py) writes it; `User.language` is the panel's, and wins over
# the cookie there for a signed-in account (base/language.py).
LANGUAGE_COOKIE_NAME = "_lang"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365  # 1 year
LANGUAGE_COOKIE_SAMESITE = "Lax"
LANGUAGE_COOKIE_SECURE = not DEBUG
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True
# `urlize` (the links of the branded mails, base/emails.py) opens a link written without its scheme over HTTPS:
# Django 2028's default, taken now.
URLIZE_ASSUME_HTTPS = True

# Content Security Policy (Django's native middleware, nonce per response; packages/live).
# `form-action` filters the whole redirect chain of a form post: «Continue with Google» posts to
# allauth.headless's provider redirect, which answers 302 to accounts.google.com, the hub-login page
# posts its form to the hub's origin and the admin's «Open in the Hub admin» to the platform host
# (named on its own: `HUB_ADMIN_CALLBACK_URL` may live outside the hubs' pattern). «Continue with Google» adds no
# script, frame nor connection source; reCAPTCHA does (below).

# Switched on, reCAPTCHA's scripts, frames and connection, and its Trusted Types policy (`goog#html`), on the
# sign-in's pages; off (the default), nothing of Google's reCAPTCHA.
SECURE_CSP = debug_policy(VITE_DEV_SERVER) if DEBUG else base_policy()
if RECAPTCHA_ENABLED:
    SECURE_CSP = with_recaptcha(SECURE_CSP)
SECURE_CSP["form-action"] = [
    *SECURE_CSP["form-action"],
    "https://accounts.google.com",
    HUB_ORIGIN_PATTERN,
    HUB_ADMIN_ORIGIN,
]
# «Read aloud» of the panel's assistant plays the mp3 it fetched from its own route (base.assistant.speak) as a
# `blob:` URL; without `media-src` the browser falls back to `default-src 'self'` and refuses it.
SECURE_CSP["media-src"] = [CSP.SELF, "blob:"]

# Static files: WhiteNoise. The template pages' Ionic (the public web, the error pages) and fonts are
# vendored under static/vendor/ (nothing from a CDN). Vite already hashes the SPA build, served under /static/spa/
# (Vite's `base`), so no Manifest storage and its hashed assets are immutable.

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
SPA_DIST = BASE_DIR / "frontend" / "dist"
STATICFILES_DIRS = [
    BASE_DIR / "static",
    *([("spa", SPA_DIST)] if SPA_DIST.is_dir() else []),
]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_IMMUTABLE_FILE_TEST = r"^/static/spa/assets/"

# Operations, live queries and the SPA (packages/live). The scope of an operation is the user.

LIVE = {
    "context_builder": "base.operations.UserContextBuilder",
    "control_alias": "default",
    # Signing out, a new password and «Close the other sessions» record it on the account's channel: every stream of
    # the account re-reads its session and the one that ended says bye, whatever its page subscribes to (live.E019).
    "session_events": ["accounts.session.closed"],
    # A cut of the database (a restart, AWS's maintenance, the Blue/Green switchover): a read waits and tries again up
    # to this long in the whole request, far below the 120 s of the load balancer. What tries again on its own gets its
    # 503 at once: the Hub's /internal,
    # the webhooks, and /readyz, which has to say the database is gone before its probes give up.
    "database_cut": {
        "wait_seconds": config("DB_CUT_WAIT_SECONDS", default=20, cast=int),
        "no_wait_prefixes": ("/internal/", "/webhooks/", "/readyz"),
    },
    # Shortest hub slug (live.slugs, shared with the Hub): 3 in production; development opens
    # one-letter slugs for the demo hubs `a` and `b` (`demo_seed`).
    "hub_slug_min_length": 1 if DEBUG else 3,
    "spa": {
        "entry": "frontend/main.ts",
        "manifest": SPA_DIST / ".vite" / "manifest.json",
        "dev_server": VITE_DEV_SERVER if DEBUG else None,
        "palette_default": "erplora",
        "palettes": ["erplora"],
        "title": "ERPlora Cloud",
        # The tab's and the home screen's icons, the public web's (public/templates/public/public_base.html).
        "icons": [
            {"rel": "icon", "path": "img/favicon.ico", "sizes": "any"},
            {"rel": "apple-touch-icon", "path": "public/img/apple-touch-icon.png"},
        ],
        # A web panel must zoom (WCAG 1.4.4); the Hub's point of sale keeps the fixed scale.
        "user_scalable": True,
    },
    # This repo is its own pnpm workspace (packages/ui is a submodule inside it).
    # With the port Django read (environment or .env): vite.config.ts reads VITE_DEV_PORT from the process
    # environment only, and a Vite on another port than the page's leaves a page that never loads.
    "vite": {
        "command": ["env", f"VITE_DEV_PORT={VITE_DEV_PORT}", "pnpm", "run", "dev"],
        "cwd": str(BASE_DIR),
    },
    # Switched on (RECAPTCHA_ENABLED, off by default), every public form asks Google whether a person sent it
    # (RECAPTCHA_* in accounts.py).
    "recaptcha": {
        "enabled": RECAPTCHA_ENABLED,
        "project": RECAPTCHA_PROJECT,
        "site_key": RECAPTCHA_SITE_KEY,
        "api_key": RECAPTCHA_API_KEY,
        "min_score": RECAPTCHA_MIN_SCORE,
        "endpoint": RECAPTCHA_ENDPOINT,
    },
}
# The apps whose assistant tools all say what a person would type to ask for them (``AI(asks=...)``, live.E020): every
# app with tools (base/tests/test_assistant_asks.py keeps the list whole).
LIVE_ASSISTANT_ASKS_REQUIRED = ("accounts", "apps", "assistant", "billing", "hubs")
