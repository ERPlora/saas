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
    # The key of the hubs' fiscal documents (fiscal/crypto.py): a Fernet key, required without DEBUG.
    "FISCAL_DOCUMENTS_KEY": "2EBDB2KSnvz5lBG1RHG5ldNq34ZjWvGZ_t5r4wl5Mpw=",
    # WhatsApp (whatsapp/): Meta's app, its webhook and the key of the Meta credentials.
    "WHATSAPP_APP_ID": "1234567890",
    "WHATSAPP_APP_SECRET": "prod-meta-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "prod-verify-token",
    "WHATSAPP_CONFIG_ID": "987654321",
    "FERNET_KEY": "yh5h4Yur2lIgWp9ZxkyLt1BrQfFVrwLH4WhIHCRwXXA=",
    # reCAPTCHA Enterprise on every public form (live.recaptcha): the site key and the assessments' API key.
    "RECAPTCHA_SITE_KEY": "prod-recaptcha-site-key",
    "RECAPTCHA_API_KEY": "prod-recaptcha-api-key",
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
    assert options["pool"] == {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5}


def test_without_tls_variables_the_connection_options_are_only_the_pool_and_its_timeouts():
    """Local Postgres (compose.yaml) has no TLS: nothing is added unless the variable is set."""
    only_the_pool = {
        "pool": {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5},
        "connect_timeout": 5,
    }
    assert production("s.DATABASES['default']['OPTIONS']") == only_the_pool
    assert (
        production(
            "s.DATABASES['default']['OPTIONS']", DB_SSLMODE="", DB_SSLROOTCERT=""
        )
        == only_the_pool
    )


def test_a_burst_of_pooled_connections_is_given_back_within_minutes():
    """psycopg_pool closes one connection above min_size per max_idle, 600 s by default: after a
    burst the idle SaaS kept up to 8 connections for over an hour (4 measured on 2026-10-18). With
    60 s it is back to one within 7 minutes; that one stays open for the next request (PLAN-DB
    «Conexiones», round 2026-10-18). As in the Hub."""
    pool = production("s.DATABASES['default']['OPTIONS']['pool']")
    assert (pool["min_size"], pool["max_size"], pool["max_idle"]) == (1, 8, 60)


@pytest.mark.django_db
def test_the_running_pool_closes_idle_connections_after_60_seconds():
    """Django hands OPTIONS["pool"] to psycopg_pool as is: the pool this process opened has it."""
    from django.db import connection

    connection.ensure_connection()
    assert (connection.pool.min_size, connection.pool.max_idle) == (1, 60)


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


# Email: a file per mail in saas-next/.mail/ in development (the sign-in code is read there, also by
# the Hub's e2e); in production the SES API signed by the task role when ECS passes SES_REGION, SMTP
# configured by the environment otherwise, or any backend EMAIL_BACKEND names. Same variables and
# order as hub-next.

SMTP = "django.core.mail.backends.smtp.EmailBackend"
SES = "django_ses.SESBackend"
CONSOLE = "django.core.mail.backends.console.EmailBackend"
FILE = "django.core.mail.backends.filebased.EmailBackend"
#: Where development writes every mail: the code of every password sign-in is read there.
DEV_MAIL_DIR = str(SAAS_NEXT / ".mail")


def test_development_writes_every_mail_to_a_file_in_saas_next_mail():
    assert development("s.MAILERS['default']") == {"BACKEND": FILE, "OPTIONS": {"file_path": DEV_MAIL_DIR}}
    # Even with production's SES region in the environment, DEBUG never sends real mail.
    assert development("s.MAILERS['default']", SES_REGION="eu-west-1") == {
        "BACKEND": FILE,
        "OPTIONS": {"file_path": DEV_MAIL_DIR},
    }


