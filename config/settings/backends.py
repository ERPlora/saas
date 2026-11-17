from psycopg_pool import ConnectionPool

from config.settings.core import CACHE_KEY_PREFIX, config

# Database: the `saas` database of the root compose.yaml (Postgres only, also locally). Django's
# native pool, never CONN_MAX_AGE > 0 with it.

# In production every connection verifies Aurora's certificate and host name (DB_SSLMODE=verify-full,
# DB_SSLROOTCERT = the RDS bundle in the image) and names its task (DB_APPLICATION_NAME,
# pg_stat_activity); each option only when set (the local Postgres has no TLS). A dead database
# fails within DB_CONNECT_TIMEOUT seconds, both waiting for a pooled connection and per connection
# attempt (psycopg: 30 s and 130 s), so /readyz answers 503 before its probes give up. As in the Hub.
# The pool keeps one connection and gives back the rest of a burst one per minute (max_idle;
# psycopg's default of 600 s holds them for over an hour).
# It checks a connection before handing it out: after a cut of the database it may hold a dead one.
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
            "pool": {
                "min_size": 1,
                "max_size": 8,
                "max_idle": 60,
                "timeout": db_connect_timeout,
                "check": ConnectionPool.check_connection,
            },
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
            "KEY_PREFIX": CACHE_KEY_PREFIX,
            "TIMEOUT": 300,
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }
        if VALKEY_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "KEY_PREFIX": CACHE_KEY_PREFIX,
        }
    )
}

# Logging: everything to the console (CloudWatch Logs in production), at LOG_LEVEL. As in the Hub. Every line goes
# through base.logging.GDPRSafeFormatter: an address, a phone, an id number, a card, a key or a password logged by
# mistake reaches the log as a label, never as written; no filter drops a record.

LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {
            "()": "base.logging.GDPRSafeFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    # Django's own logger writes once, through the same handler (not also through its DEBUG-only one).
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # httpx logs every request's full address at INFO: Meta's token exchange carries the app's secret in it
        # (whatsapp/meta.py), so only its warnings get through.
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}
