"""``fiscal.E001``: the key that encrypts the documents is a Fernet key. A bad one would only fail at the first
upload (every customer's), so ``check`` (and ``check --deploy``) says it before."""

from cryptography.fernet import Fernet
from django.core import checks

from fiscal.checks import check_documents_key


def test_a_fernet_key_passes(settings):
    settings.FISCAL_DOCUMENTS_KEY = Fernet.generate_key().decode()

    assert check_documents_key(None) == []


def test_the_local_key_of_the_settings_passes():
    assert check_documents_key(None) == []


def test_a_key_that_is_no_fernet_key_is_an_error(settings):
    settings.FISCAL_DOCUMENTS_KEY = "not-a-fernet-key"

    (error,) = check_documents_key(None)

    assert (error.id, error.level) == ("fiscal.E001", checks.ERROR)
    assert "FISCAL_DOCUMENTS_KEY" in error.msg


def test_the_check_is_registered():
    assert check_documents_key in checks.registry.registry.get_checks()