def test_development_takes_the_backend_and_the_folder_from_the_environment(tmp_path):
    """The panel's e2e names its own folder; any other backend (the console) is still one variable away."""
    assert development("s.MAILERS['default']", EMAIL_FILE_PATH=str(tmp_path)) == {
        "BACKEND": FILE,
        "OPTIONS": {"file_path": str(tmp_path)},
    }
    assert development("s.MAILERS['default']", EMAIL_BACKEND=CONSOLE) == {"BACKEND": CONSOLE}


def test_the_development_mail_folder_is_never_versioned():
    ignored = (SAAS_NEXT / ".gitignore").read_text().splitlines()

    assert ".mail/" in ignored


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


def test_a_mail_to_ses_waits_seconds_never_minutes():
    """ACCOUNTS-G79: a sign-in mails its code inside the request; with boto3's defaults (60 s to connect, 60 s to read,
    retried) an SES that does not answer held the person there for minutes. As the SMTP mailer (10 s): 3 s to connect,
    10 s to read and one try more, so a failure reaches the page (and the log) within half a minute."""
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import mailers\n"
        "c = mailers.default._config\n"
        "print(repr((c.connect_timeout, c.read_timeout, c.retries)))",
        {**PRODUCTION_ENV, **AWS_ENV, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )

    assert result.returncode == 0, result.stderr
    assert ast.literal_eval(result.stdout.strip()) == (3, 10, {"total_max_attempts": 2, "mode": "standard"})


# The hubs' fiscal documents (plan 2026-10-15): encrypted with a Fernet key, required in production like
# INTERNAL_SHARED_SECRET (a deploy without it must not start and store documents it cannot read later).


def test_production_refuses_to_start_without_the_fiscal_documents_key():
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "FISCAL_DOCUMENTS_KEY"}

    result = _run("import config.settings", env)

    assert result.returncode != 0
    assert "UndefinedValueError" in result.stderr
    assert "FISCAL_DOCUMENTS_KEY" in result.stderr


def test_production_takes_the_fiscal_documents_key_from_the_environment():
    assert production("s.FISCAL_DOCUMENTS_KEY") == PRODUCTION_ENV["FISCAL_DOCUMENTS_KEY"]


def test_development_has_a_local_fernet_key_for_the_fiscal_documents():
    from cryptography.fernet import Fernet

    key = development("s.FISCAL_DOCUMENTS_KEY")

    assert Fernet(key.encode()).decrypt(Fernet(key.encode()).encrypt(b"ok")) == b"ok"


def test_every_view_keeps_django_s_upload_ceiling():
    """Django's 2.5 MB for every view (allauth, ``/api``, Stripe's webhook): an anonymous body is never buffered
    beyond it. The four documents of an authorisation have their own ceiling, in their view only
    (``fiscal.internal.MAX_BODY_BYTES``)."""
    expression = "getattr(s, 'DATA_UPLOAD_MAX_MEMORY_SIZE', 'django default')"
    assert production(expression) == "django default"
    assert development(expression) == "django default"


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


