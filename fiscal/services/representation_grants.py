"""A business's authorisation: the Hub sends it and a person of the staff approves it, returns it or withdraws it."""

from functools import partial
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import INTERNAL, operation
from live.outbox import record_event

from base.refusals import fields_refused
from billing.nif import is_legal_person_nif, is_spanish_tax_id, normalise_nif
from fiscal import crypto, emails, events
from fiscal.documents import DocumentRejected, decode_pdf
from fiscal.models import RepresentationGrant
from fiscal.schemas import (
    TAX_ID_MAX_LENGTH,
    RepresentationSubmitIn,
    RepresentationSubmitOut,
    ReturnIn,
    ReviewIn,
    ReviewOut,
    WithdrawIn,
)
from fiscal.services.business_notices import tell_the_business
from fiscal.services.staff_gate import _staff_with
from hubs.queries import access_control
from hubs.services import hub_push
from hubs.models import Hub

Status = RepresentationGrant.Status
#: What the reviewer's note may hold (``RepresentationGrant.reason``).
REASON_MAX_LENGTH = 500
#: The Django permission that lets a member of the staff decide (``fiscal.admin``'s review page asks it too).
REVIEW_PERMISSION = "fiscal.change_representationgrant"


# --- The Hub sends an authorisation ---------------------------------------------------------------------


@operation(
    "fiscal.representation.submit",
    kind="command",
    permission="fiscal.manage",
    input=RepresentationSubmitIn,
    output=RepresentationSubmitOut,
    ai=INTERNAL,  # hub
)
def representation_submit(ctx: OperationContext, data: RepresentationSubmitIn) -> dict:
    """``POST /internal/hubs/{id}/representation``: file the business's authorisation for review.

    Only the platform runs it (``fiscal.internal``, in the owner's channel). The rules of the documents answer
    422 with a ``fiscal.*`` code; a business that does not exist or was deleted, or ERPlora's own (represented by
    nobody), 404. The waiting one it replaces is returned with ``SUPERSEDED``; an approved one stays in force until
    a person approves this one.
    """
    if ctx.actor != "system":
        raise PermissionDenied(
            _("Only the Hub sends a business's authorisation."), code="internal_command"
        )
    with translation.override(ctx.language):
        checked = _checked(data)
    hub = (
        Hub.objects.select_for_update()
        .filter(pk=data.hub_id, is_platform=False)
        .exclude(status__in=[Hub.Status.DELETING, Hub.Status.DELETED])
        .first()
    )
    if hub is None:
        raise access_control.not_found()
    now = timezone.now()
    # Under the business's lock, so two uploads never get one version; every row counts, so a version
    # names one document for ever.
    last = (
        RepresentationGrant.objects.filter(hub=hub).aggregate(last=Max("version"))[
            "last"
        ]
        or 0
    )
    RepresentationGrant.objects.filter(hub=hub, status=Status.SUBMITTED).update(
        status=Status.RETURNED, reason=RepresentationGrant.SUPERSEDED, updated_at=now
    )
    grant = RepresentationGrant.objects.create(
        hub=hub,
        version=last + 1,
        status=Status.SUBMITTED,
        submitted_at=now,
        **checked,
    )
    _stepped(ctx, events.REPRESENTATION_SUBMITTED, grant)
    return {
        "status": grant.status,
        "version": grant.version,
        "submitted_at": grant.submitted_at,
    }


