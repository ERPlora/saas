"""WHATSAPP-G12 · The mail «Connect WhatsApp again» to the business's owner, in the owner's language.

Case of the old product's ``test_token_refresh.py`` (what to do, the number, the business, translated); its
``parcial`` (the mail left in the server's language, not the person's) is fixed: the owner's ``language`` rules.
"""

from django.core import mail

from whatsapp import emails


def send(language="en"):
    return emails.send_reconnect(
        to="ana@example.com", language=language, business="Bar Manolo", number="+34 910 00 00 00", slug="bar-manolo"
    )


def test_the_mail_names_the_number_the_business_and_where_to_act(settings):
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"

    assert send() is True

    message = mail.outbox[0]
    assert message.to == ["ana@example.com"]
    assert "+34 910 00 00 00" in message.subject
    assert "Bar Manolo" in message.body
    assert "https://bar-manolo.erplora.com" in message.body
    assert "/auth/callback" not in message.body


def test_the_mail_speaks_the_owners_language():
    send("es")

    message = mail.outbox[0]
    assert message.subject.startswith("Hay que actuar")
    assert "WhatsApp" in message.body and "Bar Manolo" in message.body


def test_a_mail_that_cannot_leave_is_logged_never_raised(monkeypatch, caplog):
    def refuse(*args, **kwargs):
        raise OSError("the mail server is down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", refuse)

    assert send() is False
    assert "whatsapp.mail.not_sent" in caplog.text
