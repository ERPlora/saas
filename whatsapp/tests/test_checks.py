"""``whatsapp.E001`` (a ``FERNET_KEY`` that is no Fernet key) and ``whatsapp.I001`` (WhatsApp is off).

WhatsApp missing a setting fails visibly where it is used (503 at the webhook, ``whatsapp.not_configured`` at
the doors); ``check`` says it before, as information, so it never stops a deploy of everything else (the deploy
fails at WARNING; the secrets live in the infrastructure's repo, PLAN-SAAS «Secretos en AWS»), as
``accounts.I001`` does for Google.
"""

from django.core import checks

from whatsapp.checks import check_fernet_key, check_meta_settings
from whatsapp.tests.conftest import FERNET_KEY


def test_a_fernet_key_passes(settings):
    settings.FERNET_KEY = FERNET_KEY

    assert check_fernet_key(None) == []


def test_no_key_is_no_error_here(settings):
    settings.FERNET_KEY = ""

    assert check_fernet_key(None) == []


def test_a_key_that_is_no_fernet_key_is_an_error(settings):
    settings.FERNET_KEY = "not-a-fernet-key"

    (error,) = check_fernet_key(None)

    assert (error.id, error.level) == ("whatsapp.E001", checks.ERROR)
    assert "FERNET_KEY" in error.msg


def test_a_complete_configuration_says_nothing(whatsapp_on):
    assert check_meta_settings(None) == []


def test_a_missing_setting_is_information_naming_it(whatsapp_on, settings):
    settings.WHATSAPP_APP_SECRET = ""
    settings.FERNET_KEY = ""

    (info,) = check_meta_settings(None)

    # Below WARNING: `check --deploy --fail-level WARNING` (the deploy) still passes.
    assert (info.id, info.level) == ("whatsapp.I001", checks.INFO)
    assert "WHATSAPP_APP_SECRET" in info.msg and "FERNET_KEY" in info.msg
    assert "WHATSAPP_APP_ID" not in info.msg


def test_a_return_page_that_is_not_this_site_s_is_information_naming_it(whatsapp_on, settings):
    settings.WHATSAPP_REDIRECT_URI = "http://erplora.com/whatsapp/return"
    settings.DEBUG = False

    (info,) = check_meta_settings(None)

    assert (info.id, info.level) == ("whatsapp.I001", checks.INFO)
    assert "WHATSAPP_REDIRECT_URI" in info.msg


def test_both_checks_are_registered():
    registered = checks.registry.registry.get_checks()

    assert check_fernet_key in registered and check_meta_settings in registered
