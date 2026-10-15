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
from django.core.exceptions import ImproperlyConfigured
from live.csp import base_policy, debug_policy

BASE_DIR = Path(__file__).resolve().parent.parent

_ENV_FILE = BASE_DIR / ".env"
config = Config(
    RepositoryEnv(str(_ENV_FILE)) if _ENV_FILE.is_file() else RepositoryEmpty()
)

# Which deployment this process is (plan 2026-10-14-entorno-pre): `prod` (erplora.com, also the
# default for development and the tests) or `pre`, the team's pre-production at pre.erplora.com in
# the same cluster, Aurora and Valkey. Outside prod: its own cache prefix, nothing indexed
# (public/seo.py, public/crawlers.py, indexnow_submit) and Stripe in test mode only (billing.E002).
# Any other value refuses to start: a typo must never run as prod or as nothing.
ENVIRONMENTS = ("prod", "pre")
ERPLORA_ENVIRONMENT = config("ERPLORA_ENVIRONMENT", default="prod").strip()
if ERPLORA_ENVIRONMENT not in ENVIRONMENTS:
    raise ImproperlyConfigured(
        f"ERPLORA_ENVIRONMENT must be one of {', '.join(ENVIRONMENTS)}, not {ERPLORA_ENVIRONMENT!r}"
    )

# Off unless the environment turns it on: development sets `DEBUG=True` in saas-next/.env
# (.env.example) and the test run in config/settings_pytest.py.
DEBUG = config("DEBUG", default=False, cast=bool)
# Only local development may fall back to a known key; production refuses to start without one.
SECRET_KEY = (
    config("SECRET_KEY", default="django-insecure-local-only")
    if DEBUG
    else config("SECRET_KEY")
)
# Customers sign in at `erplora.com` (locally `localhost:8001`). No host of a hub is the SaaS's:
# hubs are `<slug>.erplora.com` (locally `a.localhost:8000`) and `hubs.erplora.com` (locally
# `hubs.localhost:8000`) is the Hub's staff admin host, served only by the Hub (ronda 13, PLAN §18).
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1" if DEBUG else "erplora.com",
    cast=Csv(),
)

# HTTPS: the ALB terminates TLS, redirects HTTP to HTTPS and sets X-Forwarded-Proto (daphne
# --proxy-headers reads it as well), so `request.is_secure()` holds behind it. Django does not
# redirect: hub-next calls /internal over plain HTTP on the private name (hub →
# saas.erplora.internal), never through the ALB. Same values as hub-next.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# The visitor's address: the ALB APPENDS it to X-Forwarded-For (what comes before, the client may
# have typed). public.client_ip puts the entry this many hops from the end in REMOTE_ADDR, which the
# rate limits read: 1 in production (the ALB), 0 locally (no proxy, the header is not trusted).
TRUSTED_PROXY_HOPS = config("TRUSTED_PROXY_HOPS", default=0 if DEBUG else 1, cast=int)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
# HSTS on erplora.com. Every subdomain (the hubs, but also whatever else the zone serves) and the
# preload list commit the whole domain and are slow to undo: opt-in by the environment.
SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000, cast=int
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)
# What the platform answers elsewhere: the ALB redirects to HTTPS (W008); HSTS for subdomains and the
# preload list stay opt-in (W005, W021).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W008", "security.W021"]

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
    "django.contrib.sitemaps",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.headless",
    # Always installed, so its table always exists: ACCOUNTS_MFA_ENABLED decides whether it is used.
    "allauth.mfa",
    # The account's active sessions (Cuenta → Seguridad; PLAN-SAAS §6): one row per signed-in browser.
    "allauth.usersessions",
    "ninja",
    "base",
    "accounts",
    # The app catalog (round 16, PLAN §21): before hubs and public, which read it.
    "apps",
    "hubs",
    # The EU VAT engine and, from lot L2-B, Stripe: after hubs, whose payer it reads.
    "billing",
    # The documentation a business sends so ERPlora files its VeriFactu records (plan 2026-10-15): after
    # hubs, whose businesses it reads and whose snapshot carries its outcome.
    "fiscal",
    # The fiscal gateway (PLAN-SAAS §4): presents the Hub's VeriFactu envelopes to the AEAT.
    "fiscal_gateway",
    "public",
    # After `public`: its templates override the package's (public/templates/cookie_consent/).
    "cookie_consent",
]