def test_a_file_backend_writes_where_email_file_path_says(tmp_path):
    """The panel's e2e (tests/e2e/panel/project.ts) reads what the SaaS mails from files: Django's
    MAILERS gives the file backend its folder in OPTIONS, never through EMAIL_FILE_PATH itself."""
    folder = str(tmp_path / "mail")
    assert development(
        "s.MAILERS['default']", EMAIL_BACKEND=FILE, EMAIL_FILE_PATH=folder
    ) == {
        "BACKEND": FILE,
        "OPTIONS": {"file_path": folder},
    }

    result = _run(
        "import django\ndjango.setup()\nfrom django.core.mail import send_mail\n"
        "send_mail('Subject', 'Body', None, ['someone@example.com'])",
        {
            "DEBUG": "True",
            "EMAIL_BACKEND": FILE,
            "EMAIL_FILE_PATH": folder,
            "DJANGO_SETTINGS_MODULE": "config.settings",
        },
    )

    assert result.returncode == 0, result.stderr
    (written,) = (tmp_path / "mail").iterdir()
    assert "To: someone@example.com" in written.read_text()


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
    # erplora/prod/saas: the Fernet key of the hubs' fiscal documents (fiscal/crypto.py; plan 2026-10-15).
    # NEW: aws-next must add it to every saas* task before this deploys, or the tasks refuse to start.
    "FISCAL_DOCUMENTS_KEY": "kX1Hq3xmJ2a6r0pN7yTbV4cZ8uW5sE9dL1fG2hJ3kM4=",
    # erplora/<env>/saas: reCAPTCHA Enterprise's site key and API key (live.recaptcha). NEW (2026-10-22): aws must
    # hand both to every saas* task before this deploys, or the tasks refuse to start.
    "RECAPTCHA_SITE_KEY": "6Lprod-recaptcha-site-key",
    "RECAPTCHA_API_KEY": "prod-recaptcha-api-key",
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
    # A RESTRICTED live key (PLAN-SAAS §4): the account's secret key fails the deploy check (billing.E001).
    "STRIPE_SECRET_KEY": "rk_live_dummy",
    "STRIPE_PUBLISHABLE_KEY": "pk_live_dummy",
    "STRIPE_WEBHOOK_SECRET": "whsec_dummy",
    # WhatsApp (whatsapp/): born empty like Google until its secrets reach the infrastructure.
    "WHATSAPP_APP_ID": "1234567890",
    "WHATSAPP_APP_SECRET": "prod-meta-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "prod-verify-token",
    "WHATSAPP_CONFIG_ID": "987654321",
    "FERNET_KEY": "yh5h4Yur2lIgWp9ZxkyLt1BrQfFVrwLH4WhIHCRwXXA=",
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
    """Born with Google and WhatsApp empty, the only lines are accounts.I001 and whatsapp.I001 (Infos: «Continue
    with Google» is hidden until step 16, and WhatsApp is off until its secrets come); never a warning, never
    mail.E001."""
    result = check_deploy(TASKS[task])
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "mail.E001" not in output
    assert "WARNINGS:" not in output and "ERRORS:" not in output, output
    assert set(re.findall(r"\(([a-z_]+\.[A-Z]\d{3})\)", output)) <= {"accounts.I001", "whatsapp.I001"}


@pytest.mark.parametrize("task", TASKS)
def test_check_deploy_identifies_no_issues_once_the_keys_are_filled(task):
    result = check_deploy({**TASKS[task], **FILLED_BY_HAND})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


def test_check_deploy_refuses_the_stripe_accounts_live_secret_key():
    result = check_deploy({**TASKS["saas"], **FILLED_BY_HAND, "STRIPE_SECRET_KEY": "sk_live_dummy"})

    assert result.returncode != 0
    assert "billing.E001" in result.stdout + result.stderr


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


# The environment (plan 2026-10-14-entorno-pre): `prod` or `pre`, the team's pre-production in the same
# cluster, ALB, Aurora and Valkey as prod. What differs in pre: the cache prefix in the shared Valkey,
# no indexing (public/seo.py, public/crawlers.py, indexnow_submit) and Stripe in test mode only
# (billing.E002). Anything else refuses to start.


def test_the_environment_defaults_to_prod_and_keeps_the_saas_cache_prefix():
    assert production("(s.ERPLORA_ENVIRONMENT, s.CACHES['default']['KEY_PREFIX'])", **AWS_ENV) == (
        "prod",
        "saas",
    )
    assert development("s.ERPLORA_ENVIRONMENT") == "prod"
    assert settings.ERPLORA_ENVIRONMENT == "prod"


@pytest.mark.parametrize("environment", ["staging", "dev", "PRE", "production", " "])
def test_an_unknown_environment_refuses_to_start(environment):
    result = _run("import config.settings", {**PRODUCTION_ENV, "ERPLORA_ENVIRONMENT": environment})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "ERPLORA_ENVIRONMENT" in result.stderr


