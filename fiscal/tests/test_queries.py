"""``fiscal.representation.status``: the business's authorisation as its page shows it (the owner and the
admins; plan 2026-10-15). The one in force if there is one, else the newest; which documents it carries
(never the documents); and the versions sent, newest first."""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import NotFound, PermissionDenied

from fiscal import queries
from fiscal.schemas import RepresentationStatusIn
from fiscal.tests.conftest import make_grant
from hubs.models import Hub
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


def status(user, hub):
    return queries.representation_status(
        ctx_for(user), RepresentationStatusIn(id=hub.id)
    ).model_dump()


NO_DOCUMENTS = {
    "signed_model": False,
    "id_copy": False,
    "signature_sample": False,
    "representation_proof": False,
}


def test_a_business_that_never_sent_one_has_none(business, owner):
    assert status(owner, business) == {
        "status": "none",
        "version": None,
        "submitted_at": None,
        "reviewed_at": None,
        "changed_at": None,
        "reason": "",
        "taxpayer_tax_id": "",
        "taxpayer_name": "",
        "signer_name": "",
        "documents": NO_DOCUMENTS,
        "history": [],
    }


def test_one_under_review(business, owner):
    grant = make_grant(
        business,
        taxpayer_tax_id="B12345678",
        taxpayer_name="Bar Manolo SL",
        signer_name="Manolo",
    )

    result = status(owner, business)

    assert (
        result["status"],
        result["version"],
        result["submitted_at"],
        result["reviewed_at"],
    ) == (
        "submitted",
        1,
        grant.submitted_at,
        None,
    )
    assert (
        result["taxpayer_tax_id"],
        result["taxpayer_name"],
        result["signer_name"],
    ) == (
        "B12345678",
        "Bar Manolo SL",
        "Manolo",
    )
    assert result["documents"] == {
        **NO_DOCUMENTS,
        "signed_model": True,
        "id_copy": True,
    }
    assert result["history"] == [
        {
            "version": 1,
            "status": "submitted",
            "submitted_at": grant.submitted_at,
            "reviewed_at": None,
            "reason": "",
            "superseded": False,
        }
    ]


def test_the_optional_documents_are_said_when_present(business, owner):
    from fiscal import crypto

    make_grant(
        business,
        signature_sample=crypto.encrypt(b"%PDF sample"),
        representation_proof=crypto.encrypt(b"%PDF deed"),
    )

    assert status(owner, business)["documents"] == {
        "signed_model": True,
        "id_copy": True,
        "signature_sample": True,
        "representation_proof": True,
    }


def test_a_returned_one_says_why(business, owner):
    make_grant(
        business,
        status="returned",
        reviewed_at=timezone.now(),
        reason="The DNI copy is unreadable.",
    )

    result = status(owner, business)

    assert (result["status"], result["reason"]) == (
        "returned",
        "The DNI copy is unreadable.",
    )


def test_the_one_in_force_is_shown_while_a_newer_one_waits(business, owner):
    reviewed = timezone.now() - timedelta(days=2)
    make_grant(business, version=1, status="approved", reviewed_at=reviewed)
    make_grant(business, version=2, status="submitted")

    result = status(owner, business)

    assert (result["status"], result["version"], result["reviewed_at"]) == (
        "approved",
        1,
        reviewed,
    )
    assert [(row["version"], row["status"]) for row in result["history"]] == [
        (2, "submitted"),
        (1, "approved"),
    ]


def test_a_withdrawal_is_dated_by_when_it_was_withdrawn_not_approved(business, owner):
    approved = timezone.now() - timedelta(days=3)
    withdrawn = timezone.now()
    make_grant(
        business,
        status="revoked",
        submitted_at=approved - timedelta(days=1),
        reviewed_at=approved,
        revoked_at=withdrawn,
        reason="The company changed its administrator.",
    )

    result = status(owner, business)

    assert (result["status"], result["reviewed_at"], result["changed_at"]) == (
        "revoked",
        approved,
        withdrawn,
    )


def test_each_state_says_when_it_last_changed(business, owner):
    sent = timezone.now() - timedelta(days=2)
    reviewed = timezone.now() - timedelta(days=1)
    make_grant(business, version=1, status="approved", submitted_at=sent, reviewed_at=reviewed)

    assert status(owner, business)["changed_at"] == reviewed