MIDDLEWARE = [
    # First: answers /healthz before the Host is validated (the ALB probes each task by its IP).
    "base.health.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # The visitor's address behind the ALB in REMOTE_ADDR, before anything reads it.
    "public.client_ip.ClientIpMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    # After Django's: the public web's own policy, set before Django's builds the header.
    "public.csp.PublicCSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # On the panel, a signed-in account speaks its own language (User.language), not the cookie's.
    "base.language.AccountLanguageMiddleware",
    # With ACCOUNTS_MFA_ENABLED off, the 2FA endpoints answer 404 (accounts/mfa.py).
    "accounts.mfa.MFAFlagMiddleware",
    # API 404/405 that never reach a route (unknown path, wrong method) answer the JSON envelope.
    "live.api_errors.ApiErrorEnvelopeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # Records each signed-in session's address, browser and last use (allauth.usersessions), at most once
    # every few minutes: Cuenta → Seguridad → Sesiones activas.
    "accounts.session_tracking.SessionActivityMiddleware",
    # Deletes the cookies of a group that was declined or never accepted (django-cookie-consent),
    # skipping the requests that carry no cookie (public/cookies.py).
    "public.cookies.CleanCookiesMiddleware",
    # `X-Robots-Tag: noindex` on everything that is not the public web (public/crawlers.py).
    "public.crawlers.NoIndexPrivatePathsMiddleware",
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
                # The shell's colour mode (`theme` cookie) for the template pages.
                "base.context_processors.theme",
                "public.context_processors.public_site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database: the `saas` database of the root compose.yaml (Postgres only, also locally). Django's
# native pool, never CONN_MAX_AGE > 0 with it.

# In production every connection verifies Aurora's certificate and host name (DB_SSLMODE=verify-full,
# DB_SSLROOTCERT = the RDS bundle in the image) and names its task (DB_APPLICATION_NAME,
# pg_stat_activity); each option only when set (the local Postgres has no TLS). A dead database
# fails within DB_CONNECT_TIMEOUT seconds, both waiting for a pooled connection and per connection
# attempt (psycopg: 30 s and 130 s), so /readyz answers 503 before its probes give up. As in hub-next.
db_connect_timeout = config("DB_CONNECT_TIMEOUT", default=5, cast=int)
db_optional_options = {
    "DB_SSLMODE": "sslmode",
    "DB_SSLROOTCERT": "sslrootcert",
    "DB_APPLICATION_NAME": "application_name",
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="saas"),
        "USER": config("DB_USER", default="hub"),
        "PASSWORD": config("DB_PASSWORD", default="hub"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
        "OPTIONS": {
            "pool": {"min_size": 1, "max_size": 8, "timeout": db_connect_timeout},
            "connect_timeout": db_connect_timeout,
            **{
                option: value
                for env, option in db_optional_options.items()
                if (value := config(env, default=""))
            },
        },
        # Sessions that run pytest at once against the same Postgres name their own test database.
        "TEST": {"NAME": config("TEST_DB_NAME", default="test_saas_next")},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache: the shared Valkey (TLS, rediss://, no AUTH) when VALKEY_URL is set, so allauth's login rate
# limits and the contact form's hold across tasks; otherwise this process's memory. A prefix per
# project and environment (pre shares prod's Valkey: `pre-saas`) and a TTL on every key (Valkey
# Serverless only evicts keys with one: never TIMEOUT=None).
# A Valkey that hangs fails the call within 2 s instead of holding the request, and a Valkey that is
# down answers as an empty cache instead of a 500 (base/cache.py).

VALKEY_URL = config("VALKEY_URL", default="")
CACHES = {
    "default": (
        {
            "BACKEND": "base.cache.FailSoftRedisCache",
            "LOCATION": VALKEY_URL,
            "KEY_PREFIX": "saas" if ERPLORA_ENVIRONMENT == "prod" else f"{ERPLORA_ENVIRONMENT}-saas",
            "TIMEOUT": 300,
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }
        if VALKEY_URL
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}

# Logging: everything to the console (CloudWatch Logs in production), at LOG_LEVEL. As in hub-next.

LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    # Django's own logger writes once, through the same handler (not also through its DEBUG-only one).
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False}
    },
}

# Accounts: email as the identifier, primary key UUIDv7 (PLAN-SAAS §6).

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
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
# A recent sign-in (allauth's reauthentication) before any change of the account's addresses or of its
# Google link through allauth.headless, as Cuenta's own «Cambiar correo» asks (accounts.email.change).
ACCOUNT_REAUTHENTICATION_REQUIRED = True
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

GOOGLE_OAUTH_CLIENT_ID = (
    config("GOOGLE_OAUTH_CLIENT_ID", default="")
    if DEBUG
    else config("GOOGLE_OAUTH_CLIENT_ID")
)
GOOGLE_OAUTH_CLIENT_SECRET = (
    config("GOOGLE_OAUTH_CLIENT_SECRET", default="")
    if DEBUG
    else config("GOOGLE_OAUTH_CLIENT_SECRET")
)
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)

