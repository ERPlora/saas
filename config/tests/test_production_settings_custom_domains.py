import pytest

from config.tests.production_settings import PRODUCTION_ENV, _run, development, production


# A business's own domain: off unless the environment turns it on, as pre and development run it; on, what
# `aws` stacks/prod/custom_domains.tf gives saas and saas-cron is required, so a half-made deployment does not start.

CUSTOM_DOMAINS_ENV = {
    "CUSTOM_DOMAINS_ENABLED": "true",
    "CUSTOM_DOMAINS_LISTENER_ARN": "arn:aws:elasticloadbalancing:eu-west-1:1:listener/app/erplora/a/b",
    "CUSTOM_DOMAINS_TARGET_TEMPLATE": "hub-{hub_id}.erplora.com",
    "CUSTOM_DOMAINS_MAX_CERTIFICATES": "24",
}


@pytest.mark.parametrize("env", [{}, {"CUSTOM_DOMAINS_ENABLED": "false"}], ids=["absent", "false"])
def test_custom_domains_are_off_without_the_variable_and_ask_for_nothing_else(env):
    assert production("s.CUSTOM_DOMAINS_ENABLED", **env) is False
    assert development("s.CUSTOM_DOMAINS_ENABLED", **env) is False


def test_custom_domains_switched_on_read_what_the_infra_gives():
    expression = (
        "(s.CUSTOM_DOMAINS_ENABLED, s.CUSTOM_DOMAINS_LISTENER_ARN, s.CUSTOM_DOMAINS_TARGET_TEMPLATE, "
        "s.CUSTOM_DOMAINS_MAX_CERTIFICATES)"
    )
    assert production(expression, **CUSTOM_DOMAINS_ENV) == (
        True,
        CUSTOM_DOMAINS_ENV["CUSTOM_DOMAINS_LISTENER_ARN"],
        "hub-{hub_id}.erplora.com",
        24,
    )


@pytest.mark.parametrize(
    ("missing", "value"),
    [
        ("CUSTOM_DOMAINS_LISTENER_ARN", ""),
        ("CUSTOM_DOMAINS_TARGET_TEMPLATE", ""),
        ("CUSTOM_DOMAINS_TARGET_TEMPLATE", "hub.erplora.com"),
    ],
)
def test_custom_domains_switched_on_refuse_to_start_without_what_they_need(missing, value):
    result = _run("import config.settings", {**PRODUCTION_ENV, **CUSTOM_DOMAINS_ENV, missing: value})

    assert result.returncode != 0
    assert missing in result.stderr
