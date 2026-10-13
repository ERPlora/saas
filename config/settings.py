"""Django settings of saas-next (phase 1: sign-in, the jump to a hub and the Ionic Vue SPA, PLAN-SAAS §2.1,
§3.1, §6).

Configuration comes from the process environment or ``saas-next/.env`` through python-decouple,
never from a ``.env`` further up the tree: the root one belongs to hub-next (its ``DB_NAME`` is
``hub``; saas#2416). ``DEBUG`` is off by default: production must provide ``SECRET_KEY``,
``INTERNAL_SHARED_SECRET``, ``GOOGLE_OAUTH_CLIENT_ID`` and ``GOOGLE_OAUTH_CLIENT_SECRET``; local
development sets ``DEBUG=True`` (``.env.example``) and gets defaults for the root ``compose.yaml``.
"""

from pathlib import Path
from urllib.parse import urlsplit

from decouple import Config, Csv, RepositoryEmpty, RepositoryEnv
from live.csp import base_policy, debug_policy

BASE_DIR = Path(__file__).resolve().parent.parent

_ENV_FILE = BASE_DIR / ".env"
config = Config(RepositoryEnv(str(_ENV_FILE)) if _ENV_FILE.is_file() else RepositoryEmpty())

# Off unless the environment turns it on: development sets `DEBUG=True` in saas-next/.env
# (.env.example) and the test run in config/settings_pytest.py.
DEBUG = config("DEBUG", default=False, cast=bool)
# Only local development may fall back to a known key; production refuses to start without one.
SECRET_KEY = config("SECRET_KEY", default="django-insecure-local-only") if DEBUG else config("SECRET_KEY")
# Customers sign in at `erplora.com` (locally `localhost:8001`). No host of a hub is the SaaS's:
# hubs are `<slug>.erplora.com` (locally `a.localhost:8000`) and `hubs.erplora.com` (locally
# `hubs.localhost:8000`) is the Hub's staff admin host, served only by the Hub (ronda 13, PLAN §18).
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1" if DEBUG else "erplora.com",
    cast=Csv(),
)

# Its own port: hub-next's Vite owns 5173 and both run at once in development.
VITE_DEV_SERVER = "http://localhost:5174"

# Application definition

INSTALLED_APPS = [
    # Before daphne: its runserver (daphne + Vite, `--novite` skips Vite) must win.
    "live",
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.headless",
    # Always installed, so its table always exists: ACCOUNTS_MFA_ENABLED decides whether it is used.
    "allauth.mfa",
    "ninja",
    "base",
    "accounts",
]