# Every saas* task of pre as ECS starts it (aws-next stacks/prod/pre_apps.tf, plan §2.2 A4): the prod
# task's variables with pre's hosts, database, roles, buckets and secrets (erplora/pre/app and
# erplora/pre/db, Stripe in test mode, Google and the seal empty). No saas-cron in pre.

PRE_TASK_ENV = {
    **SAAS_TASK_ENV,
    "ERPLORA_ENVIRONMENT": "pre",
    "DB_NAME": "pre_saas",
    "ALLOWED_HOSTS": "pre.erplora.com,saas-pre.erplora.internal",
    "AWS_STORAGE_BUCKET_NAME": "erplora-pre-saas",
    "HUB_INTERNAL_URL": "http://hub-pre.erplora.internal:8000",
    "HUB_CALLBACK_TEMPLATE": "https://{slug}.pre.erplora.com/auth/callback",
    "HUB_ADMIN_CALLBACK_URL": "https://hubs.pre.erplora.com/auth/callback",
    "HUB_STATIC_BASE_URL": "https://hubs.pre.erplora.com/static/",
    "PUBLIC_HOST": "pre.erplora.com",
    "PLATFORM_INVOICING_ENABLED": "false",
    "SECURE_HSTS_SECONDS": "86400",
    # erplora/pre/app: SAAS_SECRET_KEY and INTERNAL_SHARED_SECRET generated by Terraform.
    "SECRET_KEY": "Pq7wM3jKv6St1Yc8Gb2Hn5Rd9Lf0Xa4Ue7Zi3Ko6Vm2Tj8Wq1Nx5Bc9Ch3Dg7Fp0Es",
    "INTERNAL_SHARED_SECRET": "a-generated-pre-internal-shared-secret",
    "INTERNAL_SHARED_SECRET_PREVIOUS": "",
    # erplora/pre/app: pre's own key of the hubs' fiscal documents (NEW, as prod's).
    "FISCAL_DOCUMENTS_KEY": "pR3eK9yW2xQ7mN4bV8cZ1aS6dF0gH5jL3kT7uY2iO9E=",
    "STRIPE_PORTAL_CONFIGURATION": "",
}
PRE_TASKS = {
    "saas-pre": {
        **PRE_TASK_ENV,
        "DB_APPLICATION_NAME": "saas-pre",
        "DB_USER": "pre_saas_app",
        "DB_PASSWORD": "pre-saas-app-password",
        # Only saas-pre reads the app's installers, from prod's downloads bucket.
        "DOWNLOADS_BUCKET": "erplora-prod-downloads",
        "DOWNLOADS_REGION": "eu-west-1",
        **SEAL_SLOTS_AS_BORN,
    },
    "saas-migrate-pre": {
        **PRE_TASK_ENV,
        "DB_APPLICATION_NAME": "saas-migrate-pre",
        "DB_USER": "pre_saas_migrator",
        "DB_PASSWORD": "pre-saas-migrator-password",
    },
}
# What the pre secret's Stripe keys hold (stripe-setup-pre.sh): a RESTRICTED test key and its siblings.
PRE_STRIPE_TEST_KEYS = {
    "STRIPE_SECRET_KEY": "rk_test_dummy",
    "STRIPE_PUBLISHABLE_KEY": "pk_test_dummy",
    "STRIPE_WEBHOOK_SECRET": "whsec_dummy",
    "STRIPE_PORTAL_CONFIGURATION": "bpc_dummy",
}


