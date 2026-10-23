"""Every mail of erplora.com leaves branded, as HTML and as text, in its recipient's language (ACCOUNTS-F46; PLAN-SAAS
§7, block 13; the old saas#1044: 11 of 14 account mails left without the brand and without HTML).

Ported in structure from ERPlora/saas ``apps/core/tests/test_branded_emails.py`` (origin/develop): each family is
sent by its own sender, never rendered by hand, and each mail must be an ``EmailMultiAlternatives`` with one
``text/html`` part on the common template (the logo served by erplora.com, the brand's colour, the footer, CSS
inline and no other resource from the network) and a text part that says the same, in English and in Spanish.
allauth's mails are found on disk, as the old test did: a template allauth adds is checked the day it ships.
The mails of hubs (``hubs/emails.py``) still leave as plain text and are not in this list.
"""

import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from html import unescape
from pathlib import Path
from types import SimpleNamespace

import allauth
import pytest
from allauth.account.adapter import get_adapter
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.utils import translation
from django.utils.html import strip_tags
from django.utils.translation import gettext

from accounts import emails as account_emails
from base import emails
from billing import emails as billing_emails
from fiscal import emails as fiscal_emails
from fiscal.models import RepresentationGrant
from whatsapp import emails as whatsapp_emails

pytestmark = pytest.mark.django_db

LOGO = "https://erplora.com/static/public/img/logo.png"
BRAND_COLOUR = "#1496d6"
ADDRESS = "ana@example.com"
HUB = SimpleNamespace(id=uuid.UUID("0199a0c4-7f3e-7000-8000-000000000001"), name="Mi Hub")


@pytest.fixture(autouse=True)
def production_hosts(settings):
    """The hosts of production: a mail never points to a development host because of its template."""
    settings.PUBLIC_HOST = "erplora.com"
    settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"


def html_of(message) -> str:
    assert isinstance(message, EmailMultiAlternatives), type(message).__name__
    parts = [content for content, mimetype in message.alternatives if mimetype == "text/html"]
    assert len(parts) == 1, message.alternatives
    return parts[0]


def words(text: str) -> str:
    return " ".join(text.split())


def readable(html_body: str) -> str:
    """What a person reads in the HTML part: its body's text, unescaped."""
    return words(unescape(strip_tags(html_body.split("<body", 1)[1])))


def footer(language: str) -> str:
    with translation.override(language):
        return gettext("Sent by ERPlora")


def assert_branded(message, language: str) -> None:
    html_body = html_of(message)
    assert f'<html lang="{language}"' in html_body
    assert f'src="{LOGO}"' in html_body
    assert 'alt="ERPlora"' in html_body
    assert BRAND_COLOUR in html_body
    lowered = html_body.lower()
    for tag in ("<style", "<link", "<script", "<iframe", "<form"):
        assert tag not in lowered, tag
    # The logo is the only thing fetched from the network.
    assert set(re.findall(r'\b(?:src|background)="([^"]*)"', html_body)) == {LOGO}
    assert "url(" not in lowered
    assert "localhost" not in lowered and "127.0.0.1" not in lowered
    assert footer(language) in readable(html_body)
    # The text part says the same as the HTML part, line by line (a list's dash aside).
    text = readable(html_body)
    for line in message.body.splitlines():
        line = words(line).removeprefix("- ")
        if line:
            assert line in text, line


# --- The common piece --------------------------------------------------------------------------------------


def test_a_branded_mail_is_text_and_html():
    message = emails.branded_message(
        "Your ERPlora code: 042317", ["Type this code:", "", "042317"], [ADDRESS], language="en", code="042317"
    )

    assert message.body == "Type this code:\n\n042317\n"
    assert message.to == [ADDRESS]
    assert message.subject == "Your ERPlora code: 042317"
    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert_branded(message, "en")
    assert "<title>Your ERPlora code: 042317</title>" in html_of(message)


def test_the_language_is_the_recipients_not_the_active_one():
    with translation.override("en"):
        message = emails.branded_message("Asunto", ["Hola"], [ADDRESS], language="es")

    assert_branded(message, "es")
    assert footer("es") != footer("en")