# Refuses allauth's «connect» process and tells the owner when Google gets linked (saas#2552); an
# unknown Google email meets the closed sign-up.
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "key": "",
        },
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
# Ending a session (Cuenta → Seguridad, or allauth.headless `auth/sessions`) also asks the account's
# businesses to end theirs (accounts.signals.sessions_ended, PLAN-SAAS §2.1).
USERSESSIONS_ADAPTER = "accounts.session_tracking.UserSessionsAdapter"

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
# The secret before a rotation (accounts/signing.py): still accepted, never used to sign. Empty
# outside a rotation.
INTERNAL_SHARED_SECRET_PREVIOUS = config("INTERNAL_SHARED_SECRET_PREVIOUS", default="")
HUB_CALLBACK_TEMPLATE = config(
    "HUB_CALLBACK_TEMPLATE",
    default="http://{slug}.localhost:8000/auth/callback"
    if DEBUG
    else "https://{slug}.erplora.com/auth/callback",
)
# CSP source of every hub's origin (`http://*.localhost:8000`): the auto-submitted form posts there.
_hub_callback = urlsplit(HUB_CALLBACK_TEMPLATE.format(slug="*"))
HUB_ORIGIN_PATTERN = f"{_hub_callback.scheme}://{_hub_callback.netloc}"
# The staff's jump from this admin to the Hub's (audience `hub-admin`, ronda 13, PLAN §18): the
# callback of the platform host `hubs.erplora.com`, which only the Hub serves.
HUB_ADMIN_CALLBACK_URL = config(
    "HUB_ADMIN_CALLBACK_URL",
    default="http://hubs.localhost:8000/auth/callback"
    if DEBUG
    else "https://hubs.erplora.com/auth/callback",
)
_hub_admin_callback = urlsplit(HUB_ADMIN_CALLBACK_URL)
HUB_ADMIN_ORIGIN = f"{_hub_admin_callback.scheme}://{_hub_admin_callback.netloc}"
EXCHANGE_CODE_TTL_SECONDS = 60
INTERNAL_SIGNATURE_MAX_AGE_SECONDS = 300
# Where the SaaS calls hub-next's /internal/* (hubs.hub_client), signed with the same secret: the ALB
# answers 404 to it, so production uses the private name aws-next gives the Hub (Cloud Map).
HUB_INTERNAL_URL = config(
    "HUB_INTERNAL_URL",
    default="http://localhost:8000" if DEBUG else "http://hub.erplora.internal:8000",
)

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
        # A web panel must zoom (WCAG 1.4.4); the Hub's point of sale keeps the fixed scale.
        "user_scalable": True,
    },
    # This repo is its own pnpm workspace (packages/ui is a submodule inside it).
    "vite": {"command": ["pnpm", "run", "dev"], "cwd": str(BASE_DIR)},
}