@pytest.mark.parametrize("task", PRE_TASKS)
def test_pre_settings_load_with_the_pre_task_environment(task):
    """Every address the SaaS of pre builds points at pre: its own host, the hubs of pre and the Hub
    of pre by its private name; never erplora.com's."""
    values = _settings(
        "(s.DEBUG, s.ERPLORA_ENVIRONMENT, s.ALLOWED_HOSTS, s.DATABASES['default']['NAME'],"
        " s.DATABASES['default']['USER'], s.DATABASES['default']['OPTIONS']['application_name'],"
        " s.HUB_INTERNAL_URL, s.HUB_ORIGIN_PATTERN, s.HUB_ADMIN_ORIGIN, s.HUB_STATIC_BASE_URL,"
        " s.PUBLIC_HOST, s.SECURE_HSTS_SECONDS, s.PLATFORM_INVOICING_ENABLED, [str(source) for source in s.SECURE_CSP['form-action']])",
        PRE_TASKS[task],
    )

    assert values[:13] == (
        False,
        "pre",
        ["pre.erplora.com", "saas-pre.erplora.internal"],
        "pre_saas",
        "pre_saas_app" if task == "saas-pre" else "pre_saas_migrator",
        task,
        "http://hub-pre.erplora.internal:8000",
        "https://*.pre.erplora.com",
        "https://hubs.pre.erplora.com",
        "https://hubs.pre.erplora.com/static/",
        "pre.erplora.com",
        86400,
        False,
    )
    form_action = values[13]
    assert {"https://*.pre.erplora.com", "https://hubs.pre.erplora.com"} <= set(form_action)
    assert not [source for source in form_action if source.endswith("//hubs.erplora.com")]


def test_pre_prefixes_every_cache_key():
    """pre and prod share one Valkey: the login rate limits, the contact form's and anything cached
    by one must never be read or overwritten by the other."""
    code = (
        "import django\ndjango.setup()\nfrom django.conf import settings\n"
        "from django.core.cache import caches\n"
        "print(repr((settings.CACHES['default']['KEY_PREFIX'], caches['default'].make_key('login'))))"
    )
    env = {"VALKEY_URL": "rediss://erplora-prod.serverless.euw1.cache.amazonaws.com:6379",
           "DJANGO_SETTINGS_MODULE": "config.settings"}

    pre = _run(code, {**PRE_TASKS["saas-pre"], **env})
    prod = _run(code, {**TASKS["saas"], **env})

    assert pre.returncode == 0, pre.stderr
    assert prod.returncode == 0, prod.stderr
    assert ast.literal_eval(pre.stdout.strip()) == ("pre-saas", "pre-saas:1:login")
    assert ast.literal_eval(prod.stdout.strip()) == ("saas", "saas:1:login")


@pytest.mark.parametrize("task", PRE_TASKS)
def test_check_deploy_passes_in_pre_with_a_restricted_test_key(task):
    """Born with Google, WhatsApp and the seal empty, the only lines are accounts.I001 and whatsapp.I001 (Infos)."""
    result = check_deploy({**PRE_TASKS[task], **PRE_STRIPE_TEST_KEYS})
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "WARNINGS:" not in output and "ERRORS:" not in output, output
    assert set(re.findall(r"\(([a-z_]+\.[A-Z]\d{3})\)", output)) <= {"accounts.I001", "whatsapp.I001"}


@pytest.mark.parametrize("key", ["rk_live_dummy", "sk_live_dummy"])
def test_check_deploy_refuses_a_live_key_in_pre(key):
    """Whoever pushes to the pre branch runs code with pre's secrets: no live money there."""
    result = check_deploy({**PRE_TASKS["saas-pre"], **PRE_STRIPE_TEST_KEYS, "STRIPE_SECRET_KEY": key})

    assert result.returncode != 0
    assert "billing.E002" in result.stdout + result.stderr


# Sign-in attempts (allauth's rate limits): allauth lays ACCOUNT_RATE_LIMITS over its own defaults, so
# what it enforces is read where allauth reads it (allauth.account.app_settings), never from the dict the
# settings write. Only the e2e's panel server raises the sign-in limit (E2E_RELAX_LOGIN_RATE_LIMIT): every
# spec signs in from 127.0.0.1, and one spec repeated (`--repeat-each=6`) went past allauth's 30 a minute.

RATE_LIMITS = (
    "from django.conf import settings\n"
    "from allauth.account import app_settings\n"
    "effective = app_settings.RATE_LIMITS\n"
    "settings.ACCOUNT_RATE_LIMITS = {}\n"
    "print(repr((effective, app_settings.RATE_LIMITS)))"
)