def test_what_the_mail_says_is_escaped_and_its_links_clickable():
    message = emails.branded_message(
        "Subject",
        ["<script>alert(1)</script> & co", "Pay it: https://erplora.com/billing", "Help: www.erplora.com/help"],
        [ADDRESS],
        language="en",
    )

    html_body = html_of(message)
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co" in html_body
    assert '<a href="https://erplora.com/billing"' in html_body
    # A link written without its scheme opens over HTTPS, never HTTP.
    assert '<a href="https://www.erplora.com/help"' in html_body


def test_lines_of_a_paragraph_stay_together_and_paragraphs_apart():
    html_body = emails.branded_html(["one", "two", "", "three"], language="en")

    assert re.search(r"<p[^>]*>one<br>two</p>", html_body)
    assert re.search(r"<p[^>]*>three</p>", html_body)


def test_the_code_stands_on_its_own_box():
    html_body = emails.branded_html(["Type it:", "", "042317"], language="en", code="042317")

    assert re.search(r"<p[^>]*monospace[^>]*>042317</p>", html_body)


def test_the_sender_keeps_its_reply_to_and_headers():
    message = emails.branded_message(
        "S", ["x"], [ADDRESS], language="en", reply_to=["visitor@example.com"], headers={"X-ERPlora-Notice": "n"}
    )

    assert message.reply_to == ["visitor@example.com"]
    assert message.extra_headers == {"X-ERPlora-Notice": "n"}


# --- Every family, sent by its own sender ------------------------------------------------------------------

LANGUAGES = ("en", "es")


def invoice(language: str) -> SimpleNamespace:
    return SimpleNamespace(
        pk=1,
        payment_status="paid",
        payer_account=None,
        payer_email="facturas@example.com",
        language=language,
        kind="invoice",
        number="ERP-2026-00500",
        business_name="Mi Hub",
        issued_on=date(2026, 8, 1),
        net=Decimal("100.00"),
        tax=Decimal("21.00"),
        tax_rate=Decimal("21.00"),
        total=Decimal("121.00"),
    )


def grant(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        pk=uuid.UUID("0199a0c4-7f3e-7000-8000-000000000002"),
        hub=HUB,
        hub_id=HUB.id,
        version=2,
        status=status,
        reason="The signature cannot be read.",
    )


def oss_notice() -> SimpleNamespace:
    return SimpleNamespace(
        kind="crossed",
        reason="current_year",
        year=2026,
        accumulated_cents=1_020_000,
        threshold_cents=1_000_000,
        invoice=SimpleNamespace(number="ERP-2026-00500"),
        effective_from=date(2026, 9, 1),
    )


SENDERS = {
    "accounts.email_code": lambda language: account_emails.send_email_code(ADDRESS, "042317", language=language),
    "accounts.email_changed": lambda language: account_emails.send_email_changed(
        ADDRESS, "ana@new.example", language=language
    ),
    "accounts.api_key_created": lambda language: account_emails.send_api_key_created(
        ADDRESS, "Till", ["hubs.read", "billing.read"], language=language
    ),
    "billing.invoice_issued": lambda language: billing_emails.send_invoice_issued(invoice(language)),
    "billing.payment_failed": lambda language: billing_emails.send_payment_failed(
        HUB, to=ADDRESS, language=language, amount=Decimal("29.99"), declined=True, suspends_on=date(2026, 11, 1)
    ),
    "billing.business_suspended": lambda language: billing_emails.send_business_suspended(
        HUB, to=ADDRESS, language=language, amount=Decimal("29.99")
    ),
    "fiscal.business": lambda language: fiscal_emails._tell_the_business(
        grant(RepresentationGrant.Status.RETURNED), SimpleNamespace(language=language, email=ADDRESS)
    ),
    "whatsapp.reconnect": lambda language: whatsapp_emails.send_reconnect(
        to=ADDRESS, language=language, business="Mi Hub", number="+34 600 000 000", slug="mi-hub"
    ),
}


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("family", sorted(SENDERS))
def test_a_mail_to_a_person_is_branded_in_their_language(family, language):
    SENDERS[family](language)

    [message] = mail.outbox
    assert_branded(message, language)


