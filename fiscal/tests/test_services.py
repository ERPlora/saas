"""The commands of fiscal (plan 2026-10-15, «Diseño en el SaaS»): the Hub sends an authorisation, the staff
approve it, return it with a reason or withdraw an approval; every step leaves its trail (the row and an
``OutboxEvent``), bumps the business's snapshot in its transaction and pushes it after the COMMIT.

Ported in behaviour from ERPlora/saas ``apps/dashboard/fiscal/services/representation_grant.py``
(origin/develop: ``submit_grant_for_review``, ``approve_grant``, ``reject_grant``, their validation codes and
``superseded_by_new_upload``), keyed by the business; the withdrawal by the staff is new (the old product only
revoked from the API).
"""

import base64

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from fiscal import crypto, services
from fiscal.documents import MAX_DOCUMENT_BYTES
from fiscal.models import RepresentationGrant
from fiscal.schemas import (
    NotifyIn,
    RepresentationSubmitIn,
    ReturnIn,
    ReviewIn,
    WithdrawIn,
)
from fiscal.tests.conftest import PDF, make_grant, pdf_b64, staff_ctx, submission
from hubs.models import Hub, HubMember
from hubs.services import system_ctx_for
from hubs.tests.conftest import add_member, ctx_for

pytestmark = pytest.mark.django_db


def submit(hub, **overrides):
    return services.representation_submit(
        system_ctx_for(hub.id),
        RepresentationSubmitIn(hub_id=hub.id, **submission(**overrides)),
    )


def version_of(hub):
    return Hub.objects.get(pk=hub.pk).state_version


def grant_of(hub, version):
    return RepresentationGrant.objects.get(hub=hub, version=version)


def refusal(hub, **overrides) -> InvalidPayload:
    with pytest.raises(InvalidPayload) as refused:
        submit(hub, **overrides)
    return refused.value


JPEG = base64.b64encode(b"\xff\xd8\xff\xe0 a photo").decode()


# --- The Hub sends an authorisation -----------------------------------------------------------------