# Email (allauth's password reset and the «Google was linked» notice, until block 1 brings the
# branded mail): the console locally; in production the SES API signed by the task role (no static
# keys, PLAN-AWS §3), or SMTP from EMAIL_* when SES_REGION is unset. EMAIL_BACKEND overrides the
# choice; the file backend writes into EMAIL_FILE_PATH. Same variables and order as hub-next.

smtp_email_backend = "django.core.mail.backends.smtp.EmailBackend"
ses_email_backend = "django_ses.SESBackend"
file_email_backend = "django.core.mail.backends.filebased.EmailBackend"
if DEBUG:
    default_email_backend = "django.core.mail.backends.console.EmailBackend"
else:
    default_email_backend = (
        ses_email_backend if config("SES_REGION", default="") else smtp_email_backend
    )
email_backend = config("EMAIL_BACKEND", default=default_email_backend)
MAILERS = {"default": {"BACKEND": email_backend}}
if email_backend == ses_email_backend:
    AWS_SES_REGION_NAME = config("SES_REGION")
    AWS_SES_REGION_ENDPOINT = f"email.{AWS_SES_REGION_NAME}.amazonaws.com"
    # The throttle first calls ses:GetSendQuota, which the task role may not (only
    # SendEmail/SendRawEmail).
    AWS_SES_AUTO_THROTTLE = None
elif email_backend == smtp_email_backend:
    MAILERS["default"]["OPTIONS"] = {
        "host": config("EMAIL_HOST", default="localhost"),
        "port": config("EMAIL_PORT", default=587, cast=int),
        "username": config("EMAIL_HOST_USER", default=""),
        "password": config("EMAIL_HOST_PASSWORD", default=""),
        "use_tls": config("EMAIL_USE_TLS", default=True, cast=bool),
        "timeout": 10,
    }
elif email_backend == file_email_backend:
    # The panel's e2e reads the mails from this folder (tests/e2e/panel/project.ts).
    MAILERS["default"]["OPTIONS"] = {"file_path": config("EMAIL_FILE_PATH")}
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@erplora.com")

# The public web of erplora.com (round 16, `public/`): Django templates for SEO, its own CSP
# (public/csp.py), crawlers, cookie consent, IndexNow and the app downloads.

# The Hub serves the apps' documentation images (spec decision 10): the SaaS rewrites their paths
# to this base and the public CSP adds its origin to `img-src`. Only for that.
HUB_STATIC_BASE_URL = config(
    "HUB_STATIC_BASE_URL",
    default="http://hubs.localhost:8000/static/"
    if DEBUG
    else "https://hubs.erplora.com/static/",
)

# Google Analytics 4 and Microsoft Clarity, loaded only after the analytical consent and never on a
# page that shows credentials. Empty by default: production sets them, local stays out.
GA_MEASUREMENT_ID = config("GA_MEASUREMENT_ID", default="")
CLARITY_PROJECT_ID = config("CLARITY_PROJECT_ID", default="")

# django-cookie-consent (GDPR): its groups are seeded by `init_cookie_groups`.
COOKIE_CONSENT_NAME = "cookie_consent"
COOKIE_CONSENT_MAX_AGE = 60 * 60 * 24 * 365  # 1 year
COOKIE_CONSENT_SECURE = not DEBUG

# Messages of the contact form per address (django-ratelimit, over the default cache).
CONTACT_FORM_RATELIMIT = config("CONTACT_FORM_RATELIMIT", default="10/h")
# With Valkey down the per-IP limits of the app cannot count, and they let requests through instead
# of refusing everyone. The ALB's WAF keeps limiting sign-in, sign-up, password, Google and the
# headless API per IP meanwhile (aws-next/README.md, WAF of `stacks/shared`); the contact form has
# no WAF limit, so for that while it lasts only the app's fail-open applies.
RATELIMIT_FAIL_OPEN = True

