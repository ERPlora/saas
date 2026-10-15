"""The staff's review of a signed authorisation in the Django admin (plan 2026-10-15, «Diseño en el SaaS»).

The list is the queue (business, version, taxpayer, signer, state, when it came, who reviewed it, «Review»).
Nothing is added, deleted nor edited by hand: the normal form shows every field read-only and saving it
changes nothing; the decisions are the services' (``fiscal.representation.approve|return|withdraw``), taken on
the review page, which shows the documents decrypted and never cached. Both pages need
``fiscal.change_representationgrant``; ``support`` only sees the list and the rows.
"""

import logging

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.messages import get_messages
from django.utils import timezone
from live.models import OutboxEvent

from fiscal.models import RepresentationGrant
from fiscal.tests.conftest import PDF, make_grant

pytestmark = pytest.mark.django_db

CHANGELIST = "/admin/fiscal/representationgrant/"


def review_url(grant) -> str:
    return f"{CHANGELIST}{grant.pk}/review/"


def document_url(grant, kind: str) -> str:
    return f"{CHANGELIST}{grant.pk}/review/document/{kind}/"


def texts(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


@pytest.fixture
def as_reviewer(client, reviewer):
    client.force_login(reviewer)
    return client


@pytest.fixture
def as_support(client, make_user):
    user = make_user("support@erplora.com", first_name="Sara", is_staff=True)
    user.groups.add(Group.objects.get(name="support"))
    client.force_login(user)
    return client


@pytest.fixture
def grant(business):
    return make_grant(business)


# --- The queue -------------------------------------------------------------------------------------------


def test_the_queue_lists_each_authorisation_with_its_review_link(as_reviewer, grant, business):
    response = as_reviewer.get(CHANGELIST)

    assert response.status_code == 200
    page = response.content.decode()
    assert business.slug in page or business.name in page
    assert "12345678Z" in page
    assert review_url(grant) in page


def test_the_queue_filters_by_state(as_reviewer, grant, business):
    make_grant(business, version=2, status="returned", reason="Blurry copy.")

    response = as_reviewer.get(CHANGELIST, {"status__exact": "returned"})

    assert list(response.context["cl"].result_list) == [RepresentationGrant.objects.get(version=2)]


def test_nothing_is_added_nor_deleted_by_hand(as_reviewer, grant):
    assert as_reviewer.get(f"{CHANGELIST}add/").status_code == 403
    assert as_reviewer.get(f"{CHANGELIST}{grant.pk}/delete/").status_code == 403


def test_the_normal_form_shows_the_row_read_only_and_never_the_documents(as_reviewer, grant):
    response = as_reviewer.get(f"{CHANGELIST}{grant.pk}/change/")

    assert response.status_code == 200
    page = response.content.decode()
    assert 'name="_save"' not in page
    assert 'name="status"' not in page
    assert bytes(grant.signed_model).decode(errors="ignore")[:20] not in page


def test_saving_the_normal_form_changes_nothing(as_reviewer, grant):
    before = RepresentationGrant.objects.get(pk=grant.pk)

    as_reviewer.post(
        f"{CHANGELIST}{grant.pk}/change/",
        {"status": "approved", "reason": "forged", "taxpayer_tax_id": "B12345674", "_save": "Save"},
    )

    after = RepresentationGrant.objects.get(pk=grant.pk)
    assert (after.status, after.reason, after.taxpayer_tax_id, after.reviewed_by_id) == ("submitted", "", "12345678Z", None)
    assert after.updated_at == before.updated_at


def test_support_sees_the_queue_but_not_the_review(as_support, grant):
    assert as_support.get(CHANGELIST).status_code == 200
    assert as_support.get(f"{CHANGELIST}{grant.pk}/change/").status_code == 200
    assert as_support.get(review_url(grant)).status_code == 403
    assert as_support.get(document_url(grant, "signed_model")).status_code == 403


# --- Who reaches the review ------------------------------------------------------------------------------


def test_without_a_session_the_review_asks_to_sign_in(client, grant):
    for url in (review_url(grant), document_url(grant, "signed_model")):
        response = client.get(url)

        assert response.status_code == 302
        assert "/admin/login/" in response.url


def test_staff_without_the_permission_is_refused(client, make_user, grant):
    client.force_login(make_user("intern@erplora.com", first_name="Ian", is_staff=True))

    assert client.get(review_url(grant)).status_code == 403
    assert client.get(document_url(grant, "signed_model")).status_code == 403
    assert client.post(review_url(grant), {"action": "approve"}).status_code == 403
    assert RepresentationGrant.objects.get(pk=grant.pk).status == "submitted"


def test_staff_with_only_the_view_permission_is_refused(client, make_user, grant):
    user = make_user("viewer@erplora.com", first_name="Vera", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_representationgrant"))
    client.force_login(user)

    assert client.get(review_url(grant)).status_code == 403


def test_an_unknown_authorisation_sends_back_to_the_queue_or_404(as_reviewer, grant):
    other = f"{CHANGELIST}01900000-0000-7000-8000-000000000000/review/"

    response = as_reviewer.get(other)

    assert response.status_code in (302, 404)


# --- The review page -------------------------------------------------------------------------------------


def test_the_review_page_shows_who_signs_and_the_documents_inline(as_reviewer, grant):
    response = as_reviewer.get(review_url(grant))

    assert response.status_code == 200
    page = response.content.decode()
    assert "Manolo García" in page
    assert document_url(grant, "signed_model") in page
    assert document_url(grant, "id_copy") in page
    # Not attached: no link to a document that is not there.
    assert document_url(grant, "signature_sample") not in page
    assert 'value="approve"' in page and 'value="return"' in page
    assert 'value="withdraw"' not in page
    assert "no-store" in response["Cache-Control"]


def test_an_approved_one_offers_only_the_withdrawal(as_reviewer, business):
    approved = make_grant(business, status="approved")

    page = as_reviewer.get(review_url(approved)).content.decode()

    assert 'value="withdraw"' in page
    assert 'value="approve"' not in page and 'value="return"' not in page


def test_the_review_page_speaks_spanish(as_reviewer, grant):
    response = as_reviewer.get(review_url(grant), HTTP_ACCEPT_LANGUAGE="es")

    assert "Aprobar" in response.content.decode()


def test_the_platform_s_marks_are_said_in_words_never_as_stored(as_reviewer, business):
    """``reason`` keeps a code for what replaced a version (``SUPERSEDED``, ``REPLACED_BY_APPROVAL``): the
    review page says what happened, in the reviewer's language, both for the version under review and for the
    others."""
    superseded = make_grant(
        business, version=1, status="returned", reason=RepresentationGrant.SUPERSEDED
    )
    make_grant(
        business,
        version=2,
        status="revoked",
        reason=RepresentationGrant.REPLACED_BY_APPROVAL,
        revoked_at=timezone.now(),
    )
    make_grant(business, version=3, status="approved", reviewed_at=timezone.now())

    others = as_reviewer.get(review_url(superseded), HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Sustituida por un envío más reciente antes de revisarla" in others
    assert "Sustituida por una aprobación más reciente" in others
    assert RepresentationGrant.SUPERSEDED not in others
    assert RepresentationGrant.REPLACED_BY_APPROVAL not in others


def test_the_normal_form_says_a_mark_in_words_too(as_reviewer, business):
    superseded = make_grant(
        business, version=1, status="returned", reason=RepresentationGrant.SUPERSEDED
    )

    page = as_reviewer.get(
        f"{CHANGELIST}{superseded.pk}/change/", HTTP_ACCEPT_LANGUAGE="es"
    ).content.decode()

    assert "Sustituida por un envío más reciente antes de revisarla" in page
    assert RepresentationGrant.SUPERSEDED not in page


def test_a_reviewer_s_note_is_shown_as_written(as_reviewer, business):
    returned = make_grant(business, version=1, status="returned", reason="Blurry copy.")
    current = make_grant(business, version=2)

    page = as_reviewer.get(review_url(current), HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Blurry copy." in page
    assert returned.reason == "Blurry copy."


def test_a_document_is_served_decrypted_inline_and_never_cached(as_reviewer, grant):
    response = as_reviewer.get(document_url(grant, "signed_model"))

    assert response.status_code == 200
    assert response.content == PDF + b"signed"
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("inline")
    assert "no-store" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"
    # Shown inside the review page: framed by this origin only.
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in response["Content-Security-Policy"]


def test_serving_a_document_leaves_a_trace_without_its_content(as_reviewer, grant, reviewer, caplog):
    """Who opened which document of which authorisation: the grant, the kind and the user's id, never a byte
    of the PDF nor a name."""
    with caplog.at_level(logging.INFO, logger="fiscal.admin"):
        as_reviewer.get(document_url(grant, "signed_model"))

    assert [record.getMessage() for record in caplog.records if record.name == "fiscal.admin"] == [
        f"fiscal.admin.document grant={grant.pk} kind=signed_model user={reviewer.pk}"
    ]
    assert "signed" not in caplog.text.replace("signed_model", "")


@pytest.mark.parametrize("kind", ["signature_sample", "passport", "hub"])
def test_a_document_that_is_absent_or_unknown_is_404(as_reviewer, grant, kind):
    assert as_reviewer.get(document_url(grant, kind)).status_code == 404


def test_a_document_the_key_cannot_open_is_an_error_not_a_crash(as_reviewer, grant):
    RepresentationGrant.objects.filter(pk=grant.pk).update(signed_model=b"not a fernet token")

    response = as_reviewer.get(document_url(grant, "signed_model"))

    assert response.status_code == 500
    assert response["Content-Type"].startswith("text/plain")
    assert "no-store" in response["Cache-Control"]


# --- The decisions ---------------------------------------------------------------------------------------


def test_approving_puts_it_in_force_with_its_reviewer(as_reviewer, grant, reviewer):
    response = as_reviewer.post(review_url(grant), {"action": "approve"})

    assert response.status_code == 302
    after = RepresentationGrant.objects.get(pk=grant.pk)
    assert (after.status, after.reviewed_by, after.reviewed_at is not None) == ("approved", reviewer, True)
    event = OutboxEvent.objects.get(name="fiscal.representation.approved")
    assert (event.scope_key, event.actor) == (str(reviewer.pk), "reviewer@erplora.com")


def test_returning_without_a_reason_says_why_and_changes_nothing(as_reviewer, grant):
    response = as_reviewer.post(review_url(grant), {"action": "return", "reason": "  "}, follow=True)

    assert response.status_code == 200
    assert "Write the reason: the customer reads it." in texts(response)
    assert RepresentationGrant.objects.get(pk=grant.pk).status == "submitted"


def test_returning_with_a_reason_sends_it_back(as_reviewer, grant, reviewer):
    as_reviewer.post(review_url(grant), {"action": "return", "reason": "The copy of the DNI is blurry."})

    after = RepresentationGrant.objects.get(pk=grant.pk)
    assert (after.status, after.reason, after.reviewed_by) == ("returned", "The copy of the DNI is blurry.", reviewer)


def test_withdrawing_an_approved_one_revokes_it(as_reviewer, business, reviewer):
    approved = make_grant(business, status="approved")

    as_reviewer.post(review_url(approved), {"action": "withdraw", "reason": "The signer is no longer the administrator."})

    after = RepresentationGrant.objects.get(pk=approved.pk)
    assert (after.status, after.revoked_by, after.revoked_at is not None) == ("revoked", reviewer, True)


def test_a_decision_the_state_no_longer_allows_is_a_message_not_a_crash(as_reviewer, business):
    returned = make_grant(business, status="returned", reason="Blurry copy.")

    response = as_reviewer.post(review_url(returned), {"action": "approve"}, follow=True)

    assert response.status_code == 200
    assert "Only an authorisation under review can be approved or returned." in texts(response)
    assert RepresentationGrant.objects.get(pk=returned.pk).status == "returned"


def test_an_unknown_action_is_a_message(as_reviewer, grant):
    response = as_reviewer.post(review_url(grant), {"action": "delete"}, follow=True)

    assert response.status_code == 200
    assert texts(response) and RepresentationGrant.objects.get(pk=grant.pk).status == "submitted"