MIDDLEWARE = [
    # First: answers /healthz before the Host is validated (the ALB probes each task by its IP).
    "base.health.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # With ACCOUNTS_MFA_ENABLED off, the 2FA endpoints answer 404 (accounts/mfa.py).
    "accounts.mfa.MFAFlagMiddleware",
    # API 404/405 that never reach a route (unknown path, wrong method) answer the JSON envelope.
    "live.api_errors.ApiErrorEnvelopeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.google_login",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database: the `saas` database of the root compose.yaml (Postgres only, also locally). Django's
# native pool, never CONN_MAX_AGE > 0 with it.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="saas"),
        "USER": config("DB_USER", default="hub"),
        "PASSWORD": config("DB_PASSWORD", default="hub"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
        "OPTIONS": {"pool": {"min_size": 1, "max_size": 8}},
        "TEST": {"NAME": "test_saas_next"},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Accounts: email as the identifier, primary key UUIDv7 (PLAN-SAAS §6).

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# allauth: email + password and Google, the second factor behind ACCOUNTS_MFA_ENABLED (below); no
# signup yet (see README.md).

SITE_ID = 1
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "none"
# The «Keep me signed in» box of the login decides (same as today's SaaS).
ACCOUNT_SESSION_REMEMBER = None
ACCOUNT_LOGOUT_REDIRECT_URL = "/accounts/login/"
LOGIN_URL = "/accounts/login/"
# The Vue launcher (accounts/frontend/pages/LaunchPage.vue).
LOGIN_REDIRECT_URL = "/launch"
# Absolute links allauth builds (Google's redirect_uri): behind the load balancer the request
# arrives as http, and Google only accepts the https callback registered with it.
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http" if DEBUG else "https"
# Where an account holder writes when a mail says something they did not do.
SUPPORT_EMAIL = config("SUPPORT_EMAIL", default="support@erplora.com")

# «Continue with Google» (allauth.socialaccount), ported from ERPlora/saas (ADR-0154). Credentials
# come from the environment only (no `SocialApp` row). Local development may go without them: the
# button is hidden and `check` says so (accounts.I001). Production refuses to start without them.
# Redirect URIs registered with Google: `<origin>/auth/google/callback/` (README.md).

GOOGLE_OAUTH_CLIENT_ID = config("GOOGLE_OAUTH_CLIENT_ID", default="") if DEBUG else config("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_OAUTH_CLIENT_SECRET = (
    config("GOOGLE_OAUTH_CLIENT_SECRET", default="") if DEBUG else config("GOOGLE_OAUTH_CLIENT_SECRET")
)
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)

# Refuses allauth's «connect» process and tells the owner when Google gets linked (saas#2552); an
# unknown Google email meets the closed sign-up.
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {"client_id": GOOGLE_OAUTH_CLIENT_ID, "secret": GOOGLE_OAUTH_CLIENT_SECRET, "key": ""},
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
        # No "VERIFIED_EMAIL": Google's own `email_verified` claim decides whether the address is
        # proven. Today's SaaS forces True, which only matters when Google says the address is
        # NOT verified, the one case in which signing in by email must not happen.
    }
}
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
# Only reached when the sign-up opens: today it is closed and an unknown email gets no account.
SOCIALACCOUNT_AUTO_SIGNUP = True
# A Google that proves an account's email signs in to it and is linked to it (as today's SaaS):
# allauth only does it for an address Google verified, the guard against account takeover.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
# Only a POST (the button posts) starts the round trip, never a bare GET (login CSRF).
SOCIALACCOUNT_LOGIN_ON_GET = False
# Sign-in only: no Google API is called afterwards.
SOCIALACCOUNT_STORE_TOKENS = False

# Second factor (allauth.mfa): an authenticator app (TOTP) and recovery codes, as today's SaaS; no
# passkeys and no «trust this browser». Off by default in phase 1: with ACCOUNTS_MFA_ENABLED=False no
# login asks for a code and the 2FA endpoints answer 404 (accounts/mfa.py); turned on, an
# account with an authenticator app is asked for its code after the first factor and the staff's
# jump to the Hub admin (`hub-admin`) needs it (README.md, «Segundo factor (2FA)»).

ACCOUNTS_MFA_ENABLED = config("ACCOUNTS_MFA_ENABLED", default=False, cast=bool)
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "ERPlora"
# Accept ±1 period (30 s) of clock drift between the phone and the server, as today's SaaS.
MFA_TOTP_TOLERANCE = 1
MFA_PASSKEY_LOGIN_ENABLED = False
MFA_ADAPTER = "accounts.mfa.MFAAdapter"

# allauth.headless (ronda 11): the API of the Ionic Vue account pages, browser client only (same-origin
# session cookie + Django's CSRF), mounted at /_allauth/. The template pages stay while the Vue ones
# are built page by page; HEADLESS_ONLY turns True when the last one exists.
HEADLESS_ONLY = False
HEADLESS_CLIENTS = ("browser",)
# The links allauth mails point here even with HEADLESS_ONLY off, so a key enters only with its Vue
# page: account_signup → /signup, account_reset_password → /password/reset,
# account_reset_password_from_key → /password/reset/key/{key}, account_confirm_email →
# /verify-email/{key}. Not socialaccount_login_error: allauth reads it only for a HEADLESS Google
# flow, and «Continue with Google» is a plain form post (a browser flow), whose errors the
# SocialAccountAdapter sends to the Vue page /login/error itself.
HEADLESS_FRONTEND_URLS: dict[str, str] = {}
# openapi.yaml/.json of the headless API in development; not its HTML page (Redoc from a CDN).
HEADLESS_SERVE_SPECIFICATION = DEBUG
HEADLESS_SPECIFICATION_TEMPLATE_NAME = None

# Jump to a hub with a one-time code (PLAN-SAAS §2.1, §3.1 steps 4-6).