# IndexNow pushes the public URLs to Bing (and so to ChatGPT search) the day they change. The key
# is public by design (served at `/<key>.txt`, where the search engine checks we own the domain),
# so it ships with the code; the environment may replace it. PUBLIC_HOST is the host of the URLs
# submitted: IndexNow rejects the whole batch if one URL is on another host.
INDEXNOW_KEY = config(
    "INDEXNOW_KEY", default="1e00b99c5f72af2baaba3e383f91725b"
).strip()
PUBLIC_HOST = config("PUBLIC_HOST", default="erplora.com").strip()

# The legal terms promise the exit package of a deleted hub for this many days: a written promise
# to the customer, so it is read here and never quietly lowered.
HUB_EXIT_PACKAGE_TTL_DAYS = config("HUB_EXIT_PACKAGE_TTL_DAYS", default=90, cast=int)

# The installable app (`/app/`): its installers live in a private S3 bucket on AWS (Ireland region,
# PLAN-AWS «s3_downloads.tf»), served by short presigned links; `latest/`, never a version, so a
# cached link keeps delivering the last build. No keys here: boto3 takes the ECS task's role (or
# the environment in development); DOWNLOADS_ENDPOINT_URL is only for local development (empty =
# AWS). The stores win when their listing exists: Microsoft Store by its Store ID (assigned by
# Microsoft), Google Play by the package (an override of `com.erplora.app`, never a switch to the
# APK) while its listing is live.
DOWNLOADS_BUCKET = config("DOWNLOADS_BUCKET", default="erplora-saas")
DOWNLOADS_REGION = config("DOWNLOADS_REGION", default="eu-west-1")
DOWNLOADS_ENDPOINT_URL = config("DOWNLOADS_ENDPOINT_URL", default="")
APP_DOWNLOAD_PREFIX = config("APP_DOWNLOAD_PREFIX", default="downloads/app/latest")
DOWNLOAD_URL_TTL = config("DOWNLOAD_URL_TTL", default=300, cast=int)  # seconds
MICROSOFT_STORE_APP_ID = config("MICROSOFT_STORE_APP_ID", default="")
GOOGLE_PLAY_APP_ID = config("GOOGLE_PLAY_APP_ID", default="")
GOOGLE_PLAY_LISTING_LIVE = config("GOOGLE_PLAY_LISTING_LIVE", default=True, cast=bool)

# AWS: the region of the platform, Ireland (PLAN-AWS round 2026-10-14; ECS sets AWS_REGION in every
# task), where `report_seal_expiry` publishes to CloudWatch with the task role (no static keys).
AWS_REGION = config("AWS_REGION", default="eu-west-1")

# The fiscal seal's two .p12 slots (erplora/prod/fiscal/seal-{current,next}), base64 and password,
# loaded at startup by `saas` and `saas-cron` (PLAN §16.5); empty = an empty slot (they are born
# empty and filled by hand; `saas-migrate` gets none). `manage.py report_seal_expiry` publishes the
# days left of the one that expires first.
FISCAL_SEAL_CURRENT_P12_BASE64 = config("FISCAL_SEAL_CURRENT_P12_BASE64", default="")
FISCAL_SEAL_CURRENT_PASSWORD = config("FISCAL_SEAL_CURRENT_PASSWORD", default="")
FISCAL_SEAL_NEXT_P12_BASE64 = config("FISCAL_SEAL_NEXT_P12_BASE64", default="")
FISCAL_SEAL_NEXT_PASSWORD = config("FISCAL_SEAL_NEXT_PASSWORD", default="")
# The fiscal gateway (fiscal_gateway/, PLAN-SAAS §4): presentations to the AEAT under way at once in
# one process; one more answers 503 `gateway_busy` and the Hub retries. 8 until it is measured in pre.
VERIFACTU_GATEWAY_CONCURRENCY = config("VERIFACTU_GATEWAY_CONCURRENCY", default=8, cast=int)

