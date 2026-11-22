"""The mail that tells the payer their invoice is issued.

Without it the customer paid and got nothing, and had to remember to look in the panel. The mail LINKS to Billing
instead of attaching the PDF: the PDF is the platform hub's and carries the QR only once issued. It leaves
the first time the platform hub issues the invoice (``billing.invoice.apply_fiscal_status``), once.

Changed: in the payer's language, branded as text and as HTML on the common template (``base.emails``, whose
shape ``base/tests/test_emails.py`` checks; ACCOUNTS-F46); the link is the panel's Billing page, not the old
invoice page; the recipient is the payer's billing e-mail (the invoice's addressee), the account's otherwise.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core import mail

from billing import emails
from billing.models import Invoice, InvoiceLine, PaymentFailure

pytestmark = pytest.mark.django_db


@pytest.fixture
def invoice(make_user):
    payer = make_user(
        "buyer@example.com", first_name="Ioan", last_name="Beilic", language="es"
    )
    issued = Invoice.objects.create(
        stripe_invoice_id="in_1",
        business_name="Mi Hub",
        payer_account=payer,
        payer_email="facturas@example.com",
        language="es",
        payment_status="paid",
        series="ERP",
        sequence=500,
        number="ERP-2026-00500",
        issued_on=date(2026, 8, 1),
        net_cents=100,
        tax_cents=21,
        total_cents=121,
        tax_rate=Decimal("21.00"),
        tax_country="ES",
    )
    InvoiceLine.objects.create(
        invoice=issued,
        position=1,
        description="Plan Starter",
        net_cents=100,
        tax_cents=21,
        total_cents=121,
    )
    return issued


class TestTheMailGoesOut:
    def test_it_reaches_the_payers_billing_address(self, invoice):
        assert emails.send_invoice_issued(invoice) is True

        assert [message.to for message in mail.outbox] == [["facturas@example.com"]]

    def test_without_a_billing_address_it_reaches_the_account(self, invoice):
        invoice.payer_email = ""

        emails.send_invoice_issued(invoice)

        assert mail.outbox[0].to == ["buyer@example.com"]

    def test_the_subject_names_the_invoice(self, invoice):
        emails.send_invoice_issued(invoice)

        assert "ERP-2026-00500" in mail.outbox[0].subject

    def test_it_speaks_the_payers_language(self, invoice):
        emails.send_invoice_issued(invoice)

        assert "Factura" in mail.outbox[0].subject

    def test_it_shows_the_vat_breakdown(self, invoice):
        """The figure the invoice once got wrong: if it is missing here, nobody notices."""
        emails.send_invoice_issued(invoice)

        body = mail.outbox[0].body
        assert "1,21" in body and "0,21" in body and "1,00" in body

    def test_it_links_to_billing(self, invoice, settings):
        settings.PUBLIC_HOST = "erplora.com"

        emails.send_invoice_issued(invoice)

        assert "https://erplora.com/dashboard/billing" in mail.outbox[0].body


class TestItIsNotSentWhenItShouldNot:
    def test_nobody_to_send_it_to(self, invoice):
        """The account goes with SET_NULL (GDPR 17(3)); the invoice survives, and without an address there is
        nobody to tell."""
        invoice.payer_account = None
        invoice.payer_email = ""

        assert emails.send_invoice_issued(invoice) is False
        assert mail.outbox == []

    def test_an_unpaid_invoice(self, invoice):
        invoice.payment_status = "open"

        assert emails.send_invoice_issued(invoice) is False
        assert mail.outbox == []


def test_a_mail_that_cannot_leave_raises_so_it_is_sent_again_later(invoice, monkeypatch):
    """A failed mail is not «sent»; ``reconcile_platform_invoices`` sends it again."""
    def broken(*args, **kwargs):
        raise ConnectionRefusedError("SMTP down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", broken)

    with pytest.raises(emails.MailNotSent):
        emails.send_invoice_issued(invoice)


@pytest.mark.parametrize("notice", ["invoice", "payment_failed", "business_suspended"])
def test_a_mail_whose_html_cannot_be_drawn_is_not_sent_either(notice, invoice, monkeypatch):
    """ACCOUNTS-F46: drawing the branded HTML is part of sending it, so a failure there is ``MailNotSent`` too and
    the mail is sent again later, never an error that stops whoever asked for it."""
    def broken(*args, **kwargs):
        raise OSError("the templates cannot be read")

    monkeypatch.setattr("base.emails.render_to_string", broken)
    hub = SimpleNamespace(id="0199a0c4-7f3e-7000-8000-000000000001", name="Mi Hub")
    send = {
        "invoice": lambda: emails.send_invoice_issued(invoice),
        "payment_failed": lambda: emails.send_payment_failed(
            hub, unpaid_invoice(), to="a@example.com", language="en", amount=Decimal("29.99")
        ),
        "business_suspended": lambda: emails.send_business_suspended(
            hub, to="a@example.com", language="en", amount=Decimal("29.99")
        ),
    }[notice]

    with pytest.raises(emails.MailNotSent):
        send()
    assert mail.outbox == []


@pytest.mark.parametrize("reason", PaymentFailure.Reason.values)
def test_every_line_of_the_unpaid_mail_reaches_a_spanish_payer_in_spanish(reason):
    """BILLING-F16: the mail of a renewal that could not be charged says each of its lines in the payer's language,
    also why the card was declined: none is left in the English source (a sentence rewritten without its
    translation). The links and the amounts aside, no line of the Spanish mail is a line of the English one."""
    hub = SimpleNamespace(id="0199a0c4-7f3e-7000-8000-000000000001", name="Mi Hub")
    for language in ("en", "es"):
        emails.send_payment_failed(
            hub, unpaid_invoice(reason), to="a@example.com", language=language, amount=Decimal("29.99")
        )
    english, spanish = (set(message.body.splitlines()) - {""} for message in mail.outbox)

    assert spanish.isdisjoint(english)


def unpaid_invoice(reason: str = PaymentFailure.Reason.PAYMENT_FAILED) -> PaymentFailure:
    """An invoice Stripe could not collect, issued on 25 October: the business keeps working until 1 November."""
    return PaymentFailure(reason=reason, invoice_created_at=datetime(2026, 10, 25, 9, 30, tzinfo=UTC))


UNPAID_HUB = SimpleNamespace(id="0199a0c4-7f3e-7000-8000-000000000001", name="Panadería López")
PAY_IT = "https://erplora.com/dashboard/billing/invoices?business=0199a0c4-7f3e-7000-8000-000000000001"
#: The unpaid mail in each language: its subject, its first line, the line of a declined card and the rest.
UNPAID_MAIL = {
    "en": (
        "We could not charge the plan of Panadería López",
        "We could not charge 1,234.50 € for the plan of Panadería López.\n",
        "The bank declined your card, so we will not try it again: change the card, then pay the invoice yourself.\n",
        "Panadería López keeps working until Nov. 1, 2026. If the invoice is not paid by then, it is suspended. "
        f"Nothing is deleted.\n\nPay it from Billing: {PAY_IT}\n",
    ),
    "es": (
        "No hemos podido cobrar el plan de Panadería López",
        "No hemos podido cobrar 1\xa0234,50 € del plan de Panadería López.\n",
        "El banco rechazó tu tarjeta, así que no volveremos a intentar el cobro con ella: cámbiala y paga tú la "
        "factura.\n",
        "Panadería López sigue funcionando hasta el 1 de noviembre de 2026. Si la factura no se paga antes, se "
        f"suspende. No se borra nada.\n\nPágala en Facturación: {PAY_IT}\n",
    ),
}


@pytest.mark.parametrize("reason", PaymentFailure.Reason.values)
@pytest.mark.parametrize("language", ["en", "es", ""])
def test_the_unpaid_mail_says_how_much_until_when_and_where_to_pay(language, reason):
    """BILLING-F16: the mail of a renewal that could not be charged, word for word, in the payer's language (the
    platform's when the payer has none): how much, why the card is not tried again only when the bank declined
    it, until when the business keeps working (7 days from the invoice) and where to pay. Support filters it by
    its notice header."""
    emails.send_payment_failed(
        UNPAID_HUB, unpaid_invoice(reason), to="pagos@example.com", language=language, amount=Decimal("1234.5")
    )

    [message] = mail.outbox
    told_in = language or "en"
    subject, opening, declined_line, rest = UNPAID_MAIL[told_in]
    assert message.subject == subject
    declined = reason == PaymentFailure.Reason.CARD_DECLINED
    assert message.body == opening + (declined_line if declined else "") + rest
    assert message.to == ["pagos@example.com"]
    assert message.extra_headers == {"X-ERPlora-Notice": "billing.payment_failed"}
    [(html, _)] = message.alternatives
    assert f'<html lang="{told_in}"' in html
