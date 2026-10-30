"""The mails of hubs, in the recipient's language: the invitation, the ownership offer and its answer,
and the deletion with the date until which the business can be recovered.

Ported from ERPlora/saas ``hubs/main/emails.py`` and ``test_deletion_email`` (origin/develop). Every mail is
branded, as text and as HTML (``base.emails.branded_message``, ACCOUNTS-F46). Each mail names the business and the
way in; none is sent inside the transaction that wrote what it announces (services send them after the COMMIT).
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone, translation
from django.utils.formats import date_format

from base.tests.test_emails import assert_branded
from hubs import emails
from hubs.models import Hub, HubMember, HubOwnershipTransfer

pytestmark = pytest.mark.django_db

BASE = "https://erplora.com"
#: The day the period paid with the previous owner's card ends (HUBS-F28).
PAID_UNTIL = timezone.now() + timedelta(days=20)


@pytest.fixture(autouse=True)
def production_hosts(settings):
    """The hosts of production: a mail never points to a development host because of its template."""
    settings.PUBLIC_HOST = "erplora.com"
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"


def day(moment, language):
    with translation.override(language):
        return date_format(timezone.localtime(moment), "DATE_FORMAT")


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
    assert accepted.subject == "ana@example.com ya es propietario de Bar Manolo"


def test_the_ownership_mails_link_to_pages_the_panel_has(hub, make_user):
    """HUBS-G82: the offer is answered on Businesses, whose card says «Accept the ownership» (the panel has no
    ``/ownership/<id>`` page), and the outgoing owner, who stays as an administrator, finds the business there."""
    olga, ana = make_user("olga@example.com", language="en"), make_user("ana@example.com", language="en")
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
    assert f"{BASE}/dashboard/businesses\n" in f"{offer.body}\n"
    assert "/ownership/" not in offer.body
    assert f"{BASE}/dashboard/businesses/{hub.id}" in accepted.body
    assert "/settings" not in accepted.body


def transfer_of(hub, olga, ana):
    return HubOwnershipTransfer.objects.create(
        hub=hub,
        from_user=olga,
        to_user=ana,
        from_email=olga.email,
        to_email=ana.email,
        expires_at=timezone.now() + timedelta(days=7),
    )


def test_the_offer_of_a_paid_business_says_until_when_it_is_paid_and_where_it_is_kept(hub, make_user):
    """HUBS-F28: the plan goes with the business until the end of its paid period; the new owner keeps it with
    their card in Billing › Subscriptions."""
    olga, ana = make_user("olga@example.com", language="en"), make_user("ana@example.com", language="es")

    emails.send_ownership_offer(transfer_of(hub, olga, ana), base_url=BASE, paid_until=PAID_UNTIL)

    (offer,) = mail.outbox
    assert day(PAID_UNTIL, "es") in offer.body
    assert f"{BASE}/dashboard/billing/subscriptions" in offer.body


def test_the_acceptance_tells_the_previous_owner_until_when_their_card_paid(hub, make_user):
    olga, ana = make_user("olga@example.com", language="es"), make_user("ana@example.com", language="en")

    emails.send_ownership_accepted(transfer_of(hub, olga, ana), base_url=BASE, paid_until=PAID_UNTIL)

    (accepted,) = mail.outbox
    assert day(PAID_UNTIL, "es") in accepted.body


def test_the_mails_of_a_business_on_free_say_nothing_of_a_plan(hub, make_user):
    olga, ana = make_user("olga@example.com", language="en"), make_user("ana@example.com", language="en")
    transfer = transfer_of(hub, olga, ana)

    emails.send_ownership_offer(transfer, base_url=BASE)
    emails.send_ownership_accepted(transfer, base_url=BASE)

    offer, accepted = mail.outbox
    assert "/billing" not in offer.body
    assert "/billing" not in accepted.body


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
    assert f"{BASE}/dashboard/businesses" in message.body


@pytest.mark.parametrize("unpaid", [False, True])
def test_the_deletion_leads_to_the_copy_of_the_data_in_the_panel_never_to_the_file(hub, make_user, unpaid):
    """HUBS-F18 and HUBS-F20 (the day-180 deletion): the copy the Hub makes of the business's data is downloaded from
    the business's page (the panel asks the Hub for a link of 15 minutes there), so this link never expires."""
    owner = make_user("olga@example.com", language="en")
    hub.deletion_requested_at = timezone.now()

    emails.send_deletion(hub, owner, base_url=BASE, unpaid=unpaid)

    (message,) = mail.outbox
    assert f"Download a full copy of its data: {BASE}/dashboard/businesses/{hub.id}" in message.body
    assert "X-Amz" not in message.body