def rate_limits(env: dict[str, str]) -> tuple[dict, dict]:
    """(the rate limits allauth enforces with ``env``, allauth's own defaults with the rest of the settings)."""
    result = _run(RATE_LIMITS, {**env, "DJANGO_SETTINGS_MODULE": "config.settings"})
    assert result.returncode == 0, result.stderr
    return ast.literal_eval(result.stdout.strip())


@pytest.mark.parametrize(
    "env",
    [PRODUCTION_ENV, TASKS["saas"], {"DEBUG": "True"}],
    ids=["production", "saas-task", "development"],
)
def test_the_sign_in_limits_are_written_out(env):
    """Production and development alike (the dev server with DEBUG=True alone): every limit written out
    (config/settings.py), allauth's sign-in limit kept, and nothing of allauth's left unsaid."""
    effective, allauth = rate_limits(env)

    assert effective["login"] == allauth["login"]
    assert {**allauth, **effective} == {
        **allauth,
        "login": "30/m/ip",
        "login_failed": "5/5m/ip,5/5m/key",
        "signup": "10/h/ip",
        "reset_password": "10/h/ip,5/h/key",
        "reset_password_from_key": "20/m/ip",
        "confirm_email": "1/10s/key",
        "code_attempts": "10/5m/ip",
    }


@pytest.mark.parametrize("off", ["0", "False"])
def test_the_e2e_variable_turned_off_keeps_the_sign_in_limit(off):
    effective, allauth = rate_limits({"DEBUG": "True", "E2E_RELAX_LOGIN_RATE_LIMIT": off})

    assert effective["login"] == allauth["login"]


def test_the_e2e_raises_the_limits_per_address_of_the_sign_in_and_nothing_else():
    """Every panel spec signs in from 127.0.0.1, password and mailed code: the address's budgets of the sign-in, of the
    failed passwords and of the typed codes go out of the e2e's reach (one sign-in takes over 0.1 s, one at a time),
    still a limit. Each account keeps its own (5 wrong passwords in 5 minutes), and so do sign-up, the reset links and
    «Send another code»."""
    relaxed, allauth = rate_limits({"DEBUG": "True", "E2E_RELAX_LOGIN_RATE_LIMIT": "True"})
    kept, _ = rate_limits({"DEBUG": "True"})

    assert relaxed["login"] == "1000/m/ip" != allauth["login"]
    assert relaxed["login_failed"] == "1000/m/ip,5/5m/key"
    assert relaxed["code_attempts"] == "1000/m/ip"
    assert {**relaxed, "login": kept["login"], "login_failed": kept["login_failed"], "code_attempts": kept["code_attempts"]} == kept


def test_production_refuses_to_start_with_the_e2e_s_sign_in_limit():
    result = _run("import config.settings", {**PRODUCTION_ENV, "E2E_RELAX_LOGIN_RATE_LIMIT": "True"})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "E2E_RELAX_LOGIN_RATE_LIMIT" in result.stderr


# WhatsApp's return page (whatsapp/signup_return.py): where Meta's window brings its one-time code back. Door 10 hands
# it to the Hub, which accepts it only from its SAAS_URL's origin, and door 11 exchanges the code with the same value.


def test_production_s_whatsapp_return_page_is_erplora_s_own_over_https():
    assert production("s.WHATSAPP_REDIRECT_URI") == "https://erplora.com/whatsapp/return"


def test_pre_s_whatsapp_return_page_follows_its_host():
    assert production("s.WHATSAPP_REDIRECT_URI", PUBLIC_HOST="pre.erplora.com") == "https://pre.erplora.com/whatsapp/return"


def test_development_s_whatsapp_return_page_is_the_local_saas():
    assert development("s.WHATSAPP_REDIRECT_URI") == "http://localhost:8001/whatsapp/return"


