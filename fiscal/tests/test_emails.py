"""The mails of an authorisation's steps (FISCAL-F05): the review desk hears of every one that waits for it, and
the owner and the admins of the business hear of every step of theirs, each in their language.

Cases from ERPlora/saas ``apps/dashboard/fiscal/tests/test_grant_notifications.py`` and saas#2051 (origin/develop:
nobody at ERPlora heard of what waited for them), without what made the old mail unsafe: the desk's mail carries
the link to the review page and no document, no tax id and no name of a person; the business is found by its id,
never by a tax id (the old one wrote to the first business with that tax id, of whichever account).
"""

import logging

import pytest
from django.core import mail
from django.urls import reverse

from fiscal import emails
from fiscal.tests.conftest import make_grant
from hubs.models import HubMember
from hubs.tests.conftest import add_member

pytestmark = pytest.mark.django_db


@pytest.fixture
def desk(settings):
    settings.FISCAL_REVIEW_EMAIL = "review@erplora.example"
    settings.PUBLIC_HOST = "erplora.example"
    return settings.FISCAL_REVIEW_EMAIL


def to(address):
    return [message for message in mail.outbox if message.to == [address]]


# --- The review desk ----------------------------------------------------------------------------------------


def test_a_submission_tells_the_desk_with_the_link_to_its_review_page(business, desk):
    grant = make_grant(business, version=3, status="submitted")

    emails.grant_stepped(grant.pk)

    (message,) = to(desk)
    review = "https://erplora.example" + reverse(
        "admin:fiscal_representationgrant_review", args=[grant.pk]
    )
    assert message.subject == "Autorización firmada por revisar: Bar Manolo (versión 3)"
    assert review in message.body
    assert "Bar Manolo" in message.body


def test_the_desks_mail_carries_no_document_no_tax_id_and_no_name_of_a_person(
    business, desk
):
    grant = make_grant(
        business,
        status="submitted",
        taxpayer_tax_id="12345678Z",
        taxpayer_name="Manolo García",
        signer_tax_id="12345678Z",
        signer_name="Manolo García",
    )

    emails.grant_stepped(grant.pk)

    (message,) = to(desk)
    assert message.attachments == []
    for personal in ("12345678Z", "Manolo García"):
        assert personal not in message.subject + message.body


@pytest.mark.parametrize("status", ["approved", "returned", "revoked"])
def test_a_decision_does_not_tell_the_desk(business, desk, status):
    grant = make_grant(business, status=status, reason="Unreadable copy")

    emails.grant_stepped(grant.pk)

    assert to(desk) == []


def test_the_desks_mailbox_is_supports_unless_another_is_set():
    from django.conf import settings

    assert settings.FISCAL_REVIEW_EMAIL == settings.SUPPORT_EMAIL


# --- The business -------------------------------------------------------------------------------------------


def test_a_submission_tells_the_owner_it_arrived_in_their_language(
    business, owner, desk
):
    grant = make_grant(business, status="submitted")

    emails.grant_stepped(grant.pk)

    (message,) = to(owner.email)
    assert message.subject == "Hemos recibido la autorización firmada de Bar Manolo"
    assert f"https://erplora.example/businesses/{business.pk}" in message.body


def test_an_approval_tells_the_owner_it_is_in_force(business, owner, desk):
    grant = make_grant(business, status="approved")

    emails.grant_stepped(grant.pk)

    (message,) = to(owner.email)
    assert message.subject == "La autorización firmada de Bar Manolo ya está en vigor"


def test_a_return_tells_the_owner_why(business, owner, desk):
    grant = make_grant(business, status="returned", reason="La copia del DNI no se lee.")

    emails.grant_stepped(grant.pk)

    (message,) = to(owner.email)
    assert message.subject == "Te hemos devuelto la autorización firmada de Bar Manolo"
    assert "La copia del DNI no se lee." in message.body


def test_a_withdrawal_tells_the_owner_why(business, owner, desk):
    grant = make_grant(business, status="revoked", reason="El poder ha caducado.")

    emails.grant_stepped(grant.pk)

    (message,) = to(owner.email)
    assert message.subject == "ERPlora ha retirado la autorización firmada de Bar Manolo"
    assert "El poder ha caducado." in message.body


def test_an_admin_hears_in_their_own_language(business, make_user, desk):
    admin = make_user("adela@example.com", language="en")
    add_member(business, admin, HubMember.Role.ADMIN)
    grant = make_grant(business, status="approved")

    emails.grant_stepped(grant.pk)

    (message,) = to(admin.email)
    assert message.subject == "The signed authorisation of Bar Manolo is now in force"


def test_a_manager_an_employee_or_a_pending_invitee_are_not_told(
    business, make_user, desk
):
    for email, role, accepted in (
        ("manu@example.com", HubMember.Role.MANAGER, True),
        ("elena@example.com", HubMember.Role.EMPLOYEE, True),
        ("new-admin@example.com", HubMember.Role.ADMIN, False),
    ):
        add_member(business, make_user(email), role, accepted=accepted)
    grant = make_grant(business, status="approved")

    emails.grant_stepped(grant.pk)

    told = {address for message in mail.outbox for address in message.to}
    assert told == {"owner@example.com"}


def test_the_owner_hears_even_with_business_notices_off(business, owner, desk):
    """Whether ERPlora may file the business's invoices keeps the business running: it asks no preference
    (ACCOUNTS-F23), like the mails that keep the account safe."""
    from accounts.models import UserPreferences

    UserPreferences.objects.update_or_create(user=owner, defaults={"hub_alerts": False})
    grant = make_grant(business, status="returned", reason="Falta la firma.")

    emails.grant_stepped(grant.pk)

    assert len(to(owner.email)) == 1


def test_a_submission_a_newer_one_replaced_tells_nobody(business, desk):
    """Replaced before any review: the newer one's own mail says all there is to say."""
    from fiscal.models import RepresentationGrant

    grant = make_grant(business, status="returned", reason=RepresentationGrant.SUPERSEDED)

    emails.grant_stepped(grant.pk)

    assert mail.outbox == []


def test_an_approval_a_newer_one_replaced_tells_nobody(business, desk):
    from fiscal.models import RepresentationGrant

    grant = make_grant(
        business, status="revoked", reason=RepresentationGrant.REPLACED_BY_APPROVAL
    )

    emails.grant_stepped(grant.pk)

    assert mail.outbox == []


# --- Failures -----------------------------------------------------------------------------------------------


def test_a_mail_that_cannot_leave_is_logged_and_the_rest_still_go(
    business, owner, desk, monkeypatch, caplog
):
    from django.core.mail import send_mail as real_send_mail

    def refuse_the_desk(subject, body, sender, recipients, **kwargs):
        if recipients == [desk]:
            raise OSError("the mail server is away")
        return real_send_mail(subject, body, sender, recipients, **kwargs)

    monkeypatch.setattr(emails, "send_mail", refuse_the_desk)
    grant = make_grant(business, status="submitted")

    with caplog.at_level(logging.ERROR, logger="fiscal.emails"):
        emails.grant_stepped(grant.pk)

    assert len(to(owner.email)) == 1
    (record,) = [r for r in caplog.records if r.name == "fiscal.emails"]
    assert "fiscal.mail.not_sent" in record.getMessage()
    assert str(grant.pk) in record.getMessage()


def test_a_grant_that_no_longer_exists_sends_nothing(desk):
    import uuid

    emails.grant_stepped(uuid.uuid7())

    assert mail.outbox == []
