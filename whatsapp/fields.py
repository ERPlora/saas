"""A text column whose value is kept encrypted (``whatsapp.crypto``): the model reads the secret, the column its
Fernet token. Used for Meta's business token and the number's PIN (WHATSAPP-G04; saas#1906).

A token no live key opens reads as empty and is logged at ERROR (``whatsapp.crypto.undecryptable``): loading the
row (the admin's list, a sweep) never crashes, and every door treats an empty credential as «not connected».
The value is never logged. Lookups on the column match nothing (each token is different): nothing filters by it.
"""

import logging

from django.db import models

from whatsapp import crypto

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
            logger.error("whatsapp.crypto.undecryptable %s", problem)
            return ""