def test_the_whatsapp_return_page_may_be_given_by_the_environment():
    given = "http://localhost:8601/whatsapp/return"

    assert development("s.WHATSAPP_REDIRECT_URI", WHATSAPP_REDIRECT_URI=given) == given


# reCAPTCHA Enterprise (live.recaptcha; Ioan, 2026-10-22): every public form is checked in production, which refuses to
# start without both keys and cannot switch it off; development checks only with both keys (`.env`), and the test run
# never (config/settings_pytest.py). The minimum score and the endpoint come from the environment.

RECAPTCHA = "s.LIVE['recaptcha']"
RECAPTCHA_KEYS = {"RECAPTCHA_SITE_KEY": "dev-site-key", "RECAPTCHA_API_KEY": "dev-api-key"}


def test_production_checks_every_public_form_with_recaptcha():
    assert production(RECAPTCHA) == {
        "enabled": True,
        "project": "erplora",
        "site_key": "prod-recaptcha-site-key",
        "api_key": "prod-recaptcha-api-key",
        "min_score": 0.5,
        "endpoint": None,
    }


@pytest.mark.parametrize("missing", ["RECAPTCHA_SITE_KEY", "RECAPTCHA_API_KEY"])
@pytest.mark.parametrize("how", ["absent", "empty"])
def test_production_refuses_to_start_without_a_recaptcha_key(missing, how):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != missing}
    if how == "empty":
        env[missing] = ""

    result = _run("import config.settings", env)

    assert result.returncode != 0
    assert missing in result.stderr


@pytest.mark.parametrize("task", sorted(TASKS))
def test_every_saas_task_starts_with_recaptcha_on(task):
    result = _run(f"import config.settings as s\nprint({RECAPTCHA}['enabled'])", TASKS[task])

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_production_cannot_switch_recaptcha_off():
    result = _run("import config.settings", {**PRODUCTION_ENV, "RECAPTCHA_ENABLED": "False"})

    assert result.returncode != 0
    assert "RECAPTCHA_ENABLED" in result.stderr


def test_the_minimum_score_and_the_project_come_from_the_environment():
    conf = production(RECAPTCHA, RECAPTCHA_MIN_SCORE="0.7", RECAPTCHA_PROJECT="erplora-pre")

    assert (conf["min_score"], conf["project"]) == (0.7, "erplora-pre")


@pytest.mark.parametrize("score", ["1.5", "-0.1", "high"])
def test_a_minimum_score_outside_zero_to_one_refuses_to_start(score):
    result = _run("import config.settings", {**PRODUCTION_ENV, "RECAPTCHA_MIN_SCORE": score})

    assert result.returncode != 0
    assert "RECAPTCHA_MIN_SCORE" in result.stderr


def test_the_assessments_may_go_to_another_endpoint():
    url = "http://127.0.0.1:8018/v1/projects/erplora/assessments"

    assert production(RECAPTCHA, RECAPTCHA_ENDPOINT=url)["endpoint"] == url


def test_development_without_keys_checks_nothing():
    assert development(RECAPTCHA)["enabled"] is False


def test_development_with_both_keys_checks_the_forms():
    conf = development(RECAPTCHA, **RECAPTCHA_KEYS)

    assert (conf["enabled"], conf["site_key"], conf["api_key"]) == (True, "dev-site-key", "dev-api-key")


def test_development_with_keys_may_switch_it_off():
    assert development(RECAPTCHA, **RECAPTCHA_KEYS, RECAPTCHA_ENABLED="False")["enabled"] is False


def test_development_switched_on_without_keys_refuses_to_start():
    result = _run("import config.settings", {"DEBUG": "True", "RECAPTCHA_ENABLED": "True"})

    assert result.returncode != 0
    assert "RECAPTCHA_SITE_KEY" in result.stderr


def test_the_test_run_never_checks_whatever_the_dotenv_says():
    from django.conf import settings

    assert settings.LIVE["recaptcha"]["enabled"] is False
