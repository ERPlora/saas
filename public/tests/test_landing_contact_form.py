"""The contact form ``/contact/submit/`` (public/landing.py): what it mails, what it refuses, its limit per address,
what it keeps of what the visitor typed and the topic a visitor arrives with.

* The contact mail is rendered from ``public/templates/public/email/`` and sent branded, as text and as HTML
  (``base.emails``), to ``SUPPORT_EMAIL``; the limit per address reads the address the load balancer saw (the last
  hop of ``X-Forwarded-For``), never the balancer's own.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.test import override_settings

from public import landing
from public.tests.landing_pages import CONTACT, HOME, SUBMIT, VALID, form_of, html_of, messages_of, submit
from public.tests.test_cookies import VALKEY_DOWN

pytestmark = [pytest.mark.django_db]


# --- The contact form: /contact/submit/ -------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_limits():
    """The limit per address lives in the cache: each test starts with a clean bucket."""
    cache.clear()
    yield
    cache.clear()


def test_the_submit_route_is_post_only(client):
    assert client.get(SUBMIT).status_code == 405


def test_a_valid_message_is_mailed_to_support_and_answers_with_a_redirect(
    client, settings
):
    settings.SUPPORT_EMAIL = "support@erplora.test"

    response = submit(client, next="/contact/")

    assert response.status_code == 302
    assert response["Location"] == "/contact/#contacto"
    (sent,) = mail.outbox
    assert sent.to == ["support@erplora.test"]
    assert sent.from_email == settings.DEFAULT_FROM_EMAIL
    assert sent.subject == "Contact Form: John Doe"
    for line in (
        "Name: John Doe",
        "Email: john.doe@example.com",
        "Phone: +34 600 000 000",
        "Hello, I would like more information about ERPlora.",
    ):
        assert line in sent.body, line
    assert any("Thanks" in message for message in messages_of(response))


def test_without_a_phone_the_mail_says_so(client):
    submit(client, phone="")

    assert "Phone: Not provided" in mail.outbox[0].body


def test_the_mail_body_is_plain_text_never_escaped_html(client):
    submit(client, message="Tom & Jerry <b>bold</b>")

    assert "Tom & Jerry <b>bold</b>" in mail.outbox[0].body


def test_a_name_cannot_inject_a_header_into_the_subject(client):
    response = submit(client, first_name="John\nBcc: victim@example.com")

    assert response.status_code == 302
    (sent,) = mail.outbox
    assert "\n" not in sent.subject
    assert sent.bcc == []


@pytest.mark.parametrize("missing", ["first_name", "last_name", "email", "message"])
def test_every_field_but_the_phone_is_required(client, missing):
    response = submit(client, **{missing: "  "})

    assert response.status_code == 302
    assert mail.outbox == []
    assert any(
        "All fields are required" in message for message in messages_of(response)
    )


def test_an_empty_post_redirects_with_the_error(client):
    response = client.post(SUBMIT, {})

    assert response.status_code == 302
    assert response["Location"] == "/#contacto"
    assert mail.outbox == []


def test_an_invalid_email_is_refused(client):
    response = submit(client, email="not-an-address")

    assert response.status_code == 302
    assert mail.outbox == []
    assert any("valid email" in message for message in messages_of(response))


def test_an_external_next_is_refused(client):
    response = submit(client, next="https://example.com/phishing")

    assert response.status_code == 302
    assert response["Location"] == "/#contacto"


def test_without_next_it_goes_back_to_the_referer(client):
    response = client.post(SUBMIT, VALID, HTTP_REFERER="http://testserver/pricing/")

    assert response["Location"] == "http://testserver/pricing/#contacto"


def test_an_anchor_already_in_next_is_not_doubled(client):
    response = submit(client, next="/pricing/#faq")

    assert response["Location"] == "/pricing/#faq"


def test_a_mail_failure_is_told_to_the_visitor_and_logged(client, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise OSError("SMTP down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", broken)

    response = submit(client)

    assert response.status_code == 302
    assert any("something went wrong" in message for message in messages_of(response))
    assert "Contact form message could not be sent" in caplog.text


def test_the_messages_are_translated(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

    response = submit(client, message="")

    assert messages_of(response) and all(
        "All fields are required" not in message for message in messages_of(response)
    )


@override_settings(RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="2/h")
def test_the_form_is_limited_per_address(client):
    """The form is protected by a limit per address."""
    for _ in range(2):
        assert submit(client).status_code == 302
    assert len(mail.outbox) == 2

    throttled = submit(client)

    assert throttled.status_code == 302
    assert len(mail.outbox) == 2, "a throttled message must not be mailed"
    assert any("Too many messages" in message for message in messages_of(throttled))


@override_settings(
    RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="1/h", TRUSTED_PROXY_HOPS=1
)
def test_the_limit_is_per_visitor_not_per_load_balancer(client):
    """Behind the ALB every request comes from the balancer: the visitor is the last hop of
    ``X-Forwarded-For`` (the address the balancer saw; ``public.client_ip``). Keyed on the
    balancer, the whole internet would share one bucket; on the first hop, a forged header would
    be a fresh one per message."""
    first = client.post(SUBMIT, VALID, HTTP_X_FORWARDED_FOR="203.0.113.7")
    second = client.post(SUBMIT, VALID, HTTP_X_FORWARDED_FOR="198.51.100.9")
    forged = client.post(
        SUBMIT, VALID, HTTP_X_FORWARDED_FOR="192.0.2.50, 203.0.113.7"
    )

    assert (first.status_code, second.status_code) == (302, 302)
    assert len(mail.outbox) == 2
    assert any("Too many messages" in message for message in messages_of(forged))


@override_settings(
    RATELIMIT_ENABLE=True, CONTACT_FORM_RATELIMIT="1/h", CACHES=VALKEY_DOWN
)
def test_with_valkey_down_the_form_still_sends(client):
    """The limit cannot count without the cache: it lets the message through (fail open) instead
    of refusing every visitor. Never a 500."""
    responses = [submit(client), submit(client)]

    assert [response.status_code for response in responses] == [302, 302]
    assert len(mail.outbox) == 2


def test_the_visitor_address_is_remote_addr(rf):
    """``public.client_ip`` already put the visitor in ``REMOTE_ADDR``: the header is its job."""
    forwarded = rf.post(
        SUBMIT, HTTP_X_FORWARDED_FOR="203.0.113.7", REMOTE_ADDR="192.0.2.1"
    )
    plain = rf.post(SUBMIT, REMOTE_ADDR="192.0.2.1")

    assert landing.visitor_address(None, forwarded) == "192.0.2.1"
    assert landing.visitor_address(None, plain) == "192.0.2.1"


@pytest.mark.parametrize("address", ["", "not-an-ip"])
def test_without_a_real_address_the_visitor_shares_the_unknown_bucket(rf, address):
    """The limiter masks the key with ``ipaddress``: junk there would be a 500 on a public door."""
    request = rf.post(SUBMIT, REMOTE_ADDR=address)

    assert landing.visitor_address(None, request) == landing.UNKNOWN_ADDRESS


# --- The message reaches support with the visitor to answer, and nothing typed is lost ---


def test_the_mail_to_support_replies_to_the_visitor(client):
    """Support answers with «Reply»: the mail comes from our sender but replies to the visitor."""
    submit(client)

    (sent,) = mail.outbox
    assert sent.reply_to == ["john.doe@example.com"]
    assert sent.from_email == settings.DEFAULT_FROM_EMAIL


@pytest.mark.parametrize(
    "overrides", [{"last_name": ""}, {"email": "not-an-address"}], ids=["required", "email"]
)
def test_a_refused_message_comes_back_with_what_was_typed(client, overrides):
    response = submit(client, next=CONTACT, **overrides)

    form = form_of(client.get(response["Location"].split("#")[0]).content.decode())
    assert 'value="John"' in form
    assert 'value="+34 600 000 000"' in form
    assert "Hello, I would like more information about ERPlora." in form
    assert f'value="{overrides.get("email", VALID["email"])}"' in form


def test_a_mail_failure_keeps_what_was_typed_on_the_home_too(client, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("SMTP down")

    monkeypatch.setattr("django.core.mail.EmailMessage.send", broken)

    response = submit(client, next=HOME)

    assert 'value="John"' in form_of(html_of(client, response["Location"].split("#")[0]))


def test_what_was_typed_is_shown_once_and_never_after_a_sent_message(client):
    submit(client, next=CONTACT, last_name="")
    client.get(CONTACT)

    assert 'value="John"' not in form_of(html_of(client, CONTACT))
    submit(client, next=CONTACT)
    assert 'value="John"' not in form_of(html_of(client, CONTACT))


def test_what_was_typed_is_escaped_when_it_comes_back(client):
    submit(client, next=CONTACT, last_name="", first_name='"><script>x()</script>')

    form = form_of(html_of(client, CONTACT))
    assert "<script>x()" not in form
    assert "&quot;&gt;&lt;script&gt;" in form


# --- Arriving from another page keeps what the visitor came for ----------------------------


def test_the_collaborate_button_opens_the_form_on_its_topic(client):
    html = html_of(client, "/collaborate/")

    assert f'href="{CONTACT}?subject=collaborate"' in html


def test_a_known_topic_rides_with_the_form_and_names_the_mail(client):
    form = form_of(html_of(client, f"{CONTACT}?subject=collaborate"))

    assert '<input type="hidden" name="subject" value="collaborate">' in form
    submit(client, subject="collaborate")
    assert mail.outbox[0].subject == "Contact Form [Collaborator program]: John Doe"


def test_the_security_button_opens_the_form_on_its_topic(client):
    html = html_of(client, "/security/")

    assert f'href="{CONTACT}?subject=security"' in html
    submit(client, subject="security")
    assert mail.outbox[0].subject == "Contact Form [Security]: John Doe"


@pytest.mark.parametrize("subject", ["Collaborator Program", "<b>x</b>", "x" * 300, ""])
def test_an_unknown_topic_is_ignored(client, subject):
    form = form_of(html_of(client, f"{CONTACT}?subject={subject}"))

    assert 'name="subject"' not in form
    submit(client, subject=subject)
    assert mail.outbox[0].subject == "Contact Form: John Doe"
