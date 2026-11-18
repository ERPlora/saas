"""The sectors and business types a business is created under."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.queries import known_verticals
from hubs.models.translated_fields import TranslatedFields
from hubs.spanish_copy import spanish_copy_complaint, untranslated_copy_complaint


class TaxonomyEntry(TranslatedFields):
    """A sector or business type: a stable ``code`` and its copy in English and Spanish.

    The Spanish columns are Spanish: accented and translated. The seed is guarded by its tests; this
    ``clean()`` guards the other door, the Django admin. Only the ``_es`` columns are measured: «Menu»
    and «Salon» are English words and belong in the ``_en`` ones.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name_en = models.CharField(_("name (English)"), max_length=200)
    name_es = models.CharField(_("name (Spanish)"), max_length=200, blank=True)
    description_en = models.TextField(_("description (English)"), blank=True)
    description_es = models.TextField(_("description (Spanish)"), blank=True)
    icon = models.CharField(_("icon"), max_length=100, blank=True)
    color = models.CharField(_("colour"), max_length=20, blank=True, help_text=_("Hex colour, e.g. #ff6b35."))
    display_order = models.IntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ["display_order", "code"]

    def __str__(self):
        """In the active language (the staff's in the admin), English when its column is blank."""
        return self.name() or self.code

    def name(self, language: str | None = None) -> str:
        return self.translated("name", language)

    def description(self, language: str | None = None) -> str:
        return self.translated("description", language)

    def clean(self):
        super().clean()
        complaints = {}
        for field in ("name_es", "description_es"):
            text = getattr(self, field)
            if complaint := spanish_copy_complaint(text) or untranslated_copy_complaint(text):
                complaints[field] = complaint
        if complaints:
            raise ValidationError(complaints)


class Sector(TaxonomyEntry):
    """A business sector (hospitality, retail, healthcare…); groups the business types."""

    code = models.SlugField(
        _("code"), max_length=50, unique=True, help_text=_("Stable code used by the API. Never change it.")
    )

    class Meta(TaxonomyEntry.Meta):
        verbose_name = _("sector")
        verbose_name_plural = _("sectors")


class BusinessType(TaxonomyEntry):
    """A business type (bar, restaurant, hair salon…), under its sector.

    ``vertical`` names the template a new hub of this type is cloned from (``hub_template_<vertical>``);
    blank, the hub starts from ``hub_template``, only ``base``.
    """

    code = models.SlugField(
        _("code"), max_length=80, unique=True, help_text=_("Stable code used by the API. Never change it.")
    )
    sector = models.ForeignKey(
        Sector,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="business_types",
        verbose_name=_("sector"),
    )
    vertical = models.CharField(
        _("vertical"),
        max_length=40,
        blank=True,
        default="",
        validators=[
            RegexValidator(
                r"^[a-z][a-z0-9_]*$",
                _("Enter a vertical made of lowercase letters, digits and underscores, starting with a letter."),
            )
        ],
        help_text=_("Template a new hub of this type starts from (hair_salon, restaurant…); blank for none."),
    )

    class Meta(TaxonomyEntry.Meta):
        verbose_name = _("business type")
        verbose_name_plural = _("business types")

    def clean(self):
        """Two business types may not share a visible name in the same language, and a ``vertical`` is
        one an app of the catalog builds (``apps.queries.known_verticals``).

        The sign-up dropdown lists them by name, so two rows called «Peluquería» are two identical
        options. Blank columns are not compared: an untranslated name is empty on many rows.
        """
        complaints = {}
        try:
            super().clean()
        except ValidationError as refused:
            complaints = refused.update_error_dict(complaints)
        others = BusinessType.objects.exclude(pk=self.pk)
        for language, _name in settings.LANGUAGES:
            field = f"name_{language}"
            name = getattr(self, field).strip()
            # Folded in Python: the database's iexact does not fold «PELUQUERÍA» the same way everywhere.
            taken = {other.strip().casefold() for other in others.values_list(field, flat=True)}
            if name and name.casefold() in taken:
                complaints.setdefault(field, []).append(
                    ValidationError(
                        _("Another business type is already called «%(name)s»."),
                        code="duplicate_business_type_name",
                        params={"name": name},
                    )
                )
        if self.vertical and self.vertical not in known_verticals():
            complaints.setdefault("vertical", []).append(
                ValidationError(
                    _("No app of the catalog builds the vertical «%(vertical)s»."),
                    code="unknown_vertical",
                    params={"vertical": self.vertical},
                )
            )
        if complaints:
            raise ValidationError(complaints)
