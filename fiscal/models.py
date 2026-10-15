"""The authorisation a business signs so ERPlora files its VeriFactu records, as each version arrived and was
reviewed (plan 2026-10-15; PLAN-SAAS §4, round 2026-10-15).

Ported in behaviour from ERPlora/saas ``apps/dashboard/fiscal/models.py`` (origin/develop,
``RepresentationGrant``), reduced to what the review needs: keyed by the business (``hub``) instead of the
taxpayer's NIF, because the Hub reads «validated or not» per business in its snapshot; no review tokens,
mail, S3 archive nor signature detection (plan, «Fuera de alcance»). The figure is the «otorgamiento de la
representación directa» of the Anexo I of the AEAT's agreement 017 (collaboration social): in code,
``representation``, the Hub's word.

- ``version`` grows per business and is never reused (``UniqueConstraint``): it names one document for ever.
- ``status``: ``submitted`` (waiting for the staff), ``approved`` (ERPlora may file for it), ``returned`` (the
  staff sent it back, ``reason`` says why; also a submission a newer one replaced, ``SUPERSEDED``) and
  ``revoked`` (an approval withdrawn by the staff or replaced by a newer approval). «none» is no row at all.
- At most one ``approved`` per business (partial ``UniqueConstraint``).
- The four documents are PDFs, encrypted with ``fiscal.crypto`` (the database never holds them in the clear).
- Only ``fiscal.services`` writes them; the admin shows them read-only and decides through the services.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from hubs.models import Hub


class RepresentationGrant(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("Under review")
        APPROVED = "approved", _("Approved")
        RETURNED = "returned", _("Returned")
        REVOKED = "revoked", _("Withdrawn")

    class DocumentType(models.TextChoices):
        DNI = "dni", _("DNI")
        NIE = "nie", _("NIE")

    #: ``reason`` of a submission a newer one replaced before anybody reviewed it: a code, not a sentence
    #: (the old product's ``SUPERSEDED_REASON``), never shown to the customer as a reason.
    SUPERSEDED = "superseded_by_new_upload"
    #: ``reason`` of an approval a newer approval replaced (the old product's «Superseded by a new grant.»).
    REPLACED_BY_APPROVAL = "Superseded by a new approval."
    #: The four documents, by field: the signed Anexo I, the signer's identity document, a sample of the
    #: signature (with a NIE) and the proof that the signer represents a company.
    DOCUMENTS = ("signed_model", "id_copy", "signature_sample", "representation_proof")

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    hub = models.ForeignKey(
        Hub,
        on_delete=models.CASCADE,
        related_name="representation_grants",
        verbose_name=_("business"),
    )
    version = models.PositiveIntegerField(_("version"))
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.SUBMITTED,
        db_index=True,
    )
    taxpayer_tax_id = models.CharField(_("taxpayer's tax ID"), max_length=16)
    taxpayer_name = models.CharField(_("taxpayer"), max_length=200, blank=True)
    signer_tax_id = models.CharField(_("signer's tax ID"), max_length=16)
    signer_name = models.CharField(_("signer"), max_length=200)
    signer_document_type = models.CharField(
        _("signer's identity document"), max_length=3, choices=DocumentType.choices
    )
    signed_model = models.BinaryField(_("signed model (encrypted)"))
    id_copy = models.BinaryField(_("copy of the identity document (encrypted)"))
    signature_sample = models.BinaryField(
        _("signature sample (encrypted)"), null=True, blank=True
    )
    representation_proof = models.BinaryField(
        _("proof of representation (encrypted)"), null=True, blank=True
    )
    submitted_at = models.DateTimeField(_("submitted at"))
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("reviewed by"),
    )
    #: The staff's note to the customer: why it was returned or withdrawn.
    reason = models.CharField(
        _("note to the customer"), max_length=500, blank=True, default=""
    )
    revoked_at = models.DateTimeField(_("withdrawn at"), null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("withdrawn by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["hub", "-version"]
        verbose_name = _("signed authorisation")
        verbose_name_plural = _("signed authorisations")
        constraints = [
            models.UniqueConstraint(
                fields=["hub", "version"], name="fiscal_grant_one_version_per_hub"
            ),
            models.UniqueConstraint(
                fields=["hub"],
                condition=Q(status="approved"),
                name="fiscal_grant_one_approved_per_hub",
            ),
        ]

    def __str__(self):
        return f"{self.hub} · v{self.version} · {self.taxpayer_tax_id}"

    @classmethod
    def latest_for(cls, hub_id) -> RepresentationGrant | None:
        """The newest version the business sent, whatever became of it."""
        return cls.objects.filter(hub_id=hub_id).order_by("-version").first()

    @classmethod
    def approved_for(cls, hub_id) -> RepresentationGrant | None:
        """The authorisation in force for the business, if any."""
        return cls.objects.filter(hub_id=hub_id, status=cls.Status.APPROVED).first()

    @property
    def changed_at(self):
        """When it last changed: sent, reviewed or withdrawn, the latest."""
        return max(
            moment
            for moment in (self.submitted_at, self.reviewed_at, self.revoked_at)
            if moment
        )