def _checked(data: RepresentationSubmitIn) -> dict[str, Any]:  # noqa: C901
    """The row's fields from ``data`` (tax ids normalised, documents encrypted), or ``InvalidPayload`` naming
    every broken rule, with the first one's code."""
    problems: list[tuple[str, str, str]] = []  # (field, code, message)
    taxpayer = normalise_nif(data.taxpayer_tax_id)
    if not is_spanish_tax_id(taxpayer):
        problems.append(
            (
                "taxpayer_tax_id",
                "fiscal.taxpayer_tax_id_invalid",
                _("Enter the Spanish tax ID (NIF) of whoever owes the tax."),
            )
        )
    signer_message = _("Say who signs the authorisation: their name and tax ID.")
    # Normalised before it is judged: «--» leaves nothing, and the column keeps TAX_ID_MAX_LENGTH.
    signer_tax_id = normalise_nif(data.signer_tax_id)
    if not signer_tax_id or len(signer_tax_id) > TAX_ID_MAX_LENGTH:
        problems.append(("signer_tax_id", "fiscal.signer_required", signer_message))
    if not data.signer_name.strip():
        problems.append(("signer_name", "fiscal.signer_required", signer_message))
    document_type = data.signer_document_type.strip().lower()
    if document_type not in RepresentationGrant.DocumentType.values:
        problems.append(
            (
                "signer_document_type",
                "fiscal.document_type_invalid",
                _("The signer's identity document is a DNI or a NIE."),
            )
        )
    required = {
        "signed_model": ("fiscal.signed_model_required", _("Attach the signed model.")),
        "id_copy": (
            "fiscal.id_copy_required",
            _("Attach a copy of the signer's identity document."),
        ),
    }
    if document_type == RepresentationGrant.DocumentType.NIE:
        required["signature_sample"] = (
            "fiscal.signature_sample_required",
            _("With a NIE, attach a sample of the signature."),
        )
    if is_legal_person_nif(taxpayer):
        required["representation_proof"] = (
            "fiscal.representation_proof_required",
            _(
                "For a company, attach the document that proves the signer represents it."
            ),
        )
    stored: dict[str, bytes | None] = {}
    for name in RepresentationGrant.DOCUMENTS:
        value = getattr(data.documents, name)
        stored[name] = None
        if not value.strip():
            if name in required:
                problems.append((f"documents.{name}", *required[name]))
            continue
        try:
            stored[name] = crypto.encrypt(decode_pdf(value))
        except DocumentRejected as refused:
            problems.append(
                (f"documents.{name}", *_document_refusal(name, refused.code))
            )
    if problems:
        raise fields_refused(
            {field: message for field, _code, message in problems},
            code=problems[0][1],
        )
    return {
        "taxpayer_tax_id": taxpayer,
        "taxpayer_name": data.taxpayer_name.strip(),
        "signer_tax_id": signer_tax_id,
        "signer_name": data.signer_name.strip(),
        "signer_document_type": document_type,
        **stored,
    }


def _document_refusal(name: str, code: str) -> tuple[str, str]:
    if code == "too_large":
        return "fiscal.document_too_large", _("Each document may be 5 MB at most.")
    if name == "signed_model":
        return "fiscal.signed_model_not_pdf", _("The signed model must be a PDF.")
    return "fiscal.document_not_pdf", _("This document must be a PDF.")


# --- The staff decide -------------------------------------------------------------------------------------


@operation(
    "fiscal.representation.approve",
    kind="command",
    permission="fiscal.manage",
    input=ReviewIn,
    output=ReviewOut,
    ai=INTERNAL,  # staff
)
def representation_approve(ctx: OperationContext, data: ReviewIn) -> dict:
    """A person of the staff accepts the documents: the authorisation is in force and replaces the one that
    was (withdrawn, «Superseded by a new approval.»). Only a waiting one (409 ``fiscal.not_pending``)."""
    reviewer = _reviewer(ctx)
    grant = _locked(data.id)
    if grant.status != Status.SUBMITTED:
        raise _not_pending()
    now = timezone.now()
    # Before this one is approved: at most one approved per business (a constraint checked per row).
    RepresentationGrant.objects.filter(
        hub_id=grant.hub_id, status=Status.APPROVED
    ).update(
        status=Status.REVOKED,
        revoked_at=now,
        revoked_by=reviewer,
        reason=RepresentationGrant.REPLACED_BY_APPROVAL,
        updated_at=now,
    )
    grant.status = Status.APPROVED
    grant.reviewed_at = now
    grant.reviewed_by = reviewer
    grant.reason = ""
    grant.save(
        update_fields=["status", "reviewed_at", "reviewed_by", "reason", "updated_at"]
    )
    _stepped(ctx, events.REPRESENTATION_APPROVED, grant)
    return _decided(grant)


