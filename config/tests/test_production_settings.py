"""Production settings of saas-next, as ECS starts them (aws README, «Contrato app ↔ infra»).

``config.settings`` is evaluated once per process from the environment, so every production value
is read in a fresh interpreter. That interpreter never reads ``saas-next/.env`` (a developer's
``DEBUG=True`` would leak in) and starts from an almost empty environment: only what each test
passes, on top of the variables production must provide, reaches the settings.
"""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.cache.backends.redis import RedisCache
from django.test import RequestFactory

SAAS_NEXT = Path(__file__).resolve().parents[2]
# What the task definition and Secrets Manager give every saas* task (aws-next/stacks/prod/apps.tf),
# with dummies for the secrets. The key is long and varied enough for `check --deploy` (W009).
PRODUCTION_ENV = {
    "DEBUG": "False",
    "SECRET_KEY": "a-long-production-secret-key-with-enough-variety-0123456789-abcdefghij",
    "INTERNAL_SHARED_SECRET": "a-production-internal-secret",
    "GOOGLE_OAUTH_CLIENT_ID": "prod-client.apps.googleusercontent.com",
    "GOOGLE_OAUTH_CLIENT_SECRET": "prod-secret",
    "ALLOWED_HOSTS": "erplora.com,saas.erplora.internal",
}
# The infra's own values for the hardening variables (`base_env` and `saas_env` of apps.tf).
AWS_ENV = {
    "DB_SSLMODE": "verify-full",
    "DB_SSLROOTCERT": "/etc/ssl/certs/rds-global-bundle.pem",
    "DB_APPLICATION_NAME": "saas",
    "VALKEY_URL": "rediss://erplora-prod.serverless.euw.cache.amazonaws.com:6379",
    "SES_REGION": "eu-west-1",
    "DEFAULT_FROM_EMAIL": "noreply@erplora.com",
}
# The fresh interpreter ignores saas-next/.env: decouple's file repository is swapped for an empty
# one before config.settings builds its Config.
IGNORE_DOTENV = "import decouple; decouple.RepositoryEnv = lambda *args, **kwargs: decouple.RepositoryEmpty()"


