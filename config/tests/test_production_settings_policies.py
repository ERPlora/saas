import re

import pytest
from django.conf import settings

from config.tests.production_settings import AWS_ENV, PRODUCTION_ENV, SAAS_NEXT, _run, development, production


def test_local_policy_defaults_are_safe_without_deployment_variables():
    assert development(
        "(s.CACHE_KEY_PREFIX, s.STRIPE_EXPECTED_MODE, s.PUBLIC_INDEXING_ENABLED, s.AEAT_PRODUCTION_ENABLED)"
    ) == ("local-saas", "test", False, False)


@pytest.mark.parametrize("valkey", ["", "redis://localhost:6379/0"])
def test_cache_policy_applies_to_local_and_shared_backends(valkey):
    assert development("s.CACHES['default']['KEY_PREFIX']", VALKEY_URL=valkey) == "local-saas"
    assert development(
        "s.CACHES['default']['KEY_PREFIX']", VALKEY_URL=valkey, CACHE_KEY_PREFIX="second-local-saas"
    ) == "second-local-saas"


@pytest.mark.parametrize("label", ["prod", "pre"])
def test_explicit_policies_do_not_depend_on_the_deployment_label(label):
    assert production(
        "(s.CACHES['default']['KEY_PREFIX'], s.STRIPE_EXPECTED_MODE, s.PUBLIC_INDEXING_ENABLED, s.AEAT_PRODUCTION_ENABLED)",
        ERPLORA_ENVIRONMENT=label,
        CACHE_KEY_PREFIX="isolated-saas",
        STRIPE_EXPECTED_MODE="test",
        PUBLIC_INDEXING_ENABLED="true",
        AEAT_PRODUCTION_ENABLED="true",
        VALKEY_URL="redis://localhost:6379/0",
    ) == ("isolated-saas", "test", True, True)


@pytest.mark.parametrize("name", ["CACHE_KEY_PREFIX", "STRIPE_EXPECTED_MODE"])
def test_deployed_policy_requires_explicit_critical_values(name):
    environment = {key: value for key, value in PRODUCTION_ENV.items() if key != name}
    result = _run("import config.settings", environment)
    assert result.returncode != 0
    assert name in result.stderr


@pytest.mark.parametrize(
    ("name", "value"),
    [("CACHE_KEY_PREFIX", " "), ("STRIPE_EXPECTED_MODE", "lve"),
     ("STRIPE_EXPECTED_MODE", ""), ("PUBLIC_INDEXING_ENABLED", "tru"),
     ("AEAT_PRODUCTION_ENABLED", "tru")],
)
def test_invalid_policy_values_refuse_to_start(name, value):
    result = _run("import config.settings", {**PRODUCTION_ENV, name: value})
    assert result.returncode != 0
    assert name in result.stderr


def _image_check_env() -> dict[str, str]:
    """The ``-e NAME=value`` pairs of ``PROD_ENV`` in docker/image.test.sh, the environment the image is checked with."""
    script = (SAAS_NEXT / "docker" / "image.test.sh").read_text()
    block = re.search(r"^PROD_ENV=\((.*?)^\)", script, re.DOTALL | re.MULTILINE)
    assert block is not None, "docker/image.test.sh has no PROD_ENV=( … ) block"
    return dict(pair.split("=", 1) for pair in re.findall(r'-e "?([A-Z_][A-Z0-9_]*=[^"\s]*)"?', block.group(1)))


def test_the_image_check_environment_is_one_the_settings_start_with():
    """docker/image.test.sh runs ``manage.py check`` with DEBUG=False only in the deploy's build (deploy.yml): a variable
    the settings start requiring outside DEBUG and missing there fails every deploy, while a PR's CI stays green."""
    environment = _image_check_env()
    assert environment["DEBUG"] == "False"
    result = _run("import config.settings", environment)
    assert result.returncode == 0, result.stderr


def test_deployed_optional_policies_are_disabled_by_default():
    assert production("(s.PUBLIC_INDEXING_ENABLED, s.AEAT_PRODUCTION_ENABLED)") == (False, False)


def test_local_django_check_starts_without_policy_variables_or_external_services():
    result = _run(
        "import django\ndjango.setup()\nfrom django.core.management import call_command\ncall_command('check')",
        {"DEBUG": "True", "DJANGO_SETTINGS_MODULE": "config.settings"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("label", ["prod", "pre"])
def test_explicit_deployed_policy_matrix(label):
    live = label == "prod"
    assert production(
        "(s.CACHE_KEY_PREFIX, s.STRIPE_EXPECTED_MODE, s.PUBLIC_INDEXING_ENABLED, s.AEAT_PRODUCTION_ENABLED)",
        ERPLORA_ENVIRONMENT=label,
        CACHE_KEY_PREFIX="saas" if live else "pre-saas",
        STRIPE_EXPECTED_MODE="live" if live else "test",
        PUBLIC_INDEXING_ENABLED=str(live).lower(),
        AEAT_PRODUCTION_ENABLED=str(live).lower(),
    ) == ("saas" if live else "pre-saas", "live" if live else "test", live, live)


# The metric label retains the CloudWatch alarm's prod/pre contract; it controls no policies.


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
