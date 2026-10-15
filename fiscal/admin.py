"""Django admin of fiscal: the queue of signed authorisations and the staff's review (plan 2026-10-15,
«Diseño en el SaaS»; the old product's review page, ERPlora/saas ``apps/dashboard/fiscal``, origin/develop).

The list is the queue: business, version, taxpayer, signer, state, when it came and who reviewed it, with a
«Review» link. Nothing is added, deleted nor edited by hand, not even by a superuser: the normal form shows
every field read-only (never the encrypted documents) and saving it changes nothing. The decisions are the
services' (``fiscal.representation.approve|return|withdraw``), taken on the review page as the member of the
staff who clicks, which shows the documents decrypted inline, never cached. Both pages need
``fiscal.change_representationgrant``; ``support`` only sees the list and the rows (data migration ``0002``).
"""

import logging

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.csp import CSP
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.context import OperationContext, Scope
from live.errors import OperationError

from fiscal import crypto, services
from fiscal.models import RepresentationGrant
from fiscal.schemas import ReturnIn, ReviewIn, WithdrawIn

logger = logging.getLogger(__name__)

Status = RepresentationGrant.Status
#: The documents, in the order the review page shows them, with their label.
DOCUMENT_LABELS = {
    "signed_model": gettext_lazy("Signed model (Anexo I)"),
    "id_copy": gettext_lazy("Copy of the signer's identity document"),
    "signature_sample": gettext_lazy("Signature sample"),
    "representation_proof": gettext_lazy("Proof of representation"),
}
#: What the platform's marks in ``reason`` mean (a code, kept as stored), said in the reviewer's language.
REASON_MARKS = {
    RepresentationGrant.SUPERSEDED: gettext_lazy("Replaced by a newer submission before any review"),
    RepresentationGrant.REPLACED_BY_APPROVAL: gettext_lazy("Replaced by a newer approval"),
}


def shown_reason(reason: str) -> str:
    """``reason`` as the review page shows it: a platform's mark in words, the staff's note as written."""
    return str(REASON_MARKS.get(reason, reason))


#: The row's fields the normal form shows, all read-only (the documents are only on the review page).
SHOWN_FIELDS = (
    "hub",
    "version",
    "status",
    "taxpayer_tax_id",
    "taxpayer_name",
    "signer_tax_id",
    "signer_name",
    "signer_document_type",
    "submitted_at",
    "reviewed_at",
    "reviewed_by",
    "note_to_customer",
    "revoked_at",
    "revoked_by",
    "created_at",
    "updated_at",
)


def staff_context(request) -> OperationContext:
    """The member of the staff deciding, as the services see it: their own channel, ``fiscal.manage`` (which
    the services back with ``fiscal.change_representationgrant``) and the admin's language."""
    return OperationContext(
        scope=Scope("user", str(request.user.pk)),
        actor=request.user,
        permissions=frozenset({"fiscal.manage"}),
        language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
        request=request,
    )


