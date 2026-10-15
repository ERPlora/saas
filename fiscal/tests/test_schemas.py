"""The shapes of fiscal's contract (plan 2026-10-15, «Contrato»): what the Hub posts, what it gets back, what
the panel reads and the block of the snapshot. The rules of the documents are the service's
(``test_services.py``): every field of the body is a string here, so a missing or wrong one answers its code."""

import pydantic
import pytest

from fiscal.schemas import (
    RepresentationSnapshot,
    RepresentationStatusOut,
    RepresentationSubmitIn,
    RepresentationSubmitOut,
    ReturnIn,
    ReviewIn,
    WithdrawIn,
)
from fiscal.tests.conftest import submission

HUB = "019a0000-0000-7000-8000-000000000001"


def test_the_body_of_the_contract_is_read_as_sent():
    body = submission(
        documents={
            "signed_model": "a",
            "id_copy": "b",
            "signature_sample": "c",
            "representation_proof": "d",
        }
    )

    data = RepresentationSubmitIn.model_validate({**body, "hub_id": HUB})

    assert (data.taxpayer_tax_id, data.signer_document_type) == ("12345678Z", "dni")
    assert data.documents.model_dump() == {
        "signed_model": "a",
        "id_copy": "b",
        "signature_sample": "c",
        "representation_proof": "d",
    }


def test_what_is_left_out_is_empty_so_the_service_names_it():
    data = RepresentationSubmitIn.model_validate({"hub_id": HUB})

    assert (data.taxpayer_tax_id, data.signer_name, data.signer_document_type) == (
        "",
        "",
        "",
    )
    assert data.documents.model_dump() == {
        "signed_model": "",
        "id_copy": "",
        "signature_sample": "",
        "representation_proof": "",
    }


def test_an_absent_optional_document_may_be_null():
    body = submission(documents={"signed_model": "a", "id_copy": "b", "signature_sample": None})

    data = RepresentationSubmitIn.model_validate({**body, "hub_id": HUB})

    assert data.documents.signature_sample == ""


@pytest.mark.parametrize(
    "body",
    [submission(hub="x"), submission(documents={"signed_model": "a", "id_copy": "b", "selfie": "x"})],
)
def test_an_unknown_field_is_refused(body):
    with pytest.raises(pydantic.ValidationError) as refused:
        RepresentationSubmitIn.model_validate({**body, "hub_id": HUB})

    assert refused.value.errors()[0]["type"] == "extra_forbidden"


def test_the_names_have_a_ceiling():
    with pytest.raises(pydantic.ValidationError) as refused:
        RepresentationSubmitIn.model_validate({**submission(taxpayer_name="x" * 201), "hub_id": HUB})

    assert refused.value.errors()[0]["loc"] == ("taxpayer_name",)


def test_the_business_is_required():
    with pytest.raises(pydantic.ValidationError):
        RepresentationSubmitIn.model_validate(submission())


def test_the_answer_of_a_submission():
    assert set(RepresentationSubmitOut.model_fields) == {
        "status",
        "version",
        "submitted_at",
    }


def test_the_panel_reads_the_state_and_its_history():
    assert set(RepresentationStatusOut.model_fields) == {
        "status",
        "version",
        "submitted_at",
        "reviewed_at",
        "changed_at",
        "reason",
        "taxpayer_tax_id",
        "taxpayer_name",
        "signer_name",
        "documents",
        "history",
    }


@pytest.mark.parametrize(
    "status", ["none", "submitted", "approved", "returned", "revoked"]
)
def test_the_snapshot_carries_one_of_the_five_states(status):
    block = RepresentationSnapshot(status=status, updated_at=None, reason="")

    assert block.model_dump(mode="json") == {
        "status": status,
        "updated_at": None,
        "reason": "",
    }


def test_the_snapshot_refuses_any_other_state():
    with pytest.raises(pydantic.ValidationError):
        RepresentationSnapshot(status="pending", updated_at=None, reason="")


def test_the_reviews_name_the_grant_and_a_reason():
    assert set(ReviewIn.model_fields) == {"id"}
    assert (
        set(ReturnIn.model_fields) == set(WithdrawIn.model_fields) == {"id", "reason"}
    )


@pytest.mark.parametrize("field", ["taxpayer_tax_id", "signer_tax_id"])
def test_a_tax_id_longer_than_its_column_is_refused(field):
    """The row keeps 16 characters (``RepresentationGrant``): a longer one is a malformed field, never a 500."""
    with pytest.raises(pydantic.ValidationError) as broken:
        RepresentationSubmitIn.model_validate(
            {**submission(**{field: "1" * 17}), "hub_id": HUB}
        )

    assert [problem["loc"] for problem in broken.value.errors()] == [(field,)]