@operation(
    "fiscal.representation.return",
    kind="command",
    permission="fiscal.manage",
    input=ReturnIn,
    output=ReviewOut,
    ai=INTERNAL,  # staff
)
def representation_return(ctx: OperationContext, data: ReturnIn) -> dict:
    """A person of the staff sends the documents back, saying why (the customer reads it). Only a waiting one;
    the authorisation in force, if any, stays."""
    reviewer = _reviewer(ctx)
    with translation.override(ctx.language):
        reason = _reason(data.reason)
    grant = _locked(data.id)
    if grant.status != Status.SUBMITTED:
        raise _not_pending()
    grant.status = Status.RETURNED
    grant.reviewed_at = timezone.now()
    grant.reviewed_by = reviewer
    grant.reason = reason
    grant.save(
        update_fields=["status", "reviewed_at", "reviewed_by", "reason", "updated_at"]
    )
    _stepped(ctx, events.REPRESENTATION_RETURNED, grant)
    return _decided(grant)


@operation(
    "fiscal.representation.withdraw",
    kind="command",
    permission="fiscal.manage",
    input=WithdrawIn,
    output=ReviewOut,
    ai=INTERNAL,  # staff
)
def representation_withdraw(ctx: OperationContext, data: WithdrawIn) -> dict:
    """A person of the staff withdraws an approval, saying why: ERPlora no longer files for the business by
    this authorisation (the Hub reads ``revoked``). Only an approved one (409 ``fiscal.not_approved``)."""
    reviewer = _reviewer(ctx)
    with translation.override(ctx.language):
        reason = _reason(data.reason)
    grant = _locked(data.id)
    if grant.status != Status.APPROVED:
        raise Conflict(
            _("Only an approved authorisation can be withdrawn."),
            code="fiscal.not_approved",
        )
    grant.status = Status.REVOKED
    grant.revoked_at = timezone.now()
    grant.revoked_by = reviewer
    grant.reason = reason
    grant.save(
        update_fields=["status", "revoked_at", "revoked_by", "reason", "updated_at"]
    )
    _stepped(ctx, events.REPRESENTATION_REVOKED, grant)
    return _decided(grant)


def _reviewer(ctx: OperationContext):
    """The member of the staff running ``ctx``, who may decide (``REVIEW_PERMISSION``); anybody else, 403."""
    return _staff_with(ctx, REVIEW_PERMISSION)


def _locked(grant_id: UUID) -> RepresentationGrant:
    """The grant ``grant_id``, locked after its business's row (one decision per business at a time)."""
    hub_id = (
        RepresentationGrant.objects.filter(pk=grant_id)
        .values_list("hub_id", flat=True)
        .first()
    )
    if hub_id is None:
        raise NotFound(_("This authorisation does not exist."))
    Hub.objects.select_for_update().filter(pk=hub_id).first()
    return RepresentationGrant.objects.select_for_update().get(pk=grant_id)


def _reason(value: str) -> str:
    reason = value.strip()
    if not reason:
        raise fields_refused(
            {"reason": _("Write the reason: the customer reads it.")},
            code="fiscal.reason_required",
        )
    if len(reason) > REASON_MAX_LENGTH:
        raise fields_refused(
            {
                "reason": _("The reason may be %(count)d characters at most.")
                % {"count": REASON_MAX_LENGTH}
            },
            code="fiscal.reason_too_long",
        )
    return reason


def _not_pending() -> Conflict:
    return Conflict(
        _("Only an authorisation under review can be approved or returned."),
        code="fiscal.not_pending",
    )


def _decided(grant: RepresentationGrant) -> dict:
    return {"id": grant.id, "status": grant.status, "version": grant.version}


def _stepped(ctx: OperationContext, event: str, grant: RepresentationGrant) -> None:
    """The trail of a step and what follows it: its event, the business told (its page at once, its mails and the
    review desk's after the COMMIT, FISCAL-F05), a newer snapshot for the Hub (bumped in this transaction, pushed
    after the COMMIT)."""
    record_event(
        ctx,
        event,
        {"hub_id": str(grant.hub_id), "id": str(grant.id), "version": grant.version},
    )
    tell_the_business(ctx, grant.hub_id)
    transaction.on_commit(partial(emails.grant_stepped, grant.id), robust=True)
    hub_push.bump_state(grant.hub_id)
    hub_push.push_after_commit(grant.hub_id)