class TestSubmit:
    def test_it_is_filed_for_review_as_version_1(self, business):
        result = submit(
            business, taxpayer_tax_id=" 12.345.678-z ", signer_tax_id="12345678z"
        )

        grant = grant_of(business, 1)
        assert (result.status, result.version, result.submitted_at) == (
            "submitted",
            1,
            grant.submitted_at,
        )
        assert (grant.status, grant.taxpayer_tax_id, grant.signer_tax_id) == (
            "submitted",
            "12345678Z",
            "12345678Z",
        )
        assert (grant.taxpayer_name, grant.signer_name, grant.signer_document_type) == (
            "Manolo García",
            "Manolo García",
            "dni",
        )
        assert (grant.reviewed_at, grant.reviewed_by, grant.reason) == (None, None, "")

    def test_the_documents_are_stored_encrypted(self, business):
        submit(business)

        grant = grant_of(business, 1)
        assert PDF not in bytes(grant.signed_model)
        assert crypto.decrypt(grant.signed_model) == PDF + b"signed"
        assert crypto.decrypt(grant.id_copy) == PDF + b"id"
        assert (grant.signature_sample, grant.representation_proof) == (None, None)

    def test_a_nie_brings_a_signature_sample(self, business):
        submit(
            business,
            taxpayer_tax_id="X1234567L",
            signer_tax_id="X1234567L",
            signer_document_type="nie",
            documents={
                "signed_model": pdf_b64("s"),
                "id_copy": pdf_b64("i"),
                "signature_sample": pdf_b64("sample"),
            },
        )

        assert crypto.decrypt(grant_of(business, 1).signature_sample) == PDF + b"sample"

    def test_a_company_brings_the_proof_of_its_representative(self, business):
        submit(
            business,
            taxpayer_tax_id="B12345678",
            taxpayer_name="Bar Manolo SL",
            documents={
                "signed_model": pdf_b64("s"),
                "id_copy": pdf_b64("i"),
                "representation_proof": pdf_b64("deed"),
            },
        )

        grant = grant_of(business, 1)
        assert (grant.taxpayer_tax_id, crypto.decrypt(grant.representation_proof)) == (
            "B12345678",
            PDF + b"deed",
        )

    def test_a_new_upload_replaces_the_one_still_waiting(self, business):
        submit(business)

        assert submit(business).version == 2

        first = grant_of(business, 1)
        assert (first.status, first.reason, first.reviewed_at) == (
            "returned",
            "superseded_by_new_upload",
            None,
        )
        assert grant_of(business, 2).status == "submitted"

    def test_an_approved_authorisation_stays_in_force_while_the_new_one_waits(
        self, business
    ):
        make_grant(business, version=1, status="approved", reviewed_at=timezone.now())

        submit(business)

        assert grant_of(business, 1).status == "approved"
        assert grant_of(business, 2).status == "submitted"

    def test_a_returned_one_keeps_the_reason_the_reviewer_gave(self, business):
        make_grant(
            business, version=1, status="returned", reason="The DNI copy is unreadable."
        )

        submit(business)

        assert grant_of(business, 1).reason == "The DNI copy is unreadable."

    def test_a_version_is_never_handed_out_twice(self, business):
        make_grant(business, version=1, status="revoked")
        make_grant(business, version=4, status="returned")

        assert submit(business).version == 5

    def test_the_versions_of_each_business_are_its_own(self, business, other_business):
        make_grant(other_business, version=7, status="approved")

        assert submit(business).version == 1

    def test_it_bumps_the_snapshot_of_its_business_only(self, business, other_business):
        before, other = version_of(business), version_of(other_business)

        submit(business)

        assert (version_of(business), version_of(other_business)) == (before + 1, other)

    def test_the_hub_gets_the_new_state_after_the_commit(
        self, business, hub_double, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            submit(business)

        state = hub_double.calls_to("PUT", f"/internal/hubs/{business.id}/state")[
            -1
        ].body
        assert state["verifactu"]["representation"]["status"] == "submitted"
        assert state["version"] == version_of(business)

    def test_nothing_leaves_before_the_commit(
        self, business, hub_double, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            submit(business)

        assert callbacks and hub_double.calls == []

    def test_its_trail_names_the_version_and_never_carries_a_document(
        self, business, owner
    ):
        submit(business)

        event = OutboxEvent.objects.get(name="fiscal.representation.submitted")
        grant = grant_of(business, 1)
        assert (event.actor, event.scope_key) == ("system", str(owner.pk))
        assert event.payload == {
            "hub_id": str(business.id),
            "id": str(grant.id),
            "version": 1,
        }

    def test_only_the_platform_sends_an_authorisation(self, business, owner):
        with pytest.raises(PermissionDenied):
            services.representation_submit(
                ctx_for(owner),
                RepresentationSubmitIn(hub_id=business.id, **submission()),
            )

        assert not RepresentationGrant.objects.exists()

    def test_an_unknown_business_is_404(self, plans):
        import uuid

        hub_id = uuid.uuid7()
        with pytest.raises(NotFound):
            services.representation_submit(
                system_ctx_for(hub_id),
                RepresentationSubmitIn(hub_id=hub_id, **submission()),
            )

    @pytest.mark.parametrize("status", ["deleting", "deleted"])
    def test_a_deleted_business_takes_none(self, business, status):
        Hub.objects.filter(pk=business.pk).update(status=status)

        with pytest.raises(NotFound):
            submit(business)

        assert not RepresentationGrant.objects.exists()


class TestTheRulesOfASubmission:
    """The old product's table (``GrantValidationError``), with the business's codes: each broken rule names
    its field; the first one is the error's code; nothing is stored and the snapshot does not move."""

    @pytest.mark.parametrize(
        "overrides, code, field",
        [
            (
                {"taxpayer_tax_id": ""},
                "fiscal.taxpayer_tax_id_invalid",
                "taxpayer_tax_id",
            ),
            (
                {"taxpayer_tax_id": "ESB12345678"},
                "fiscal.taxpayer_tax_id_invalid",
                "taxpayer_tax_id",
            ),
            ({"signer_tax_id": "  "}, "fiscal.signer_required", "signer_tax_id"),
            # Nothing left once normalised: it would be stored empty.
            ({"signer_tax_id": "--"}, "fiscal.signer_required", "signer_tax_id"),
            ({"signer_name": ""}, "fiscal.signer_required", "signer_name"),
            (
                {"signer_document_type": "passport"},
                "fiscal.document_type_invalid",
                "signer_document_type",
            ),
            (
                {"documents": {"id_copy": pdf_b64()}},
                "fiscal.signed_model_required",
                "documents.signed_model",
            ),
            (
                {"documents": {"signed_model": JPEG, "id_copy": pdf_b64()}},
                "fiscal.signed_model_not_pdf",
                "documents.signed_model",
            ),
            (
                {"documents": {"signed_model": pdf_b64()}},
                "fiscal.id_copy_required",
                "documents.id_copy",
            ),
            (
                {"documents": {"signed_model": pdf_b64(), "id_copy": JPEG}},
                "fiscal.document_not_pdf",
                "documents.id_copy",
            ),
            (
                {"signer_document_type": "nie"},
                "fiscal.signature_sample_required",
                "documents.signature_sample",
            ),
            (
                {"taxpayer_tax_id": "B12345678"},
                "fiscal.representation_proof_required",
                "documents.representation_proof",
            ),
            (
                {
                    "documents": {
                        "signed_model": pdf_b64(),
                        "id_copy": pdf_b64(),
                        "signature_sample": "%%%",
                    }
                },
                "fiscal.document_not_pdf",
                "documents.signature_sample",
            ),
        ],
    )
    def test_each_rule_answers_its_code(self, business, overrides, code, field):
        before = version_of(business)

        refused = refusal(business, **overrides)

        assert (refused.status, refused.code) == (422, code)
        assert field in refused.fields
        assert not RepresentationGrant.objects.exists()
        assert version_of(business) == before

    @pytest.mark.parametrize(
        "field, code",
        [
            ("signer_tax_id", "fiscal.signer_required"),
            ("taxpayer_tax_id", "fiscal.taxpayer_tax_id_invalid"),
        ],
    )
    def test_a_tax_id_longer_than_its_column_is_a_rule_not_a_crash(
        self, business, field, code
    ):
        """The schema refuses it at the door; a caller that skips the schema still gets its code, never a
        ``DataError`` from the 16 characters of the column."""
        data = RepresentationSubmitIn(hub_id=business.id, **submission())
        overlong = data.model_copy(update={field: "1" * 17 + "Z"})

        with pytest.raises(InvalidPayload) as refused:
            services.representation_submit(system_ctx_for(business.id), overlong)

        assert (refused.value.code, field in refused.value.fields) == (code, True)
        assert not RepresentationGrant.objects.exists()

    def test_a_document_over_5_mb_is_refused(self, business):
        big = base64.b64encode(PDF + b"x" * MAX_DOCUMENT_BYTES).decode()

        refused = refusal(
            business, documents={"signed_model": big, "id_copy": pdf_b64()}
        )

        assert (refused.code, list(refused.fields)) == (
            "fiscal.document_too_large",
            ["documents.signed_model"],
        )

    def test_every_broken_rule_is_named_and_the_first_is_the_code(self, business):
        refused = refusal(business, taxpayer_tax_id="", signer_name="", documents={})

        assert refused.code == "fiscal.taxpayer_tax_id_invalid"
        assert set(refused.fields) == {
            "taxpayer_tax_id",
            "signer_name",
            "documents.signed_model",
            "documents.id_copy",
        }

    def test_the_messages_speak_the_callers_language(self, business):
        ctx = system_ctx_for(business.id)
        es = type(ctx)(
            scope=ctx.scope, actor=ctx.actor, permissions=ctx.permissions, language="es"
        )

        with pytest.raises(InvalidPayload) as refused:
            services.representation_submit(
                es,
                RepresentationSubmitIn(
                    hub_id=business.id, **submission(signer_name="")
                ),
            )

        assert (
            refused.value.fields["signer_name"]
            == "Indica quién firma la autorización: su nombre y su NIF."
        )


# --- The staff decide ----------------------------------------------------------------------------------


@pytest.fixture
def waiting(business):
    return make_grant(business, version=1, status="submitted")


class TestApprove:
    def test_it_puts_the_authorisation_in_force_with_its_reviewer(
        self, waiting, reviewer
    ):
        result = services.representation_approve(
            staff_ctx(reviewer), ReviewIn(id=waiting.id)
        )

        waiting.refresh_from_db()
        assert (result.id, result.status, result.version) == (waiting.id, "approved", 1)
        assert (waiting.status, waiting.reviewed_by, waiting.reason) == (
            "approved",
            reviewer,
            "",
        )
        assert waiting.reviewed_at is not None

    def test_it_withdraws_the_one_it_replaces(self, business, reviewer):
        old = make_grant(
            business, version=1, status="approved", reviewed_at=timezone.now()
        )
        new = make_grant(business, version=2, status="submitted")

        services.representation_approve(staff_ctx(reviewer), ReviewIn(id=new.id))

        old.refresh_from_db()
        assert (old.status, old.revoked_by, old.reason) == (
            "revoked",
            reviewer,
            "Superseded by a new approval.",
        )
        assert old.revoked_at is not None
        assert RepresentationGrant.approved_for(business.id) == new

    @pytest.mark.parametrize("status", ["approved", "returned", "revoked"])
    def test_only_one_waiting_is_decided(self, business, reviewer, status):
        grant = make_grant(business, version=1, status=status)

        with pytest.raises(Conflict) as refused:
            services.representation_approve(staff_ctx(reviewer), ReviewIn(id=grant.id))

        assert (refused.value.status, refused.value.code) == (409, "fiscal.not_pending")
        grant.refresh_from_db()
        assert grant.status == status

    def test_it_bumps_the_snapshot_and_pushes_it_after_the_commit(
        self,
        business,
        waiting,
        reviewer,
        hub_double,
        django_capture_on_commit_callbacks,
    ):
        before = version_of(business)

        with django_capture_on_commit_callbacks(execute=True):
            services.representation_approve(
                staff_ctx(reviewer), ReviewIn(id=waiting.id)
            )

        assert version_of(business) == before + 1
        state = hub_double.calls_to("PUT", "/state")[-1].body
        assert (state["version"], state["verifactu"]["representation"]["status"]) == (
            before + 1,
            "approved",
        )

    def test_its_trail_names_the_reviewer(self, business, waiting, reviewer):
        services.representation_approve(staff_ctx(reviewer), ReviewIn(id=waiting.id))

        event = OutboxEvent.objects.get(name="fiscal.representation.approved")
        assert (event.actor, event.scope_key) == (
            "reviewer@erplora.com",
            str(reviewer.pk),
        )
        assert event.payload == {
            "hub_id": str(business.id),
            "id": str(waiting.id),
            "version": 1,
        }

    def test_a_superuser_may_decide(self, waiting, make_user):
        root = make_user("root@erplora.com", is_staff=True, is_superuser=True)

        assert (
            services.representation_approve(
                staff_ctx(root), ReviewIn(id=waiting.id)
            ).status
            == "approved"
        )

    @pytest.mark.parametrize(
        "who",
        ["customer", "staff without the permission", "inactive reviewer", "platform"],
    )
    def test_nobody_else_decides(
        self, business, waiting, reviewer, owner, make_user, who
    ):
        if who == "customer":
            ctx = ctx_for(owner)
        elif who == "staff without the permission":
            ctx = staff_ctx(make_user("help@erplora.com", is_staff=True))
        elif who == "inactive reviewer":
            reviewer.is_active = False
            reviewer.save()
            ctx = staff_ctx(reviewer)
        else:
            ctx = system_ctx_for(business.id)

        with pytest.raises(PermissionDenied):
            services.representation_approve(ctx, ReviewIn(id=waiting.id))

        waiting.refresh_from_db()
        assert waiting.status == "submitted"

    def test_an_unknown_authorisation_is_404(self, reviewer, plans):
        import uuid

        with pytest.raises(NotFound):
            services.representation_approve(
                staff_ctx(reviewer), ReviewIn(id=uuid.uuid7())
            )


class TestReturn:
    def test_it_goes_back_with_the_reason_for_the_customer(self, waiting, reviewer):
        result = services.representation_return(
            staff_ctx(reviewer),
            ReturnIn(id=waiting.id, reason="  The DNI copy is unreadable.  "),
        )

        waiting.refresh_from_db()
        assert result.status == "returned"
        assert (waiting.status, waiting.reason, waiting.reviewed_by) == (
            "returned",
            "The DNI copy is unreadable.",
            reviewer,
        )
        assert waiting.reviewed_at is not None
        assert OutboxEvent.objects.filter(
            name="fiscal.representation.returned"
        ).exists()

    def test_an_approved_one_in_force_stays(self, business, reviewer):
        approved = make_grant(business, version=1, status="approved")
        new = make_grant(business, version=2, status="submitted")

        services.representation_return(
            staff_ctx(reviewer), ReturnIn(id=new.id, reason="Not signed.")
        )

        approved.refresh_from_db()
        assert approved.status == "approved"

    @pytest.mark.parametrize("reason", ["", "   "])
    def test_it_needs_a_reason(self, business, waiting, reviewer, reason):
        before = version_of(business)

        with pytest.raises(InvalidPayload) as refused:
            services.representation_return(
                staff_ctx(reviewer), ReturnIn(id=waiting.id, reason=reason)
            )

        assert (refused.value.code, list(refused.value.fields)) == (
            "fiscal.reason_required",
            ["reason"],
        )
        waiting.refresh_from_db()
        assert waiting.status == "submitted"
        assert version_of(business) == before

    def test_the_reason_has_a_ceiling(self, waiting, reviewer):
        with pytest.raises(InvalidPayload) as refused:
            services.representation_return(
                staff_ctx(reviewer), ReturnIn(id=waiting.id, reason="x" * 501)
            )

        assert refused.value.code == "fiscal.reason_too_long"

    def test_only_one_waiting_is_returned(self, business, reviewer):
        grant = make_grant(business, version=1, status="approved")

        with pytest.raises(Conflict) as refused:
            services.representation_return(
                staff_ctx(reviewer), ReturnIn(id=grant.id, reason="No.")
            )

        assert refused.value.code == "fiscal.not_pending"

    def test_it_bumps_the_snapshot(self, business, waiting, reviewer):
        before = version_of(business)

        services.representation_return(
            staff_ctx(reviewer), ReturnIn(id=waiting.id, reason="Not signed.")
        )

        assert version_of(business) == before + 1

    def test_the_customer_does_not_return_it(self, waiting, owner):
        with pytest.raises(PermissionDenied):
            services.representation_return(
                ctx_for(owner), ReturnIn(id=waiting.id, reason="No.")
            )


class TestWithdraw:
    def test_an_approval_is_withdrawn_with_its_reason_and_who(self, business, reviewer):
        approved = make_grant(
            business, version=1, status="approved", reviewed_at=timezone.now()
        )

        result = services.representation_withdraw(
            staff_ctx(reviewer),
            WithdrawIn(id=approved.id, reason="The company changed its administrator."),
        )

        approved.refresh_from_db()
        assert result.status == "revoked"
        assert (approved.status, approved.reason, approved.revoked_by) == (
            "revoked",
            "The company changed its administrator.",
            reviewer,
        )
        assert approved.revoked_at is not None
        assert OutboxEvent.objects.filter(name="fiscal.representation.revoked").exists()

    @pytest.mark.parametrize("status", ["submitted", "returned", "revoked"])
    def test_only_an_approval_is_withdrawn(self, business, reviewer, status):
        grant = make_grant(business, version=1, status=status)

        with pytest.raises(Conflict) as refused:
            services.representation_withdraw(
                staff_ctx(reviewer), WithdrawIn(id=grant.id, reason="No.")
            )

        assert (refused.value.status, refused.value.code) == (
            409,
            "fiscal.not_approved",
        )

    def test_it_needs_a_reason(self, business, reviewer):
        approved = make_grant(business, version=1, status="approved")

        with pytest.raises(InvalidPayload) as refused:
            services.representation_withdraw(
                staff_ctx(reviewer), WithdrawIn(id=approved.id, reason="")
            )

        assert refused.value.code == "fiscal.reason_required"
        approved.refresh_from_db()
        assert approved.status == "approved"

    def test_it_bumps_the_snapshot_and_pushes_it(
        self, business, reviewer, hub_double, django_capture_on_commit_callbacks
    ):
        approved = make_grant(business, version=1, status="approved")
        before = version_of(business)

        with django_capture_on_commit_callbacks(execute=True):
            services.representation_withdraw(
                staff_ctx(reviewer), WithdrawIn(id=approved.id, reason="Revoked.")
            )

        state = hub_double.calls_to("PUT", "/state")[-1].body
        assert (state["version"], state["verifactu"]["representation"]) == (
            before + 1,
            {
                "status": "revoked",
                "updated_at": RepresentationGrant.objects.get(
                    pk=approved.pk
                ).revoked_at.isoformat(),
                "reason": "Revoked.",
            },
        )


# --- The owner and the admins of the business hear of each step ------------------------------------------


class TestTheBusinessHearsOfIt:
    def test_the_owner_and_the_admins_get_it_on_their_channels(
        self, business, owner, team, waiting, reviewer
    ):
        services.representation_approve(staff_ctx(reviewer), ReviewIn(id=waiting.id))

        told = set(
            OutboxEvent.objects.filter(
                name="fiscal.representation.changed"
            ).values_list("scope_key", flat=True)
        )
        assert told == {str(owner.pk), str(team["admin"].pk)}

    def test_the_channel_of_the_command_is_not_told_twice(self, business, owner):
        """The Hub's upload runs in the owner's channel (``system_ctx_for``): its own event re-runs it."""
        submit(business)

        assert not OutboxEvent.objects.filter(
            name="fiscal.representation.changed", scope_key=str(owner.pk)
        ).exists()

    def test_a_manager_or_an_employee_is_not_told(
        self, business, team, waiting, reviewer
    ):
        services.representation_approve(staff_ctx(reviewer), ReviewIn(id=waiting.id))

        told = set(
            OutboxEvent.objects.filter(
                name="fiscal.representation.changed"
            ).values_list("scope_key", flat=True)
        )
        assert (
            str(team["manager"].pk) not in told and str(team["employee"].pk) not in told
        )

    def test_only_the_platform_tells(self, business, owner):
        with pytest.raises(PermissionDenied):
            services.representation_notify(ctx_for(owner), NotifyIn(id=business.id))


def test_a_pending_invitation_is_not_told(business, make_user, waiting, reviewer):
    add_member(
        business,
        make_user("new-admin@example.com"),
        HubMember.Role.ADMIN,
        accepted=False,
    )

    services.representation_approve(staff_ctx(reviewer), ReviewIn(id=waiting.id))

    assert OutboxEvent.objects.filter(name="fiscal.representation.changed").count() == 1


def test_the_reviewer_needs_the_change_permission_not_only_the_view_one(
    waiting, make_user
):
    helper = make_user("support@erplora.com", is_staff=True)
    helper.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="fiscal", codename="view_representationgrant"
        )
    )

    with pytest.raises(PermissionDenied):
        services.representation_approve(staff_ctx(helper), ReviewIn(id=waiting.id))