# The documentation a hub sends so ERPlora files its VeriFactu records (fiscal/, plan 2026-10-15): the
# signed Anexo I, a copy of the signer's identity document and the rest, encrypted at rest with this Fernet
# key (fiscal/crypto.py; `check` says if it is no Fernet key, fiscal.E001). Required in production, like
# INTERNAL_SHARED_SECRET: a document stored with a lost key is lost. Local development uses a fixed key.
FISCAL_DOCUMENTS_KEY = (
    config("FISCAL_DOCUMENTS_KEY", default="bG9jYWwtZmlzY2FsLWRvY3VtZW50cy1rZXktMzJieXQ=")
    if DEBUG
    else config("FISCAL_DOCUMENTS_KEY")
)
# DATA_UPLOAD_MAX_MEMORY_SIZE stays Django's 2.5 MB for every view: the four documents of an authorisation
# (up to about 27 MB) have their own ceiling, read by their view alone (fiscal.internal.MAX_BODY_BYTES).

# EU VAT (billing/): VIES, the European Commission's register of VAT numbers, asked through its REST
# endpoint as an identified requester (ERPlora's own VAT number, billing.CompanyConfig), the only way
# its answer carries the consultation number that proves it (billing/vies.py). Short timeout: a person
# waits for it (the forms, the checkout); a slow VIES is `unavailable`, and the sale pays VAT.
VIES_ENDPOINT = config(
    "VIES_ENDPOINT",
    default="https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number",
)
VIES_CONNECT_TIMEOUT_SECONDS = config("VIES_CONNECT_TIMEOUT_SECONDS", default=3.0, cast=float)
VIES_TIMEOUT_SECONDS = config("VIES_TIMEOUT_SECONDS", default=5.0, cast=float)
# One budget per person for every door that spends a VIES query (the panel's check, the admin's
# «Check now in VIES»), and one for everybody: each one is a request to the Commission under
# ERPlora's requester number. Only a query really sent spends.
VAT_CHECK_RATE = config("VAT_CHECK_RATE", default="20/m")
VAT_CHECK_GLOBAL_RATE = config("VAT_CHECK_GLOBAL_RATE", default="60/m")

# Stripe (billing/, lot L2-B; PLAN-SAAS §4). Production holds a RESTRICTED live key (`rk_live_…`), local
# development test keys only; never a key in code. Without a secret key no payment starts (503
# `billing.payments_unavailable`) and the webhook answers 503. STRIPE_WEBHOOK_SECRET is the `whsec_…` of
# the one endpoint, `/webhooks/stripe/`; the publishable key travels to the SPA with each checkout. A
# call to Stripe waits STRIPE_TIMEOUT_SECONDS at most and is retried once (a command holds its
# transaction open meanwhile; Aurora ends one idle for 30 s). Prices: the Stripe ids on each Plan (admin)
# and apps.Module.
STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = config("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")
STRIPE_TIMEOUT_SECONDS = config("STRIPE_TIMEOUT_SECONDS", default=10.0, cast=float)
# The Customer Portal's configuration (`bpc_…`): cards and receipts only; plan changes go through the panel,
# which puts our TaxRates. Empty = the portal does not open (503 `billing.portal_unavailable`).
STRIPE_PORTAL_CONFIGURATION = config("STRIPE_PORTAL_CONFIGURATION", default="")
# ERPlora's invoices are issued by its platform hub (billing, lot L3-C): a live key charges nothing until this
# says the route is wired AND the Hub answers `GET /internal/platform/invoices/health` (working rules §15).
PLATFORM_INVOICING_ENABLED = config("PLATFORM_INVOICING_ENABLED", default=False, cast=bool)
# Promo codes grant trial days (ADR-0107): a person may ask whether one is valid this often, so the codes
# cannot be guessed by brute force.
PROMO_CHECK_RATE = config("PROMO_CHECK_RATE", default="20/m")
