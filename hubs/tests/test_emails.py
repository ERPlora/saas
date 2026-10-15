"""The mails of hubs, in the recipient's language: the invitation, the ownership offer and its answer,
and the deletion with the date until which the business can be recovered.

Ported from ERPlora/saas ``hubs/main/emails.py`` and ``test_deletion_email`` (origin/develop): plain
text until block 1 brings the branded mail. Each mail names the business and the way in; none is
sent inside the transaction that wrote what it announces (services send them after the COMMIT).
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone, translation
from django.utils.formats import date_format

from hubs import emails
from hubs.models import Hub, HubMember, HubOwnershipTransfer

pytestmark = pytest.mark.django_db

BASE = "https://erplora.com"


@pytest.fixture
def hub():
    return Hub.objects.create(slug="bar-manolo", name="Bar Manolo", country="ES")


def test_the_invitation_names_who_where_as_what_and_until_when(hub, make_user):
    inviter = make_user("olga@example.com", first_name="Olga", last_name="Owner")
    invitee = make_user("ana@example.com", language="es")
    member = HubMember.objects.create(
        hub=hub,
        user=invitee,
        role=HubMember.Role.MANAGER,
        invited_by=inviter,
        invitation_message="¡Bienvenida!",
        invited_at=timezone.now(),
        invitation_expires_at=timezone.now() + timedelta(days=7),
    )

    emails.send_invitation(member, base_url=BASE, new_account=False)

    (message,) = mail.outbox
    assert message.to == ["ana@example.com"]
    assert message.subject == "Olga Owner te ha invitado a Bar Manolo"
    assert "Encargado" in message.body
    assert "¡Bienvenida!" in message.body
    assert f"{BASE}/invitation" in message.body
    with translation.override("es"):
        assert (
            date_format(timezone.localtime(member.invitation_expires_at), "DATE_FORMAT")
            in message.body
        )


def test_a_new_account_is_told_how_to_get_in(hub, make_user):
    inviter = make_user("olga@example.com")
    invitee = make_user("new@example.com", language="en")
    member = HubMember.objects.create(
        hub=hub, user=invitee, invited_by=inviter, invitation_expires_at=timezone.now()
    )

    emails.send_invitation(member, base_url=BASE, new_account=True)

    body = mail.outbox[0].body
    # «Forgot your password?» of the sign-in: the SPA's page, which mails the key to the address.
    assert f"{BASE}/password/reset" in body
    assert "/accounts/" not in body
    assert "olga@example.com invited you to Bar Manolo" == mail.outbox[0].subject


def test_the_ownership_offer_and_its_acceptance(hub, make_user):
    olga, ana = (
        make_user("olga@example.com", language="es"),
        make_user("ana@example.com", language="en"),
    )
    transfer = HubOwnershipTransfer.objects.create(
        hub=hub,
        from_user=olga,
        to_user=ana,
        from_email=olga.email,
        to_email=ana.email,
        expires_at=timezone.now() + timedelta(days=7),
    )

    emails.send_ownership_offer(transfer, base_url=BASE)
    emails.send_ownership_accepted(transfer, base_url=BASE)

    offer, accepted = mail.outbox
    assert (offer.to, accepted.to) == (["ana@example.com"], ["olga@example.com"])
    assert offer.subject == "olga@example.com wants to hand Bar Manolo over to you"
    # Billing does not move with the business: both mails say who keeps paying.
    assert "billing" in offer.body.lower()
    assert accepted.subject == "ana@example.com ya es propietario de Bar Manolo"
    assert "factura" in accepted.body.lower()


def test_the_deletion_says_until_when_it_can_be_recovered(hub, make_user):
    owner = make_user("olga@example.com", language="en")
    hub.deletion_requested_at = timezone.now()

    emails.send_deletion(hub, owner, base_url=BASE)

    (message,) = mail.outbox
    assert message.subject == "Bar Manolo was deleted"
    with translation.override("en"):
        assert (
            date_format(timezone.localtime(hub.purge_after), "DATE_FORMAT")
            in message.body
        )
    assert f"{BASE}/businesses" in message.body


def test_a_mail_that_cannot_leave_is_logged_not_raised(
    hub, make_user, monkeypatch, caplog
):
    owner = make_user("olga@example.com")
    hub.deletion_requested_at = timezone.now()

    def broken(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(emails, "send_mail", broken)

    assert emails.send_deletion(hub, owner, base_url=BASE) is False
    assert "smtp down" in caplog.text


def test_the_base_url_of_a_request_or_the_public_host(rf, settings):
    settings.PUBLIC_HOST = "erplora.com"

    assert (
        emails.base_url(rf.get("/", HTTP_HOST="localhost:8001"))
        == "http://localhost:8001"
    )
    assert emails.base_url(None) == "https://erplora.com"
