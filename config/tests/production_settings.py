"""Production settings of the SaaS, as ECS starts them (aws README, «Contrato app ↔ infra»).

``config.settings`` is evaluated once per process from the environment, so every production value
is read in a fresh interpreter. That interpreter never reads the repo's ``.env`` (a developer's
``DEBUG=True`` would leak in) and starts from an almost empty environment: only what each test
passes, on top of the variables production must provide, reaches the settings.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

SAAS_NEXT = Path(__file__).resolve().parents[2]
# What the task definition and Secrets Manager give every saas* task (ERPlora/aws stacks/prod/apps.tf),
# with dummies for the secrets. The key is long and varied enough for `check --deploy` (W009).
PRODUCTION_ENV = {
    "DEBUG": "False",
    "CACHE_KEY_PREFIX": "saas",
    "STRIPE_EXPECTED_MODE": "live",
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
    # reCAPTCHA Enterprise (live.recaptcha): the site key and the assessments' API key, read only with
    # RECAPTCHA_ENABLED=True (off by default).
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
# The fresh interpreter ignores the repo's .env: decouple's file repository is swapped for an empty
# one before config.settings builds its Config.
IGNORE_DOTENV = "import decouple; decouple.RepositoryEnv = lambda *args, **kwargs: decouple.RepositoryEmpty()"


def bare_environment() -> dict[str, str]:
    """What a fresh interpreter needs from the shell to start, and nothing else a developer exports."""
    return {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}


def _run(code: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", f"{IGNORE_DOTENV}\n{code}"],
        cwd=SAAS_NEXT,
        env={**bare_environment(), **env},
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
    """The same with ``DEBUG=True`` alone, as the repo's .env (.env.example) runs it. The test run
    swaps some values (the mailers, for one), so development is read in a fresh process too."""
    return _settings(expression, {"DEBUG": "True", **env})


# Every saas* task as ECS starts it (ERPlora/aws stacks/prod/apps.tf and secrets.tf): `base_env`,
# `saas_env` and the task's DB_APPLICATION_NAME, plus one variable per secret key. The Stripe and
# Google keys are born empty and filled by hand (aws README, step 16), and so are the seal slots,
# which only `saas` and `saas-cron` receive.

SAAS_TASK_ENV = {
    "AWS_REGION": "eu-west-1",
    "SES_REGION": "eu-west-1",
    "DEBUG": "False",
    "CACHE_KEY_PREFIX": "saas",
    "STRIPE_EXPECTED_MODE": "live",
    "PUBLIC_INDEXING_ENABLED": "true",
    "AEAT_PRODUCTION_ENABLED": "true",
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
    # erplora/prod/saas: the Fernet key of the hubs' fiscal documents (fiscal/crypto.py). Every saas* task needs
    # it, or the tasks refuse to start.
    "FISCAL_DOCUMENTS_KEY": "kX1Hq3xmJ2a6r0pN7yTbV4cZ8uW5sE9dL1fG2hJ3kM4=",
    # erplora/<env>/saas: reCAPTCHA Enterprise's site key and API key (live.recaptcha), handed to every saas* task.
    # Read only with RECAPTCHA_ENABLED=True (off by default).
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


def task_settings(expression: str, task: str, **env: str):
    """The value of ``expression`` with exactly the environment ECS gives ``task``."""
    return _settings(expression, {**TASKS[task], **env})


def check_deploy(env: dict[str, str]) -> subprocess.CompletedProcess:
    return _run(
        "from django.core.management import execute_from_command_line\n"
        "execute_from_command_line(['manage.py', 'check', '--deploy', '--fail-level', 'WARNING'])",
        {**env, "DJANGO_SETTINGS_MODULE": "config.settings"},
    )
