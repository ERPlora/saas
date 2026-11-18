"""The copy of a row in one column per language, shared by the plans and the taxonomy."""

from django.conf import settings
from django.db import models
from django.utils.translation import get_language


class TranslatedFields(models.Model):
    """A row whose copy lives in one column per language: ``<field>_en`` (the source), ``<field>_es``."""

    class Meta:
        abstract = True

    def translated(self, field: str, language: str | None = None):
        """``field`` in ``language`` (the active one by default); English when blank or unknown."""
        code = (language or get_language() or settings.LANGUAGE_CODE).split("-")[0].lower()
        value = getattr(self, f"{field}_{code}", None) if code in dict(settings.LANGUAGES) else None
        return value or getattr(self, f"{field}_{settings.LANGUAGE_CODE}")
