"""Commands of fiscal: the Hub sends a business's authorisation, the staff decide on it (plan 2026-10-15,
«Diseño en el SaaS»; PLAN-SAAS §4, round 2026-10-15).

Ported in behaviour from ERPlora/saas ``apps/dashboard/fiscal/services/representation_grant.py``
(origin/develop): an upload is not an authority, it waits for a person (``submitted``); a newer upload replaces
the one still waiting (``returned`` with ``SUPERSEDED``) and never the one in force; only a waiting one is
approved or returned, and returning needs a reason the customer can act on; approving replaces the approval in
force. New here: the staff may withdraw an approval (with a reason), and each step is keyed by the business,
whose snapshot carries the outcome to the Hub (``hubs.queries.hub_snapshot``, block ``verifactu``).

Every step bumps the business's ``state_version`` in its transaction (``hubs.services.bump_state``) and pushes
the snapshot once it commits (``push_after_commit``; ``reconcile_hub_states`` retries it while the Hub is
away), records its event (the trail: who, which business, which version) and tells the owner and the admins of
the business (``tell_the_business``). No document ever leaves in an event or a snapshot.
"""

from typing import Any
from uuid import UUID

from django.db.models import Max
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from billing.nif import is_legal_person_nif, is_spanish_tax_id, normalise_nif
from fiscal import crypto, events
from fiscal.documents import DocumentRejected, decode_pdf
from fiscal.models import RepresentationGrant
from fiscal.schemas import (
    TAX_ID_MAX_LENGTH,
    NotifyIn,
    NotifyOut,
    RepresentationSubmitIn,
    RepresentationSubmitOut,
    ReturnIn,
    ReviewIn,
    ReviewOut,
    WithdrawIn,
)
from hubs import queries as hub_queries
from hubs import services as hub_services
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
)
def representation_submit(ctx: OperationContext, data: RepresentationSubmitIn) -> dict:
    """``POST /internal/hubs/{id}/representation``: file the business's authorisation for review.

    Only the platform runs it (``fiscal.internal``, in the owner's channel). The rules of the documents answer
    422 with a ``fiscal.*`` code; a business that does not exist or was deleted, 404. The waiting one it
    replaces is returned with ``SUPERSEDED``; an approved one stays in force until a person approves this one.
    """
    if ctx.actor != "system":
        raise PermissionDenied(
            _("Only the Hub sends a business's authorisation."), code="internal_command"
        )
    with translation.override(ctx.language):
        checked = _checked(data)
    hub = (
        Hub.objects.select_for_update()
        .filter(pk=data.hub_id)
        .exclude(status__in=[Hub.Status.DELETING, Hub.Status.DELETED])
        .first()
    )
    if hub is None:
        raise hub_queries.not_found()
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


def _checked(data: RepresentationSubmitIn) -> dict[str, Any]:
    """The row's fields from ``data`` (tax ids normalised, documents encrypted), or ``InvalidPayload`` naming
    every broken rule, with the first one's code (the old product's table, ``GrantValidationError``)."""
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
        raise InvalidPayload(
            _("Invalid payload"),
            code=problems[0][1],
            fields={field: message for field, _code, message in problems},
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
    user = ctx.actor
    if not (
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.is_staff
        and user.has_perm(REVIEW_PERMISSION)
    ):
        raise PermissionDenied(
            _("Only ERPlora's staff decide on an authorisation."),
            code="fiscal.staff_only",
        )
    return user


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
        raise InvalidPayload(
            _("Invalid payload"),
            code="fiscal.reason_required",
            fields={"reason": _("Write the reason: the customer reads it.")},
        )
    if len(reason) > REASON_MAX_LENGTH:
        raise InvalidPayload(
            _("Invalid payload"),
            code="fiscal.reason_too_long",
            fields={
                "reason": _("The reason may be %(count)d characters at most.")
                % {"count": REASON_MAX_LENGTH}
            },
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
    """The trail of a step and what follows it: its event, the business told, a newer snapshot for the Hub
    (bumped in this transaction, pushed after the COMMIT)."""
    record_event(
        ctx,
        event,
        {"hub_id": str(grant.hub_id), "id": str(grant.id), "version": grant.version},
    )
    tell_the_business(ctx, grant.hub_id)
    hub_services.bump_state(grant.hub_id)
    hub_services.push_after_commit(grant.hub_id)


# --- The owner and the admins of the business hear of it ----------------------------------------------


@operation(
    "fiscal.representation.notify",
    kind="command",
    permission="fiscal.manage",
    input=NotifyIn,
    output=NotifyOut,
)
def representation_notify(ctx: OperationContext, data: NotifyIn) -> dict:
    """A change of the business's authorisation, recorded on this context's channel so that account's page
    re-runs at once. Only the platform runs it, from ``tell_the_business``."""
    if ctx.actor != "system":
        raise PermissionDenied(
            _("Only the platform tells a business of its authorisation."),
            code="internal_command",
        )
    record_event(ctx, events.REPRESENTATION_CHANGED, {"hub_id": str(data.id)})
    return {"id": data.id}


def tell_the_business(ctx: OperationContext, hub_id: UUID) -> None:
    """Tell the owner and the admins of the business (who read its authorisation), each on its own channel,
    but the channel ``ctx`` already notifies. Called inside the command: nothing leaves if it rolls back."""
    for user_id in hub_queries.people_to_tell(hub_id):
        scope = Scope("user", str(user_id))
        if scope != ctx.scope:
            representation_notify(system_context(scope), NotifyIn(id=hub_id))
