"""Queries of fiscal: the business's authorisation as its page shows it (``fiscal.representation.status``) and
as its snapshot tells the Hub (``snapshot_block``; plan 2026-10-15, «Contrato»).

Both read the same state (``_current``): the authorisation in force if there is one (a newer upload waiting or
returned never takes it away, as in the old product); else the one waiting for review (what happens next,
even after a later withdrawal of an older one); else the version that changed last (sent, reviewed or
withdrawn; on a tie, the newer version), so a withdrawal after a newer version was returned reads
«withdrawn»; «none» without any. Neither reads the documents (a live query re-runs after every change, and the encrypted megabytes are the
admin's alone).

``hubs.queries.hub_snapshot`` imports this module, so this one never imports ``hubs.queries`` at its top (that
would be a cycle): it reads ``hubs.models`` only, and ``access``/``account_of`` inside the operation.
"""

from typing import Any
from uuid import UUID

from django.db.models import BooleanField, Case, ExpressionWrapper, F, Q, Value, When
from django.db.models.functions import Coalesce, Greatest
from live.context import OperationContext
from live.operations import operation

from fiscal.models import RepresentationGrant
from fiscal.schemas import RepresentationStatusIn, RepresentationStatusOut
from hubs.models import HubMember

Status = RepresentationGrant.Status
#: How many versions the page lists, newest first.
HISTORY_LENGTH = 10
#: Reasons that are a mark of the platform, never a note to the customer: an upload a newer one replaced, an
#: approval a newer approval replaced.
REPLACED_MARKS = (RepresentationGrant.SUPERSEDED, RepresentationGrant.REPLACED_BY_APPROVAL)
#: The states whose reason is the staff's note to the customer.
STATES_WITH_A_REASON = (Status.RETURNED, Status.REVOKED)


def _rows(hub_id: UUID):
    """The business's versions without their documents, saying which optional ones they carry."""
    return (
        RepresentationGrant.objects.filter(hub_id=hub_id)
        .defer(*RepresentationGrant.DOCUMENTS)
        .annotate(
            has_signature_sample=ExpressionWrapper(
                Q(signature_sample__isnull=False), output_field=BooleanField()
            ),
            has_representation_proof=ExpressionWrapper(
                Q(representation_proof__isnull=False), output_field=BooleanField()
            ),
        )
        .order_by("-version")
    )


def _current(rows) -> RepresentationGrant | None:
    """The one in force, else the one waiting for review, else the one that changed last
    (``RepresentationGrant.changed_at``; on a tie, the newer version), in one query."""
    return (
        rows.annotate(
            precedence=Case(
                When(status=Status.APPROVED, then=Value(0)),
                When(status=Status.SUBMITTED, then=Value(1)),
                default=Value(2),
            ),
            last_change=Greatest(
                F("submitted_at"),
                Coalesce("reviewed_at", "submitted_at"),
                Coalesce("revoked_at", "submitted_at"),
            ),
        )
        .order_by("precedence", "-last_change", "-version")
        .first()
    )


def _reason(grant: RepresentationGrant) -> str:
    """The staff's note to the customer: only of a returned or withdrawn one, and never a platform's mark."""
    if grant.status not in STATES_WITH_A_REASON or grant.reason in REPLACED_MARKS:
        return ""
    return grant.reason


@operation(
    "fiscal.representation.status",
    kind="query",
    permission="fiscal.view",
    input=RepresentationStatusIn,
    output=RepresentationStatusOut,
)
def representation_status(
    ctx: OperationContext, data: RepresentationStatusIn
) -> dict[str, Any]:
    """The business's authorisation, for its owner and admins (as ``hubs.business.get``: 404 without access,
    403 below admin)."""
    # Inside: hubs.queries imports this module for the snapshot (see the module's docstring).
    from hubs.queries import access, account_of

    access(account_of(ctx), data.id, HubMember.Role.ADMIN)
    rows = _rows(data.id)
    newest = list(rows[:HISTORY_LENGTH])
    current = _current(rows)
    history = [
        {
            "version": row.version,
            "status": row.status,
            "submitted_at": row.submitted_at,
            "reviewed_at": row.reviewed_at,
            "reason": _reason(row),
            "superseded": row.reason in REPLACED_MARKS,
        }
        for row in newest
    ]
    if current is None:
        return {
            "status": "none",
            "version": None,
            "submitted_at": None,
            "reviewed_at": None,
            "changed_at": None,
            "reason": "",
            "taxpayer_tax_id": "",
            "taxpayer_name": "",
            "signer_name": "",
            "documents": {
                "signed_model": False,
                "id_copy": False,
                "signature_sample": False,
                "representation_proof": False,
            },
            "history": history,
        }
    return {
        "status": current.status,
        "version": current.version,
        "submitted_at": current.submitted_at,
        "reviewed_at": current.reviewed_at,
        "changed_at": current.changed_at,
        "reason": _reason(current),
        "taxpayer_tax_id": current.taxpayer_tax_id,
        "taxpayer_name": current.taxpayer_name,
        "signer_name": current.signer_name,
        "documents": {
            # Required: every row carries them.
            "signed_model": True,
            "id_copy": True,
            "signature_sample": current.has_signature_sample,
            "representation_proof": current.has_representation_proof,
        },
        "history": history,
    }


def snapshot_block(hub_id: UUID) -> dict[str, Any]:
    """``verifactu.representation`` of the business's snapshot (``hubs.queries.hub_snapshot``): its state,
    when it last changed (ISO 8601) and the staff's note of a returned or withdrawn one. Never a document, a
    name nor a tax ID."""
    rows = _rows(hub_id)
    current = _current(rows)
    if current is None:
        return {"representation": {"status": "none", "updated_at": None, "reason": ""}}
    return {
        "representation": {
            "status": current.status,
            "updated_at": current.changed_at.isoformat(),
            "reason": _reason(current),
        }
    }


def step_to_announce(grant_id: UUID) -> tuple[RepresentationGrant, list] | None:
    """What ``fiscal.emails`` announces of the step that left ``grant_id`` as it is: the grant with its business,
    without its documents, and the active owner and admins of the business who answered their invitation, by
    email. ``None`` for a grant that no longer exists and for a step a newer one replaced (a mark of the
    platform in ``reason``): the newer step's own mail says all there is to say."""
    grant = (
        RepresentationGrant.objects.select_related("hub")
        .defer(*RepresentationGrant.DOCUMENTS)
        .filter(pk=grant_id)
        .first()
    )
    if grant is None or grant.reason in REPLACED_MARKS:
        return None
    members = (
        HubMember.objects.filter(
            hub_id=grant.hub_id,
            accepted_at__isnull=False,
            role__in=[HubMember.Role.OWNER, HubMember.Role.ADMIN],
            user__is_active=True,
        )
        .select_related("user")
        .order_by("user__email")
    )
    return grant, [member.user for member in members]