def test_the_deletion_leads_to_the_copy_in_spanish(hub, make_user):
    owner = make_user("olga@example.com", language="es")
    hub.deletion_requested_at = timezone.now()

    emails.send_deletion(hub, owner, base_url=BASE)

    (message,) = mail.outbox
    assert f"Descarga una copia completa de sus datos: {BASE}/dashboard/businesses/{hub.id}" in message.body


@pytest.mark.parametrize(
    ("language", "subject", "line"),
    [
        ("en", "The copy of the data of Bar Manolo is ready", "Download it from {url} until {date}."),
        ("es", "La copia de los datos de Bar Manolo está lista", "Descárgala desde {url} hasta el {date}."),
    ],
)
def test_the_copy_ready_mail_leads_to_the_business_page_until_it_is_erased(hub, make_user, language, subject, line):
    """«We'll let you know» of the business's page, kept: the copy of a deleted business's data is ready."""
    owner = make_user("olga@example.com", language=language)
    hub.deletion_requested_at = timezone.now()

    assert emails.send_data_copy_ready(hub, owner, base_url=BASE) is True

    (message,) = mail.outbox
    assert message.to == ["olga@example.com"]
    assert message.subject == subject
    assert line.format(url=f"{BASE}/dashboard/businesses/{hub.id}", date=day(hub.purge_after, language)) in message.body


def test_the_copy_ready_mail_without_an_owner_is_not_sent_and_says_so(hub, caplog):
    hub.deletion_requested_at = timezone.now()

    assert emails.send_data_copy_ready(hub, None, base_url=BASE) is False

    assert mail.outbox == []
    assert f"hubs.mail.data_copy_unsent hub={hub.pk}" in caplog.text


def test_the_ready_mail_opens_the_business(hub, make_user, settings):
    """HUBS-F04 (HUBS-G68) and HUBS-F07 (HUBS-G91): once the Hub reports it ready, the owner hears it with
    the way in (the jump, which starts at the business) and the business's page in the panel."""
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"
    owner = make_user("olga@example.com", language="es")

    emails.send_ready(hub, owner, base_url=BASE)

    (message,) = mail.outbox
    assert message.to == ["olga@example.com"]
    assert message.subject == "Bar Manolo ya está listo"
    assert "https://bar-manolo.erplora.com/auth/login?next=/" in message.body
    assert f"{BASE}/dashboard/businesses/{hub.id}" in message.body


def test_a_mail_that_cannot_leave_is_logged_not_raised(
    hub, make_user, settings, caplog
):
    owner = make_user("olga@example.com")
    hub.deletion_requested_at = timezone.now()
    # A mailer that cannot connect (nothing listens there).
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                                    "OPTIONS": {"host": "127.0.0.1", "port": 9, "timeout": 1}}}

    assert emails.send_deletion(hub, owner, base_url=BASE) is False
    assert "hubs.mail.not_sent" in caplog.text


def test_the_base_url_of_a_request_or_the_public_host(rf, settings):
    settings.PUBLIC_HOST = "erplora.com"

    assert (
        emails.base_url(rf.get("/", HTTP_HOST="localhost:8001"))
        == "http://localhost:8001"
    )
    assert emails.base_url(None) == "https://erplora.com"


# --- Branded, as text and as HTML (ACCOUNTS-F46) -------------------------------------------------------------


def senders(hub, make_user, language):
    olga = make_user("olga@example.com", first_name="Olga", language=language)
    ana = make_user("ana@example.com", language=language)
    member = HubMember.objects.create(
        hub=hub, user=ana, invited_by=olga, invitation_message="¡Bienvenida!",
        invitation_expires_at=timezone.now() + timedelta(days=7),
    )
    transfer = transfer_of(hub, olga, ana)
    hub.deletion_requested_at = timezone.now()
    return {
        "invitation": lambda: emails.send_invitation(member, base_url=BASE, new_account=True),
        "ownership_offer": lambda: emails.send_ownership_offer(transfer, base_url=BASE, paid_until=PAID_UNTIL),
        "ownership_accepted": lambda: emails.send_ownership_accepted(transfer, base_url=BASE, paid_until=PAID_UNTIL),
        "deletion": lambda: emails.send_deletion(hub, olga, base_url=BASE, unpaid=True),
        "ready": lambda: emails.send_ready(hub, olga, base_url=BASE),
        "data_copy_ready": lambda: emails.send_data_copy_ready(hub, olga, base_url=BASE),
        "suspension": lambda: emails.send_suspension_notice(
            hub, olga, base_url=BASE, delete_on=PAID_UNTIL, final=True
        ),
    }


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(
    "family", ["invitation", "ownership_offer", "ownership_accepted", "deletion", "ready", "data_copy_ready", "suspension"]
)
def test_every_mail_of_hubs_is_branded_in_its_recipients_language(hub, make_user, family, language):
    assert senders(hub, make_user, language)[family]() is True

    (message,) = mail.outbox
    assert_branded(message, language)