def test_without_one_in_force_the_latest_change_is_shown(business, owner):
    """v1 approved, v2 returned, then v1 withdrawn: the business must read «withdrawn» and why, not the older
    return of v2."""
    now = timezone.now()
    make_grant(
        business,
        version=1,
        status="revoked",
        submitted_at=now - timedelta(days=10),
        reviewed_at=now - timedelta(days=9),
        revoked_at=now,
        reason="The company changed its administrator.",
    )
    make_grant(
        business,
        version=2,
        status="returned",
        submitted_at=now - timedelta(days=5),
        reviewed_at=now - timedelta(days=4),
        reason="Not signed.",
    )

    result = status(owner, business)

    assert (result["status"], result["version"], result["reason"], result["changed_at"]) == (
        "revoked",
        1,
        "The company changed its administrator.",
        now,
    )
    assert [(row["version"], row["status"], row["reason"]) for row in result["history"]] == [
        (2, "returned", "Not signed."),
        (1, "revoked", "The company changed its administrator."),
    ]


def test_a_newer_upload_after_a_withdrawal_is_shown(business, owner):
    now = timezone.now()
    make_grant(
        business,
        version=1,
        status="revoked",
        submitted_at=now - timedelta(days=10),
        reviewed_at=now - timedelta(days=9),
        revoked_at=now - timedelta(days=1),
        reason="The company changed its administrator.",
    )
    make_grant(business, version=2, status="submitted", submitted_at=now)

    assert (status(owner, business)["status"], status(owner, business)["version"]) == (
        "submitted",
        2,
    )


def test_on_a_tie_the_newer_version_is_shown(business, owner):
    moment = timezone.now()
    make_grant(
        business,
        version=1,
        status="returned",
        submitted_at=moment - timedelta(days=3),
        reviewed_at=moment,
        reason="Not signed.",
    )
    make_grant(
        business,
        version=2,
        status="revoked",
        submitted_at=moment - timedelta(days=2),
        reviewed_at=moment - timedelta(days=1),
        revoked_at=moment,
        reason="The company changed its administrator.",
    )

    assert (status(owner, business)["status"], status(owner, business)["version"]) == ("revoked", 2)


def test_one_waiting_for_review_comes_before_a_later_withdrawal(business, owner):
    """v1 approved, v2 sent, then v1 withdrawn: the business reads «under review» (v2 is what happens next),
    and its history still says why v1 was withdrawn."""
    now = timezone.now()
    make_grant(
        business,
        version=1,
        status="revoked",
        submitted_at=now - timedelta(days=10),
        reviewed_at=now - timedelta(days=9),
        revoked_at=now,
        reason="The company changed its administrator.",
    )
    make_grant(business, version=2, status="submitted", submitted_at=now - timedelta(days=2))

    result = status(owner, business)

    assert (result["status"], result["version"]) == ("submitted", 2)
    assert [(row["version"], row["status"], row["reason"]) for row in result["history"]] == [
        (2, "submitted", ""),
        (1, "revoked", "The company changed its administrator."),
    ]


def test_a_replaced_version_is_marked_and_carries_no_code_as_a_reason(business, owner):
    make_grant(
        business, version=1, status="returned", reason="superseded_by_new_upload"
    )
    make_grant(
        business,
        version=2,
        status="revoked",
        reason="Superseded by a new approval.",
        revoked_at=timezone.now(),
    )
    make_grant(business, version=3, status="approved", reviewed_at=timezone.now())

    history = status(owner, business)["history"]

    assert [(row["version"], row["superseded"], row["reason"]) for row in history] == [
        (3, False, ""),
        (2, True, ""),
        (1, True, ""),
    ]


def test_the_history_holds_the_ten_newest(business, owner):
    for version in range(1, 13):
        make_grant(
            business, version=version, status="returned", reason=f"No. {version}"
        )

    history = status(owner, business)["history"]

    assert [row["version"] for row in history] == list(range(12, 2, -1))


def test_an_admin_reads_it(business, team):
    make_grant(business)

    assert status(team["admin"], business)["status"] == "submitted"


@pytest.mark.parametrize("role", ["manager", "employee"])
def test_below_admin_it_is_refused(business, team, role):
    with pytest.raises(PermissionDenied):
        status(team[role], business)


@pytest.mark.parametrize("role", ["invitee", "stranger"])
def test_without_access_the_business_does_not_exist(business, team, role):
    with pytest.raises(NotFound):
        status(team[role], business)


def test_a_purged_business_does_not_exist(business, owner):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

    with pytest.raises(NotFound):
        status(owner, business)


def test_the_documents_are_never_read_to_answer(business, owner):
    """A live query re-runs after each change: it never pulls the encrypted megabytes of the documents."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    make_grant(business)

    with CaptureQueriesContext(connection) as captured:
        status(owner, business)

    selected = " ".join(query["sql"] for query in captured.captured_queries)
    assert '"fiscal_representationgrant"."signed_model"' not in selected
    assert '"fiscal_representationgrant"."id_copy"' not in selected
