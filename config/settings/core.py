from pathlib import Path

from decouple import Config, Csv, RepositoryEmpty, RepositoryEnv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]

_ENV_FILE = BASE_DIR / ".env"
config = Config(
    RepositoryEnv(str(_ENV_FILE)) if _ENV_FILE.is_file() else RepositoryEmpty()
)

# Deployment label for the CertificatesAttached CloudWatch metric, not application policy.
# The existing alarm matches Environment=prod; retain its contract and reject unknown labels.
ENVIRONMENTS = ("prod", "pre")
ERPLORA_ENVIRONMENT = config("ERPLORA_ENVIRONMENT", default="prod").strip()
if ERPLORA_ENVIRONMENT not in ENVIRONMENTS:
    raise ImproperlyConfigured(
        f"ERPLORA_ENVIRONMENT must be one of {', '.join(ENVIRONMENTS)}, not {ERPLORA_ENVIRONMENT!r}"
    )

# Off unless the environment turns it on: development sets `DEBUG=True` in this repo's .env
# (.env.example) and the test run in config/settings_pytest.py.
DEBUG = config("DEBUG", default=False, cast=bool)

CACHE_KEY_PREFIX = config("CACHE_KEY_PREFIX", default="local-saas" if DEBUG else "").strip()
if not CACHE_KEY_PREFIX:
    raise ImproperlyConfigured("CACHE_KEY_PREFIX must be explicitly configured outside DEBUG.")
STRIPE_EXPECTED_MODE = config("STRIPE_EXPECTED_MODE", default="test" if DEBUG else "").strip()
if STRIPE_EXPECTED_MODE not in ("test", "live"):
    raise ImproperlyConfigured("STRIPE_EXPECTED_MODE must be explicitly set to test or live.")


def _policy_boolean(name):
    try:
        return config(name, default=False, cast=bool)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a boolean.") from exc


PUBLIC_INDEXING_ENABLED = _policy_boolean("PUBLIC_INDEXING_ENABLED")
AEAT_PRODUCTION_ENABLED = _policy_boolean("AEAT_PRODUCTION_ENABLED")

# Only local development may fall back to a known key; production refuses to start without one.
SECRET_KEY = (
    config("SECRET_KEY", default="django-insecure-local-only")
    if DEBUG
    else config("SECRET_KEY")
)
# Customers sign in at `erplora.com` (locally `localhost:8001`). No host of a hub is the SaaS's:
# hubs are `<slug>.erplora.com` (locally `a.localhost:8000`) and `hubs.erplora.com` (locally
# `hubs.localhost:8000`) is the Hub's staff admin host, served only by the Hub.
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1" if DEBUG else "erplora.com",
    cast=Csv(),
)

# HTTPS: the ALB terminates TLS, redirects HTTP to HTTPS and sets X-Forwarded-Proto (daphne
# --proxy-headers reads it as well), so `request.is_secure()` holds behind it. Django does not
# redirect: the Hub calls /internal over plain HTTP on the private name (hub →
# saas.erplora.internal), never through the ALB. Same values as the Hub.
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

# Vite's dev server (`vite.config.ts` reads the same VITE_DEV_PORT): 5174, since the Hub's owns 5173 and
# both run at once in development, unless a second checkout runs beside another one (the e2e of a branch,
# README «Dos SaaS a la vez»). `runserver` hands the port it read to the Vite it starts (LIVE["vite"]);
# `pnpm run dev` or the e2e on their own read the process environment only, not this repo's .env.
_vite_dev_port = config("VITE_DEV_PORT", default="5174")
VITE_DEV_PORT = int(_vite_dev_port) if _vite_dev_port.isdecimal() else 0
if not 0 < VITE_DEV_PORT < 65536:
    raise ImproperlyConfigured(
        f"VITE_DEV_PORT must be a TCP port, not {_vite_dev_port!r}."
    )
VITE_DEV_SERVER = f"http://localhost:{VITE_DEV_PORT}"
