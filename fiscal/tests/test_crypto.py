"""The documents of an authorisation are encrypted at rest (Fernet, ``FISCAL_DOCUMENTS_KEY``): a scan of an
identity card never sits in the database in the clear (RGPD), as in the old product (FISCAL-F03)."""

import pytest
from cryptography.fernet import Fernet

from fiscal import crypto

PDF = b"%PDF-1.7\nthe signed model\n%%EOF"


def test_what_is_encrypted_decrypts_to_the_same_bytes():
    token = crypto.encrypt(PDF)

    assert token != PDF
    assert b"signed model" not in token
    assert crypto.decrypt(token) == PDF


def test_two_encryptions_of_one_document_differ():
    """Fernet carries a random IV: equal documents are not recognisable in the table."""
    assert crypto.encrypt(PDF) != crypto.encrypt(PDF)


def test_it_uses_the_key_of_the_settings(settings):
    key = Fernet.generate_key().decode()
    settings.FISCAL_DOCUMENTS_KEY = key

    token = crypto.encrypt(PDF)

    assert Fernet(key.encode()).decrypt(token) == PDF


def test_a_document_encrypted_with_another_key_is_refused(settings):
    token = Fernet(Fernet.generate_key()).encrypt(PDF)

    with pytest.raises(crypto.Undecryptable):
        crypto.decrypt(token)


def test_bytes_that_are_no_token_are_refused():
    with pytest.raises(crypto.Undecryptable):
        crypto.decrypt(b"not a token")


def test_the_stored_memoryview_of_a_binary_field_decrypts():
    """Postgres hands a ``BinaryField`` back as a ``memoryview``."""
    assert crypto.decrypt(memoryview(crypto.encrypt(PDF))) == PDF


@pytest.mark.parametrize("key", ["", "short", "x" * 44])
def test_a_key_that_is_no_fernet_key_is_named(key):
    assert crypto.key_problem(key)


def test_a_fernet_key_has_no_problem():
    assert crypto.key_problem(Fernet.generate_key().decode()) is None
