"""The mails of accounts, each in its recipient's language (``accounts.emails``): the code that proves a new
address (Account → «Change email») and the notice to the old one once the change is done (what Google, GitHub
and Stripe send, so a change nobody asked for does not go unnoticed). Branded, as text and as HTML: what they look
like is ``base/tests/test_emails.py``'s (ACCOUNTS-F46)."""

import pytest
from django.core import mail

from accounts import emails

pytestmark = pytest.mark.django_db


def test_the_code_goes_to_the_new_address_alone_on_its_line(settings):
    assert emails.send_email_code("ana@new.example", "042317", language="en") is True

    [message] = mail.outbox
    assert message.to == ["ana@new.example"]
    assert message.subject == "Your ERPlora code: 042317"
    assert "\n042317\n" in message.body
    assert "15 minutes" in message.body
    assert message.from_email == settings.DEFAULT_FROM_EMAIL


def test_in_spanish():
    emails.send_email_code("ana@new.example", "042317", language="es")

    [message] = mail.outbox
    assert message.subject == "Tu código de ERPlora: 042317"
    assert "15 minutos" in message.body


def test_a_mail_that_cannot_leave_says_so_and_is_logged(monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise OSError("SMTP down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", broken)

    assert emails.send_email_code("ana@new.example", "042317", language="en") is False
    assert "accounts.mail_failed" in caplog.text
    assert "042317" not in caplog.text


def test_the_old_address_is_told_and_given_the_support_address(settings):
    emails.send_email_changed("ana@example.com", "ana@new.example", language="en")

    [message] = mail.outbox
    assert message.to == ["ana@example.com"]
    assert "ana@new.example" in message.body
    assert settings.SUPPORT_EMAIL in message.body


def test_a_new_api_key_is_told_with_its_name_and_permissions_in_spanish(settings):
    emails.send_api_key_created("ana@example.com", "Gestoría", ["billing.read", "hubs.read"], language="es")

    [message] = mail.outbox
    assert message.subject == "Nueva clave de API en tu cuenta de ERPlora"
    assert "Gestoría" in message.body
    assert "Facturas · lectura, Negocios · lectura" in message.body
    assert settings.SUPPORT_EMAIL in message.body
