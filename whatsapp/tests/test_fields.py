"""WHATSAPP-G04 · The encrypted field: what the model reads is the secret, what the column holds is its token."""

import logging

from whatsapp import crypto
from whatsapp.fields import EncryptedTextField
from whatsapp.tests.conftest import OTHER_FERNET_KEY

FIELD = EncryptedTextField()


def test_a_value_goes_in_as_a_token_and_comes_back(whatsapp_on):
    stored = FIELD.get_prep_value("EAAG-token")

    assert stored.startswith("gAAAA") and "EAAG" not in stored
    assert FIELD.from_db_value(stored, None, None) == "EAAG-token"


def test_empty_stays_empty(whatsapp_on):
    assert FIELD.get_prep_value("") == ""
    assert FIELD.get_prep_value(None) == ""
    assert FIELD.from_db_value("", None, None) == ""
    assert FIELD.from_db_value(None, None, None) == ""


def test_a_token_no_key_opens_reads_empty_and_says_so(whatsapp_on, settings, caplog):
    """A lost key must not crash every page that loads the row (the admin's list): the credential reads empty,
    which the doors treat as «not connected», and the log says why at ERROR."""
    settings.FERNET_KEY = OTHER_FERNET_KEY
    token = crypto.encrypt("EAAG-x")
    settings.FERNET_KEY = "mbAv33BqhZbROx9FgnZVR3XPEUopApIq3G-xQR4E58w="

    with caplog.at_level(logging.ERROR, logger="whatsapp.fields"):
        assert FIELD.from_db_value(token, None, None) == ""

    assert "whatsapp.crypto.undecryptable" in caplog.text
    assert "EAAG" not in caplog.text
