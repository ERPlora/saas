"""A text column whose value is kept encrypted (``assistant.crypto``): the model reads the provider's key, the
column its Fernet token (ASSISTANT-G26; saas#528).

A token no live key opens reads as empty and is logged at ERROR (``assistant.crypto.undecryptable``): loading the row
(the admin's list, the turn's route) never crashes, and an empty key is a provider without a usable key. The value
and the token are never logged. Lookups on the column match nothing (each token is different): nothing filters by it.
``rotate_encryption_keys`` finds every column of this class (``assistant.rotation``).
"""

import logging

from django.db import models

from assistant import crypto

logger = logging.getLogger(__name__)


class EncryptedTextField(models.TextField):
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return ""
        return crypto.encrypt(str(value))

    def from_db_value(self, value, expression, connection):
        if not value:
            return ""
        try:
            return crypto.decrypt(value)
        except (crypto.Undecryptable, crypto.NotConfigured) as problem:
            logger.error("assistant.crypto.undecryptable %s", problem)
            return ""