def _run(code: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    minimal = {
        key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ
    }
    return subprocess.run(
        [sys.executable, "-c", f"{IGNORE_DOTENV}\n{code}"],
        cwd=SAAS_NEXT,
        env={**minimal, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def _settings(expression: str, env: dict[str, str]):
    result = _run(f"import config.settings as s\nprint(repr({expression}))", env)
    assert result.returncode == 0, result.stderr
    return ast.literal_eval(result.stdout.strip())


def production(expression: str, **env: str):
    """The value of ``expression`` (``s`` = ``config.settings``) with the production environment."""
    return _settings(expression, {**PRODUCTION_ENV, **env})


def development(expression: str, **env: str):
    """The same with ``DEBUG=True`` alone, as saas-next/.env (.env.example) runs it. The test run
    swaps some values (the mailers, for one), so development is read in a fresh process too."""
    return _settings(expression, {"DEBUG": "True", **env})


# Database: TLS verify-full against Aurora with the RDS bundle the image ships.


def test_production_verifies_the_database_certificate_against_the_rds_bundle():
    options = production("s.DATABASES['default']['OPTIONS']", **AWS_ENV)

    assert options["sslmode"] == "verify-full"
    assert options["sslrootcert"] == "/etc/ssl/certs/rds-global-bundle.pem"
    # The task's name in pg_stat_activity (saas, saas-migrate, saas-cron).
    assert options["application_name"] == "saas"
    assert options["pool"] == {"min_size": 1, "max_size": 8, "timeout": 5}


def test_without_tls_variables_the_connection_options_are_only_the_pool_and_its_timeouts():
    """Local Postgres (compose.yaml) has no TLS: nothing is added unless the variable is set."""
    only_the_pool = {
        "pool": {"min_size": 1, "max_size": 8, "timeout": 5},
        "connect_timeout": 5,
    }
    assert production("s.DATABASES['default']['OPTIONS']") == only_the_pool
    assert (
        production("s.DATABASES['default']['OPTIONS']", DB_SSLMODE="", DB_SSLROOTCERT="")
        == only_the_pool
    )


def test_a_dead_database_fails_within_db_connect_timeout_seconds():
    """psycopg waits 30 s for a connection from the pool and 130 s per connection attempt, so a
    dead database made /readyz answer 503 after its probes had given up. Both waits are
    DB_CONNECT_TIMEOUT seconds, 5 by default. As in hub-next."""
    timeouts = "(s.DATABASES['default']['OPTIONS']['connect_timeout'], s.DATABASES['default']['OPTIONS']['pool']['timeout'])"
    assert production(timeouts) == (5, 5)
    assert production(timeouts, DB_CONNECT_TIMEOUT="2") == (2, 2)


# HTTPS behind the ALB: it terminates TLS, redirects plain HTTP to HTTPS and forwards the request
# to daphne with X-Forwarded-Proto. Same values as hub-next.

PRODUCTION_SECURITY = (
    "(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT, s.SECURE_PROXY_SSL_HEADER,"
    " s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SECURE_HSTS_PRELOAD)"
)


def test_production_cookies_are_secure_and_browsers_are_told_to_stay_on_https():
    assert production(PRODUCTION_SECURITY) == (
        True,
        True,
        # The ALB redirects; Django must not, or hub-next's /internal calls over plain HTTP break.
        False,
        ("HTTP_X_FORWARDED_PROTO", "https"),
        31536000,
        # Every subdomain and the preload list commit the whole domain and are slow to undo: opt-in.
        False,
        False,
    )


def test_hsts_for_subdomains_and_preload_are_opt_in():
    assert production(
        "(s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SECURE_HSTS_PRELOAD)",
        SECURE_HSTS_SECONDS="63072000",
        SECURE_HSTS_INCLUDE_SUBDOMAINS="True",
        SECURE_HSTS_PRELOAD="True",
    ) == (63072000, True, True)


def test_development_stays_on_plain_http():
    assert development(
        "(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS)"
    ) == (False, False, False, 0)


def test_a_request_the_alb_received_over_https_is_secure():
    """CSRF's origin check, the secure cookies and absolute URLs rely on it (the same in every mode)."""
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="https").is_secure()
    assert not RequestFactory().get("/").is_secure()


# The visitor's address: the ALB appends it to X-Forwarded-For (public/client_ip.py).


def test_production_trusts_the_alb_as_its_one_proxy():
    assert production("s.TRUSTED_PROXY_HOPS", **AWS_ENV) == 1


def test_development_trusts_no_proxy():
    """runserver has nobody in front: a forged X-Forwarded-For must not choose the address."""
    assert development("s.TRUSTED_PROXY_HOPS") == 0
    assert settings.TRUSTED_PROXY_HOPS == 0


def test_the_proxy_hops_come_from_the_environment():
    assert production("s.TRUSTED_PROXY_HOPS", TRUSTED_PROXY_HOPS="2") == 2
    assert development("s.TRUSTED_PROXY_HOPS", TRUSTED_PROXY_HOPS="1") == 1


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
    WAF keeps limiting sign-in, sign-up and passwords per IP meanwhile (aws-next README, WAF)."""
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


# Email: the console in development; in production the SES API signed by the task role when ECS
# passes SES_REGION, SMTP configured by the environment otherwise, or any backend EMAIL_BACKEND
# names. Same variables and order as hub-next.

SMTP = "django.core.mail.backends.smtp.EmailBackend"
SES = "django_ses.SESBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"


def test_development_prints_mail_to_the_console():
    assert development("s.MAILERS['default']") == {"BACKEND": CONSOLE}
    # Even with production's SES region in the environment, DEBUG never sends real mail.
    assert development("s.MAILERS['default']", SES_REGION="eu-west-1") == {
        "BACKEND": CONSOLE
    }


def test_production_mail_goes_through_the_ses_api_with_the_task_role():
    """ECS passes SES_REGION and the task role may ses:SendRawEmail: no SMTP, no static keys."""
    mailer, region, endpoint, throttle, static_keys = production(
        "(s.MAILERS['default'], s.AWS_SES_REGION_NAME, s.AWS_SES_REGION_ENDPOINT,"
        " s.AWS_SES_AUTO_THROTTLE,"
        " sorted({'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SES_ACCESS_KEY_ID'} & set(dir(s))))",
        **AWS_ENV,
        EMAIL_HOST="smtp.example.com",
    )

    assert mailer == {"BACKEND": SES}
    assert (region, endpoint) == ("eu-west-1", "email.eu-west-1.amazonaws.com")
    # The throttle would first call ses:GetSendQuota, which the task role may not.
    assert throttle is None
    assert static_keys == []


def test_the_ses_backend_builds_from_the_settings_so_its_library_is_installed():
    """Built the way Django 6.1 builds a mailer; building neither connects nor signs."""
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import mailers\n"
        "b = mailers.default\n"
        "print(repr((f'{type(b).__module__}.{type(b).__name__}', b._region_name, b._endpoint_url,"
        " b._throttle, b._access_key_id, b._access_key, b._session_token)))",
        {**PRODUCTION_ENV, **AWS_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stderr
    assert ast.literal_eval(result.stdout.strip()) == (
        SES,
        "eu-west-1",
        "https://email.eu-west-1.amazonaws.com",
        None,
        # No keys of its own: boto3 signs with the task role.
        None,
        None,
        None,
    )


def test_a_ses_backend_named_by_the_environment_needs_its_region():
    result = _run("import config.settings", {**PRODUCTION_ENV, "EMAIL_BACKEND": SES})

    assert result.returncode != 0
    assert "UndefinedValueError" in result.stderr
    assert "SES_REGION" in result.stderr


def test_production_sends_mail_by_smtp_from_noreply():
    mailer, sender = production("(s.MAILERS['default'], s.DEFAULT_FROM_EMAIL)")

    assert mailer == {
        "BACKEND": SMTP,
        "OPTIONS": {
            "host": "localhost",
            "port": 587,
            "username": "",
            "password": "",
            "use_tls": True,
            "timeout": 10,
        },
    }
    assert sender == "noreply@erplora.com"


def test_the_smtp_server_and_the_sender_come_from_the_environment():
    mailer, sender = production(
        "(s.MAILERS['default'], s.DEFAULT_FROM_EMAIL)",
        EMAIL_HOST="email-smtp.eu-west-1.amazonaws.com",
        EMAIL_PORT="2587",
        EMAIL_HOST_USER="smtp-user",
        EMAIL_HOST_PASSWORD="smtp-password",
        EMAIL_USE_TLS="False",
        DEFAULT_FROM_EMAIL="hello@erplora.com",
    )

    assert mailer["OPTIONS"] == {
        "host": "email-smtp.eu-west-1.amazonaws.com",
        "port": 2587,
        "username": "smtp-user",
        "password": "smtp-password",
        "use_tls": False,
        "timeout": 10,
    }
    assert sender == "hello@erplora.com"


def test_email_backend_names_another_backend():
    assert production(
        "s.MAILERS['default']",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ) == {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}


def test_the_production_smtp_mailer_can_be_built():
    """Without SES_REGION, Django's MAILERS accepts the SMTP options (no connection until it sends)."""
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import mailers\n"
        "print(type(mailers.default).__module__)",
        {**PRODUCTION_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "django.core.mail.backends.smtp"


# The deploy checklist: `manage.py check --deploy` has nothing to say about production.


def test_check_deploy_is_clean_in_production():
    # AWS_ENV carries SES_REGION as ECS sets it: the SES backend must not trip mail.E001.
    result = _run(
        "from django.core.management import execute_from_command_line\n"
        "execute_from_command_line(['manage.py', 'check', '--deploy', '--fail-level', 'WARNING'])",
        {**PRODUCTION_ENV, **AWS_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


# Every saas* task as ECS starts it (aws-next/stacks/prod/apps.tf and secrets.tf): `base_env`,
# `saas_env` and the task's DB_APPLICATION_NAME, plus one variable per secret key. The Stripe and
# Google keys are born empty and filled by hand (aws README, step 16), and so are the seal slots,
# which only `saas` and `saas-cron` receive.

SAAS_TASK_ENV = {
    "AWS_REGION": "eu-west-1",
    "SES_REGION": "eu-west-1",
    "DEBUG": "False",
    "DB_HOST": "erplora-prod.cluster-c0ffee.eu-west-1.rds.amazonaws.com",
    "DB_PORT": "5432",
    "DB_SSLMODE": "verify-full",
    "DB_SSLROOTCERT": "/etc/ssl/certs/rds-global-bundle.pem",
    "VALKEY_URL": "rediss://erplora-prod-c0ffee.serverless.euw1.cache.amazonaws.com:6379",
    "DB_NAME": "saas",
    "AWS_STORAGE_BUCKET_NAME": "erplora-prod-saas",
    "HUB_INTERNAL_URL": "http://hub.erplora.internal:8000",
    "HUB_CALLBACK_TEMPLATE": "https://{slug}.erplora.com/auth/callback",
    "DEFAULT_FROM_EMAIL": "noreply@erplora.com",
    "ALLOWED_HOSTS": "erplora.com,saas.erplora.internal",
    # erplora/prod/saas: SECRET_KEY is generated by Terraform (64 letters and digits).
    "SECRET_KEY": "Zq8vN2kLw5Rt9Xb3Hc7Jm1Pd6Fg4Ys0Ue2Ai8Ko5Vn3Tl7Wr1Qx9Mz6Bh4Cj0Gp2Ds",
    "STRIPE_SECRET_KEY": "",
    "STRIPE_PUBLISHABLE_KEY": "",
    "STRIPE_WEBHOOK_SECRET": "",
    "GOOGLE_OAUTH_CLIENT_ID": "",
    "GOOGLE_OAUTH_CLIENT_SECRET": "",
    # erplora/prod/internal, the same in both projects.
    "INTERNAL_SHARED_SECRET": "a-generated-internal-shared-secret",
}
SEAL_SLOTS_AS_BORN = {
    "FISCAL_SEAL_CURRENT_P12_BASE64": "",
    "FISCAL_SEAL_CURRENT_PASSWORD": "",
    "FISCAL_SEAL_NEXT_P12_BASE64": "",
    "FISCAL_SEAL_NEXT_PASSWORD": "",
}
TASKS = {
    "saas": {
        **SAAS_TASK_ENV,
        "DB_APPLICATION_NAME": "saas",
        "DB_USER": "saas_app",
        "DB_PASSWORD": "saas-app-password",
        **SEAL_SLOTS_AS_BORN,
    },
    "saas-migrate": {
        **SAAS_TASK_ENV,
        "DB_APPLICATION_NAME": "saas-migrate",
        "DB_USER": "saas_migrator",
        "DB_PASSWORD": "saas-migrator-password",
    },
    "saas-cron": {
        **SAAS_TASK_ENV,
        "DB_APPLICATION_NAME": "saas-cron",
        "DB_USER": "saas_app",
        "DB_PASSWORD": "saas-app-password",
        **SEAL_SLOTS_AS_BORN,
    },
}
# What step 16 fills by hand: Google's client and Stripe's keys.
FILLED_BY_HAND = {
    "GOOGLE_OAUTH_CLIENT_ID": "prod-client.apps.googleusercontent.com",
    "GOOGLE_OAUTH_CLIENT_SECRET": "prod-secret",
    "STRIPE_SECRET_KEY": "sk_live_dummy",
    "STRIPE_PUBLISHABLE_KEY": "pk_live_dummy",
    "STRIPE_WEBHOOK_SECRET": "whsec_dummy",
}


def task_settings(expression: str, task: str, **env: str):
    """The value of ``expression`` with exactly the environment ECS gives ``task``."""
    return _settings(expression, {**TASKS[task], **env})


def check_deploy(env: dict[str, str]) -> subprocess.CompletedProcess:
    return _run(
        "from django.core.management import execute_from_command_line\n"
        "execute_from_command_line(['manage.py', 'check', '--deploy', '--fail-level', 'WARNING'])",
        {**env, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )


@pytest.mark.parametrize("task", TASKS)
def test_every_saas_task_loads_its_settings(task):
    assert task_settings(
        "(s.DEBUG, s.ALLOWED_HOSTS, s.AWS_REGION, s.DATABASES['default']['OPTIONS']['application_name'],"
        " s.FISCAL_SEAL_CURRENT_P12_BASE64, s.FISCAL_SEAL_CURRENT_PASSWORD,"
        " s.FISCAL_SEAL_NEXT_P12_BASE64, s.FISCAL_SEAL_NEXT_PASSWORD)",
        task,
    ) == (
        False,
        ["erplora.com", "saas.erplora.internal"],
        "eu-west-1",
        task,
        # An empty slot is an empty slot; saas-migrate gets none at all.
        "",
        "",
        "",
        "",
    )


@pytest.mark.parametrize("task", TASKS)
def test_check_deploy_has_nothing_to_say_about_any_saas_task(task):
    """Born with Google empty, the only line is accounts.I001 (an Info: «Continue with Google» is
    hidden until step 16); never a warning, never mail.E001."""
    result = check_deploy(TASKS[task])
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "mail.E001" not in output
    assert "WARNINGS:" not in output and "ERRORS:" not in output, output
    assert set(re.findall(r"\(([a-z_]+\.[A-Z]\d{3})\)", output)) <= {"accounts.I001"}


@pytest.mark.parametrize("task", TASKS)
def test_check_deploy_identifies_no_issues_once_the_keys_are_filled(task):
    result = check_deploy({**TASKS[task], **FILLED_BY_HAND})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


def test_the_seal_slots_and_the_region_come_from_the_environment():
    """The two .p12 slots of the fiscal seal (erplora/prod/fiscal/seal-{current,next}), base64 and
    password each, and the region CloudWatch is called in (report_seal_expiry)."""
    assert task_settings(
        "(s.AWS_REGION, s.FISCAL_SEAL_CURRENT_P12_BASE64, s.FISCAL_SEAL_CURRENT_PASSWORD,"
        " s.FISCAL_SEAL_NEXT_P12_BASE64, s.FISCAL_SEAL_NEXT_PASSWORD)",
        "saas-cron",
        AWS_REGION="eu-west-3",
        FISCAL_SEAL_CURRENT_P12_BASE64="Y3VycmVudA==",
        FISCAL_SEAL_CURRENT_PASSWORD="current-password",
        FISCAL_SEAL_NEXT_P12_BASE64="bmV4dA==",
        FISCAL_SEAL_NEXT_PASSWORD="next-password",
    ) == ("eu-west-3", "Y3VycmVudA==", "current-password", "bmV4dA==", "next-password")


def test_development_has_empty_seal_slots_and_the_platform_region():
    assert development(
        "(s.AWS_REGION, s.FISCAL_SEAL_CURRENT_P12_BASE64, s.FISCAL_SEAL_NEXT_P12_BASE64)"
    ) == ("eu-west-1", "", "")