@admin.register(RepresentationGrant)
class RepresentationGrantAdmin(admin.ModelAdmin):
    list_display = (
        "hub",
        "version",
        "taxpayer_tax_id",
        "signer_name",
        "status",
        "submitted_at",
        "reviewed_by",
        "review_link",
    )
    list_filter = ("status", "signer_document_type", "submitted_at")
    search_fields = (
        "hub__slug",
        "hub__name",
        "taxpayer_tax_id",
        "taxpayer_name",
        "signer_tax_id",
        "signer_name",
    )
    list_select_related = ("hub", "reviewed_by")
    ordering = ("-submitted_at",)
    date_hierarchy = "submitted_at"
    fields = SHOWN_FIELDS
    readonly_fields = SHOWN_FIELDS

    def get_queryset(self, request):
        # The list and the form never need the encrypted megabytes.
        return super().get_queryset(request).defer(*RepresentationGrant.DOCUMENTS)

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        """Never: the services write the row (a save would at least move ``updated_at``)."""

    def save_related(self, request, form, formsets, change):
        """Never, as ``save_model``."""

    def log_change(self, request, obj, message):
        """Nothing changed by the form, so nothing to log (the decisions are the outbox's trail)."""

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "show_save": False,
            "show_save_and_continue": False,
            "show_save_and_add_another": False,
            "show_delete": False,
        }
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.display(description=gettext_lazy("note to the customer"))
    def note_to_customer(self, obj):
        """``reason`` as the review page says it (``shown_reason``)."""
        return shown_reason(obj.reason)

    @admin.display(description=gettext_lazy("Review"))
    def review_link(self, obj):
        url = reverse("admin:fiscal_representationgrant_review", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, _("Review"))

    def get_urls(self):
        # ``admin_view``: active staff only (else the login page), and ``never_cache`` (``no-store``).
        wrap = self.admin_site.admin_view
        return [
            path(
                "<path:object_id>/review/",
                wrap(self.review_view),
                name="fiscal_representationgrant_review",
            ),
            path(
                "<path:object_id>/review/document/<str:kind>/",
                wrap(self.document_view),
                name="fiscal_representationgrant_document",
            ),
            *super().get_urls(),
        ]

    # --- The review page --------------------------------------------------------------------------------

    def _reviewable(self, request, object_id) -> RepresentationGrant:
        """The grant ``object_id`` if the user may decide on it (403 otherwise; 404 if it does not exist)."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        grant = self.get_object(request, object_id)
        if grant is None:
            raise Http404(_("This authorisation does not exist."))
        if not self.has_change_permission(request, grant):
            raise PermissionDenied
        return grant

    def review_view(self, request, object_id):
        grant = self._reviewable(request, object_id)
        if request.method == "POST":
            self._decide(request, grant)
            return HttpResponseRedirect(request.path)
        documents = [
            {
                "kind": kind,
                "label": label,
                "url": reverse("admin:fiscal_representationgrant_document", args=[grant.pk, kind]),
            }
            for kind, label in DOCUMENT_LABELS.items()
            if self._has_document(grant, kind)
        ]
        versions = list(
            RepresentationGrant.objects.filter(hub_id=grant.hub_id)
            .exclude(pk=grant.pk)
            .defer(*RepresentationGrant.DOCUMENTS)
            .select_related("reviewed_by", "revoked_by")
            .order_by("-version")
        )
        for version in versions:
            version.shown_reason = shown_reason(version.reason)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Review the signed authorisation"),
            "grant": grant,
            "grant_reason": shown_reason(grant.reason),
            "documents": documents,
            "versions": versions,
            "can_decide": grant.status == Status.SUBMITTED,
            "can_withdraw": grant.status == Status.APPROVED,
            "reason_max_length": services.REASON_MAX_LENGTH,
        }
        return TemplateResponse(request, "admin/fiscal/representationgrant/review.html", context)

    @staticmethod
    def _has_document(grant: RepresentationGrant, kind: str) -> bool:
        return RepresentationGrant.objects.filter(pk=grant.pk, **{f"{kind}__isnull": False}).exists()

    def _decide(self, request, grant: RepresentationGrant) -> None:
        """Run the decision the form names through its service; every refusal becomes a message."""
        action = request.POST.get("action", "")
        reason = request.POST.get("reason", "")
        ctx = staff_context(request)
        try:
            if action == "approve":
                services.representation_approve(ctx, ReviewIn(id=grant.pk))
                messages.success(request, _("Approved: ERPlora may now file the business's records."))
            elif action == "return":
                services.representation_return(ctx, ReturnIn(id=grant.pk, reason=reason))
                messages.success(request, _("Returned to the customer with your reason."))
            elif action == "withdraw":
                services.representation_withdraw(ctx, WithdrawIn(id=grant.pk, reason=reason))
                messages.success(request, _("Withdrawn: ERPlora no longer files for the business by it."))
            else:
                messages.error(request, _("Choose approve, return or withdraw."))
        except OperationError as refused:
            # 409 (the state moved on), 422 (the reason) or 403: what the service says, field by field.
            for message in list((refused.fields or {}).values()) or [refused.message]:
                messages.error(request, message)

    # --- A document -------------------------------------------------------------------------------------

    def document_view(self, request, object_id, kind):
        grant = self._reviewable(request, object_id)
        if kind not in DOCUMENT_LABELS:
            raise Http404
        token = (
            RepresentationGrant.objects.filter(pk=grant.pk).values_list(kind, flat=True).first()
        )
        if token is None:
            raise Http404
        try:
            content = crypto.decrypt(token)
        except crypto.Undecryptable:
            logger.error("fiscal.admin.undecryptable grant=%s document=%s", grant.pk, kind)
            response = HttpResponse(
                _("This document cannot be opened with the current key (FISCAL_DOCUMENTS_KEY)."),
                status=500,
                content_type="text/plain; charset=utf-8",
            )
        else:
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{kind}-v{grant.version}.pdf"'
            # Shown framed by the review page, from this origin only (XFrameOptionsMiddleware keeps a set value).
            response["X-Frame-Options"] = "SAMEORIGIN"
            response._csp_config = {**settings.SECURE_CSP, "frame-ancestors": [CSP.SELF]}
        response["X-Content-Type-Options"] = "nosniff"
        return response
