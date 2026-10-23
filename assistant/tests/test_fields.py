"""The encrypted column of a provider's key (``assistant.fields.EncryptedTextField``; saas#528 of the old product:
the keys lived in the clear in Aurora and in every ``pg_dump``).

The model reads the key, the column holds its Fernet token; a token no live key opens reads as empty (the key is
«unreadable», never a crash of the admin's list) and says so in the log without the token.
"""

import logging

import pytest
from django.db import connection

from assistant.models import AIProviderCredential
from assistant.tests.conftest import API_KEY, OTHER_FERNET_KEY

pytestmark = pytest.mark.django_db


def raw_column(credential) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT api_key FROM assistant_aiprovidercredential WHERE id = %s", [credential.pk])
        return cursor.fetchone()[0]


def test_the_column_holds_a_token_never_the_key(provider):
    credential = AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY)

    stored = raw_column(credential)
    assert API_KEY not in stored
    assert API_KEY[-4:] not in stored
    assert AIProviderCredential.objects.get(pk=credential.pk).api_key == API_KEY


def test_a_key_no_live_key_opens_reads_as_empty_and_is_logged(provider, settings, caplog):
    credential = AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY)
    settings.FERNET_KEY = OTHER_FERNET_KEY

    with caplog.at_level(logging.ERROR, logger="assistant.fields"):
        assert AIProviderCredential.objects.get(pk=credential.pk).api_key == ""

    assert "assistant.crypto.undecryptable" in caplog.text
    assert raw_column(credential) not in caplog.text


def test_an_empty_key_stays_empty(provider):
    credential = AIProviderCredential.objects.create(provider=provider, label="default", api_key="")

    assert raw_column(credential) == ""