# The team's mails, in the language the team reads.


def test_the_support_report_is_branded():
    account_emails.send_support_report(
        SimpleNamespace(email=ADDRESS), subject="The till froze", description="It froze.", context=[("Page", "/")]
    )

    [message] = mail.outbox
    assert message.reply_to == [ADDRESS]
    assert_branded(message, "en")


def test_the_oss_notice_is_branded():
    billing_emails.send_oss_notice(oss_notice())

    [message] = mail.outbox
    assert message.extra_headers["X-ERPlora-Notice"] == "billing.oss_crossed"
    assert_branded(message, settings.LANGUAGE_CODE)


def test_the_review_desks_mail_is_branded():
    fiscal_emails._tell_the_desk(grant(RepresentationGrant.Status.SUBMITTED))

    [message] = mail.outbox
    assert_branded(message, fiscal_emails.DESK_LANGUAGE)


def test_the_contact_form_mail_is_branded(client):
    cache.clear()
    client.post(
        "/contact/submit/",
        {"first_name": "John", "last_name": "Doe", "email": "john@example.com", "message": "More about ERPlora."},
    )

    [message] = mail.outbox
    assert message.reply_to == ["john@example.com"]
    assert_branded(message, "en")


# --- allauth's mails, every template it ships and ours -----------------------------------------------------

ALLAUTH_TEMPLATES = Path(allauth.__file__).parent / "templates"
OUR_TEMPLATES = Path(settings.BASE_DIR) / "templates"
MAIL_FOLDERS = ("account/email", "socialaccount/email", "mfa/email")


def mail_prefixes() -> list[str]:
    found = set()
    for root in (ALLAUTH_TEMPLATES, OUR_TEMPLATES):
        for folder in MAIL_FOLDERS:
            for path in (root / folder).glob("*_message.txt"):
                name = path.name.removesuffix("_message.txt")
                if name != "base":
                    found.add(f"{folder}/{name}")
    return sorted(found)


ALLAUTH_CONTEXT = {
    "code": "042317",
    "user_display": "Ana",
    "username": "ana",
    "password_reset_url": "https://erplora.com/password/reset/key/1-abc",
    "activate_url": "https://erplora.com/verify-email/abc",
    "from_email": "ana@old.example",
    "to_email": ADDRESS,
    "deleted_email": "ana@old.example",
    "provider": SimpleNamespace(name="Google"),
    "account": SimpleNamespace(get_provider=lambda: SimpleNamespace(name="Google")),
    "ip": "203.0.113.7",
    "user_agent": "Firefox <on> Linux",
    "timestamp": datetime(2026, 10, 23, 9, 30, tzinfo=UTC),
    "support_email": "support@erplora.com",
}


def test_every_allauth_mail_is_found():
    assert "account/email/login_code" in mail_prefixes()
    assert "socialaccount/email/account_connected" in mail_prefixes()


@pytest.fixture
def allauth_context():
    user = get_user_model().objects.create_user(email=ADDRESS, password="x-Very-long-1", first_name="Ana")
    return {**ALLAUTH_CONTEXT, "user": user}


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("prefix", mail_prefixes())
def test_every_allauth_mail_is_branded(prefix, language, allauth_context):
    with translation.override(language):
        get_adapter().send_mail(prefix, ADDRESS, allauth_context)

    [message] = mail.outbox
    assert_branded(message, language)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_sign_in_codes_box_is_the_code_alone(language, allauth_context):
    with translation.override(language):
        get_adapter().send_mail("account/email/login_code", ADDRESS, allauth_context)

    [message] = mail.outbox
    assert re.search(r"<p[^>]*monospace[^>]*>042317</p>", html_of(message))


@pytest.mark.parametrize(
    "path", sorted(p.relative_to(OUR_TEMPLATES) for f in MAIL_FOLDERS for p in (OUR_TEMPLATES / f).glob("*_message.txt"))
)
def test_each_mail_template_of_ours_has_its_html(path):
    """A text template of ours (the wrapper and the notices it wrote) goes with its HTML, saying the same."""
    assert (OUR_TEMPLATES / str(path).replace("_message.txt", "_message.html")).is_file()
