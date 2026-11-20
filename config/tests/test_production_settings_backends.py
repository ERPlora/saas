import pytest
from django.conf import settings
from django.core.cache.backends.redis import RedisCache

from config.tests.production_settings import AWS_ENV, PRODUCTION_ENV, _run, development, production


# Database: TLS verify-full against Aurora with the RDS bundle the image ships.


#: The connection options, the pool's check by name: the `repr` of a function is no literal to read back.
CONNECTION_OPTIONS = (
    "{**s.DATABASES['default']['OPTIONS'], 'pool': {**s.DATABASES['default']['OPTIONS']['pool'],"
    " 'check': s.DATABASES['default']['OPTIONS']['pool']['check'].__qualname__}}"
)
POOL = {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5, "check": "ConnectionPool.check_connection"}


def test_production_verifies_the_database_certificate_against_the_rds_bundle():
    options = production(CONNECTION_OPTIONS, **AWS_ENV)

    assert options["sslmode"] == "verify-full"
    assert options["sslrootcert"] == "/etc/ssl/certs/rds-global-bundle.pem"
    # The task's name in pg_stat_activity (saas, saas-migrate, saas-cron).
    assert options["application_name"] == "saas"
    assert options["pool"] == POOL


def test_without_tls_variables_the_connection_options_are_only_the_pool_and_its_timeouts():
    """Local Postgres (compose.yaml) has no TLS: nothing is added unless the variable is set."""
    only_the_pool = {"pool": POOL, "connect_timeout": 5}
    assert production(CONNECTION_OPTIONS) == only_the_pool
    assert production(CONNECTION_OPTIONS, DB_SSLMODE="", DB_SSLROOTCERT="") == only_the_pool


def test_a_burst_of_pooled_connections_is_given_back_within_minutes():
    """psycopg_pool closes one connection above min_size per max_idle, 600 s by default: after a
    burst the idle SaaS would keep up to 8 connections for over an hour. With 60 s it is back to one
    within 7 minutes; that one stays open for the next request. As in the Hub."""
    pool = production(f"{CONNECTION_OPTIONS}['pool']")
    assert (pool["min_size"], pool["max_size"], pool["max_idle"]) == (1, 8, 60)


@pytest.mark.django_db
def test_the_running_pool_closes_idle_connections_after_60_seconds():
    """Django hands OPTIONS["pool"] to psycopg_pool as is: the pool this process opened has it."""
    from django.db import connection

    connection.ensure_connection()
    assert (connection.pool.min_size, connection.pool.max_idle) == (1, 60)


def test_a_dead_database_fails_within_db_connect_timeout_seconds():
    """psycopg waits 30 s for a connection from the pool and 130 s per connection attempt, so a
    dead database would make /readyz answer 503 after its probes had given up. Both waits are
    DB_CONNECT_TIMEOUT seconds, 5 by default. As in the Hub."""
    timeouts = "(s.DATABASES['default']['OPTIONS']['connect_timeout'], s.DATABASES['default']['OPTIONS']['pool']['timeout'])"
    assert production(timeouts) == (5, 5)
    assert production(timeouts, DB_CONNECT_TIMEOUT="2") == (2, 2)


# Cache: the shared Valkey (TLS, no AUTH) when the infra gives one, local memory otherwise.


def test_production_caches_in_valkey_with_a_prefix_and_a_finite_ttl():
    cache = production("s.CACHES['default']", **AWS_ENV)

    # Django's RedisCache, failing soft: Valkey down is a cache that forgets (base/cache.py).
    assert cache["BACKEND"] == "base.cache.FailSoftRedisCache"
    assert cache["LOCATION"] == AWS_ENV["VALKEY_URL"]
    assert cache["KEY_PREFIX"] == "saas"
    # Valkey Serverless only evicts keys with a TTL: never TIMEOUT=None.
    assert cache.get("TIMEOUT", 300) is not None
    # A Valkey that hangs fails the call quickly instead of the request.
    assert cache["OPTIONS"]["socket_connect_timeout"] <= 2
    assert cache["OPTIONS"]["socket_timeout"] <= 2


def test_without_valkey_the_cache_is_local_memory():
    assert (
        production("s.CACHES['default']['BACKEND']")
        == "django.core.cache.backends.locmem.LocMemCache"
    )
    assert (
        settings.CACHES["default"]["BACKEND"]
        == "django.core.cache.backends.locmem.LocMemCache"
    )


def test_the_valkey_client_library_is_installed():
    """Django's RedisCache imports `redis` on first use: without it the first cached call fails."""
    client = RedisCache("redis://127.0.0.1:1", {})._cache

    assert client._lib.__name__ == "redis"


def test_the_valkey_cache_is_built_from_the_environment():
    """`caches['default']` and its client come up with VALKEY_URL alone; no server is contacted."""
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.cache import caches\n"
        "cache = caches['default']\nprint(type(cache).__name__, cache._cache._lib.__name__)",
        {
            **PRODUCTION_ENV,
            "VALKEY_URL": "redis://localhost:6379/0",
            "DJANGO_SETTINGS_MODULE": "config.settings",
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["FailSoftRedisCache", "redis"]


def test_with_valkey_down_the_rate_limits_let_requests_through():
    """django-ratelimit blocks a request whose count it cannot read unless told to fail open; the
    WAF keeps limiting sign-in, sign-up and passwords per IP meanwhile (ERPlora/aws README, WAF)."""
    assert production("s.RATELIMIT_FAIL_OPEN", **AWS_ENV) is True
    assert development("s.RATELIMIT_FAIL_OPEN") is True


# Logging: one console handler (CloudWatch reads stdout), its level from LOG_LEVEL.


def test_logs_go_to_the_console_at_info_by_default():
    logging = production("s.LOGGING")

    assert logging["handlers"]["console"]["class"] == "logging.StreamHandler"
    assert logging["root"] == {"handlers": ["console"], "level": "INFO"}
    assert logging["loggers"]["django"]["handlers"] == ["console"]


def test_the_log_level_comes_from_the_environment():
    logging = production("s.LOGGING", LOG_LEVEL="WARNING")

    assert logging["root"]["level"] == "WARNING"
    assert logging["loggers"]["django"]["level"] == "WARNING"
