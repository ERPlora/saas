"""WHATSAPP-G04 · The Meta credentials of a number are encrypted at rest (Fernet), with a key rotation."""

import pytest

from whatsapp import crypto
from whatsapp.tests.conftest import FERNET_KEY, OTHER_FERNET_KEY


def test_a_secret_comes_back_from_its_token(meta):
    token = crypto.encrypt("EAAG-business-token")

    assert token != "EAAG-business-token"
    assert "EAAG" not in token
    assert crypto.decrypt(token) == "EAAG-business-token"


def test_the_previous_key_still_opens_what_it_closed(meta, settings):
    settings.FERNET_KEY = OTHER_FERNET_KEY
    old = crypto.encrypt("EAAG-old")

    settings.FERNET_KEY = FERNET_KEY
    settings.FERNET_KEY_PREVIOUS = OTHER_FERNET_KEY

    assert crypto.decrypt(old) == "EAAG-old"
    # What is written now is the current key's.
    settings.FERNET_KEY_PREVIOUS = ""
    assert crypto.decrypt(crypto.encrypt("EAAG-new")) == "EAAG-new"


def test_a_token_of_another_key_is_undecryptable(meta, settings):
    settings.FERNET_KEY = OTHER_FERNET_KEY
    token = crypto.encrypt("EAAG-x")
    settings.FERNET_KEY = FERNET_KEY

    with pytest.raises(crypto.Undecryptable):
        crypto.decrypt(token)


def test_without_a_key_nothing_is_encrypted(meta, settings):
    settings.FERNET_KEY = ""

    assert crypto.configured() is False
    with pytest.raises(crypto.NotConfigured):
        crypto.encrypt("EAAG-x")


def test_key_problem_names_a_bad_key():
    assert crypto.key_problem(FERNET_KEY) is None
    assert crypto.key_problem("not-a-key") is not None
