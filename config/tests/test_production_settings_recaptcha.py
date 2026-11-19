import pytest

from config.tests.production_settings import PRODUCTION_ENV, TASKS, _run, development, production


# reCAPTCHA Enterprise (live.recaptcha), switched OFF by default: the WAF on the ALB filters the suspicious traffic and
# the attempt limits stop the brute force. RECAPTCHA_ENABLED=True switches it back on, in production as in
# development, and then both keys are
# required (the process refuses to start without them). The test run never checks (config/settings_pytest.py). The
# minimum score and the endpoint come from the environment.

RECAPTCHA = "s.LIVE['recaptcha']"
RECAPTCHA_KEYS = {"RECAPTCHA_SITE_KEY": "dev-site-key", "RECAPTCHA_API_KEY": "dev-api-key"}
#: Every source Google's reCAPTCHA adds to a policy (live.recaptcha.with_recaptcha), and its Trusted Types policy.
GOOGLE_RECAPTCHA_SOURCES = (
    "https://www.google.com/recaptcha/",
    "https://www.gstatic.com/recaptcha/",
    "https://recaptcha.google.com/recaptcha/",
    "goog#html",
)
SECURE_CSP_SOURCES = "sorted({str(source) for sources in s.SECURE_CSP.values() for source in sources})"


def test_production_leaves_recaptcha_off_by_default_even_with_its_keys():
    assert production(RECAPTCHA)["enabled"] is False


def test_production_switched_on_checks_every_public_form_with_recaptcha():
    assert production(RECAPTCHA, RECAPTCHA_ENABLED="True") == {
        "enabled": True,
        "project": "erplora",
        "site_key": "prod-recaptcha-site-key",
        "api_key": "prod-recaptcha-api-key",
        "min_score": 0.5,
        "endpoint": None,
    }


def test_production_starts_without_recaptcha_keys_while_it_is_off():
    env = {key: value for key, value in PRODUCTION_ENV.items() if not key.startswith("RECAPTCHA_")}

    result = _run(f"import config.settings as s\nprint({RECAPTCHA}['enabled'])", env)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.parametrize("missing", ["RECAPTCHA_SITE_KEY", "RECAPTCHA_API_KEY"])
@pytest.mark.parametrize("how", ["absent", "empty"])
def test_production_switched_on_refuses_to_start_without_a_recaptcha_key(missing, how):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != missing}
    env["RECAPTCHA_ENABLED"] = "True"
    if how == "empty":
        env[missing] = ""

    result = _run("import config.settings", env)

    assert result.returncode != 0
    assert missing in result.stderr


@pytest.mark.parametrize("task", sorted(TASKS))
def test_every_saas_task_starts_with_recaptcha_off(task):
    result = _run(f"import config.settings as s\nprint({RECAPTCHA}['enabled'])", TASKS[task])

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.parametrize("task", sorted(TASKS))
def test_every_saas_task_may_switch_recaptcha_on_with_its_keys(task):
    result = _run(f"import config.settings as s\nprint({RECAPTCHA}['enabled'])", {**TASKS[task], "RECAPTCHA_ENABLED": "True"})

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_production_switched_off_names_nothing_of_google_recaptcha_in_its_csp():
    """No script, frame nor connection of Google's reCAPTCHA and no `goog#html` Trusted Types policy."""
    sources = production(SECURE_CSP_SOURCES)

    assert not [source for source in sources if source in GOOGLE_RECAPTCHA_SOURCES or "recaptcha" in source]


def test_production_switched_on_admits_google_recaptcha_in_its_csp():
    sources = production(SECURE_CSP_SOURCES, RECAPTCHA_ENABLED="True")

    assert set(GOOGLE_RECAPTCHA_SOURCES) <= set(sources)


def test_the_minimum_score_and_the_project_come_from_the_environment():
    conf = production(RECAPTCHA, RECAPTCHA_ENABLED="True", RECAPTCHA_MIN_SCORE="0.7", RECAPTCHA_PROJECT="erplora-pre")

    assert (conf["min_score"], conf["project"]) == (0.7, "erplora-pre")


@pytest.mark.parametrize("score", ["1.5", "-0.1", "high"])
def test_a_minimum_score_outside_zero_to_one_refuses_to_start(score):
    result = _run("import config.settings", {**PRODUCTION_ENV, "RECAPTCHA_MIN_SCORE": score})

    assert result.returncode != 0
    assert "RECAPTCHA_MIN_SCORE" in result.stderr


def test_the_assessments_may_go_to_another_endpoint():
    url = "http://127.0.0.1:8018/v1/projects/erplora/assessments"

    assert production(RECAPTCHA, RECAPTCHA_ENABLED="True", RECAPTCHA_ENDPOINT=url)["endpoint"] == url


def test_development_without_keys_checks_nothing():
    assert development(RECAPTCHA)["enabled"] is False


def test_development_with_both_keys_still_checks_nothing_until_switched_on():
    assert development(RECAPTCHA, **RECAPTCHA_KEYS)["enabled"] is False


def test_development_switched_on_with_both_keys_checks_the_forms():
    conf = development(RECAPTCHA, **RECAPTCHA_KEYS, RECAPTCHA_ENABLED="True")

    assert (conf["enabled"], conf["site_key"], conf["api_key"]) == (True, "dev-site-key", "dev-api-key")


def test_development_switched_on_without_keys_refuses_to_start():
    result = _run("import config.settings", {"DEBUG": "True", "RECAPTCHA_ENABLED": "True"})

    assert result.returncode != 0
    assert "RECAPTCHA_SITE_KEY" in result.stderr


def test_the_test_run_never_checks_whatever_the_dotenv_says():
    from django.conf import settings

    assert settings.LIVE["recaptcha"]["enabled"] is False