# hub-next signs POST /internal/auth/redeem with this secret (HMAC-SHA256 + timestamp).
INTERNAL_SHARED_SECRET = (
    config("INTERNAL_SHARED_SECRET", default="local-internal-shared-secret")
    if DEBUG
    else config("INTERNAL_SHARED_SECRET")
)
HUB_CALLBACK_TEMPLATE = config(
    "HUB_CALLBACK_TEMPLATE",
    default="http://{slug}.localhost:8000/auth/callback" if DEBUG else "https://{slug}.erplora.com/auth/callback",
)
# CSP source of every hub's origin (`http://*.localhost:8000`): the auto-submitted form posts there.
_hub_callback = urlsplit(HUB_CALLBACK_TEMPLATE.format(slug="*"))
HUB_ORIGIN_PATTERN = f"{_hub_callback.scheme}://{_hub_callback.netloc}"
# The staff's jump from this admin to the Hub's (audience `hub-admin`, ronda 13, PLAN §18): the
# callback of the platform host `hubs.erplora.com`, which only the Hub serves.
HUB_ADMIN_CALLBACK_URL = config(
    "HUB_ADMIN_CALLBACK_URL",
    default="http://hubs.localhost:8000/auth/callback" if DEBUG else "https://hubs.erplora.com/auth/callback",
)
_hub_admin_callback = urlsplit(HUB_ADMIN_CALLBACK_URL)
HUB_ADMIN_ORIGIN = f"{_hub_admin_callback.scheme}://{_hub_admin_callback.netloc}"
EXCHANGE_CODE_TTL_SECONDS = 60
INTERNAL_SIGNATURE_MAX_AGE_SECONDS = 300

# Internationalization: English is the source, Spanish the translation.

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("es", "Español")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

# Content Security Policy (Django's native middleware, nonce per response; packages/live).
# `form-action` filters the whole redirect chain of a form post: «Continue with Google» posts to
# /auth/google/login/, which answers 302 to accounts.google.com (saas#945), the hub-login page
# posts its form to the hub's origin and the admin's «Open in the Hub admin» to the platform host
# (named on its own: `HUB_ADMIN_CALLBACK_URL` may live outside the hubs' pattern). Google adds no
# script, frame nor connection source.

SECURE_CSP = debug_policy(VITE_DEV_SERVER) if DEBUG else base_policy()
SECURE_CSP["form-action"] = [
    *SECURE_CSP["form-action"],
    "https://accounts.google.com",
    HUB_ORIGIN_PATTERN,
    HUB_ADMIN_ORIGIN,
]
# The Iconify web component creates its own Trusted Types policy (as in today's SaaS).
SECURE_CSP["trusted-types"] = [*SECURE_CSP["trusted-types"], "iconify"]

# Static files: WhiteNoise. The template pages' Ionic, Iconify and fonts are vendored under
# static/vendor/ (nothing from a CDN). Vite already hashes the SPA build, served under /static/spa/
# (Vite's `base`), so no Manifest storage and its hashed assets are immutable.

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
SPA_DIST = BASE_DIR / "frontend" / "dist"
STATICFILES_DIRS = [BASE_DIR / "static", *([("spa", SPA_DIST)] if SPA_DIST.is_dir() else [])]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_IMMUTABLE_FILE_TEST = r"^/static/spa/assets/"

# Operations, live queries and the SPA (packages/live). The scope of an operation is the user.

LIVE = {
    "context_builder": "base.operations.UserContextBuilder",
    "control_alias": "default",
    # Shortest hub slug (live.slugs, shared with hub-next): 3 in production; development opens
    # one-letter slugs for the demo hubs `a` and `b` (`demo_seed`).
    "hub_slug_min_length": 1 if DEBUG else 3,
    "spa": {
        "entry": "frontend/main.ts",
        "manifest": SPA_DIST / ".vite" / "manifest.json",
        "dev_server": VITE_DEV_SERVER if DEBUG else None,
        "palette_default": "erplora",
        "palettes": ["erplora"],
        "title": "ERPlora Cloud",
    },
    # This repo is its own pnpm workspace (packages/ui is a submodule inside it).
    "vite": {"command": ["pnpm", "run", "dev"], "cwd": str(BASE_DIR)},
}

# Email (allauth's password reset and the «Google was linked» notice, until block 1 brings the
# branded mail).

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}
