"""The key of the credentials (``assistant.crypto``): Fernet with ``FERNET_KEY``, the previous key only to read.

The same scheme as WhatsApp's Meta credentials (``whatsapp.crypto``) and the old product's ``fernet_fields``
(saas#528): the database only ever holds the token.
"""

import pytest
from cryptography.fernet import Fernet

from assistant import crypto
from assistant.tests.conftest import FERNET_KEY, OTHER_FERNET_KEY


def test_a_value_comes_back_from_its_token_and_the_token_hides_it():
    token = crypto.encrypt("sk-secret-value")

    assert "sk-secret-value" not in token
    assert crypto.decrypt(token) == "sk-secret-value"


def test_the_token_is_written_with_the_current_key(settings):
    token = crypto.encrypt("sk-secret-value")

    assert Fernet(FERNET_KEY.encode()).decrypt(token.encode()) == b"sk-secret-value"


def test_during_a_rotation_the_previous_key_still_reads(settings):
    old_token = crypto.encrypt("sk-secret-value")
    settings.FERNET_KEY = OTHER_FERNET_KEY
    settings.FERNET_KEY_PREVIOUS = FERNET_KEY

    assert crypto.decrypt(old_token) == "sk-secret-value"


def test_a_token_no_live_key_opens_is_undecryptable(settings):
    old_token = crypto.encrypt("sk-secret-value")
    settings.FERNET_KEY = OTHER_FERNET_KEY

    with pytest.raises(crypto.Undecryptable):
        crypto.decrypt(old_token)


def test_without_a_key_nothing_is_kept(settings):
    settings.FERNET_KEY = ""

    assert crypto.configured() is False
    with pytest.raises(crypto.NotConfigured):
        crypto.encrypt("sk-secret-value")


def test_a_key_that_is_no_fernet_key_is_not_configured(settings):
    settings.FERNET_KEY = "not-a-key"

    assert crypto.configured() is False
    assert crypto.key_problem("not-a-key")


def test_rotate_writes_an_old_token_again_with_the_current_key(settings):
    old_token = crypto.encrypt("sk-secret-value")
    settings.FERNET_KEY = OTHER_FERNET_KEY
    settings.FERNET_KEY_PREVIOUS = FERNET_KEY

    assert crypto.is_current(old_token) is False
    new_token = crypto.rotate(old_token)

    assert crypto.is_current(new_token) is True
    settings.FERNET_KEY_PREVIOUS = ""
    assert crypto.decrypt(new_token) == "sk-secret-value"


def test_rotate_refuses_a_token_no_live_key_opens(settings):
    old_token = crypto.encrypt("sk-secret-value")
    settings.FERNET_KEY = OTHER_FERNET_KEY

    with pytest.raises(crypto.Undecryptable):
        crypto.rotate(old_token)
