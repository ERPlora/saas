"""System checks of accounts: a development server without Google credentials says so."""

from django.core import checks

from accounts.checks import google_sign_in


def test_without_credentials_it_says_the_google_button_is_hidden():
    (message,) = google_sign_in(app_configs=None)

    assert message.id == "accounts.I001"
    assert message.level == checks.INFO
    assert "GOOGLE_OAUTH_CLIENT_ID" in message.msg
    assert "GOOGLE_OAUTH_CLIENT_SECRET" in message.msg


def test_with_credentials_there_is_nothing_to_say(google):
    assert google_sign_in(app_configs=None) == []


def test_it_runs_with_the_project_checks():
    assert "accounts.I001" in [message.id for message in checks.run_checks(include_deployment_checks=False)]
