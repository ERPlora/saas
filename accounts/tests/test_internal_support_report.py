"""``POST /internal/support/report``: «Report a problem» from the Hub's user menu (ACCOUNTS-F38, FIX-HUB-BASE-REPORT-PROBLEM-MODAL).

The Hub sends, signed v1 + v2 with ``INTERNAL_SHARED_SECRET`` like ``/internal/auth/redeem``, what the person wrote and
who and where they are: the account of their session, the business and the screen, and their browser. It is the panel's
report (``accounts.support.report``): the same limit per account, the same mail to the support mailbox «Reply-To» the
account, plus the business it comes from and «From: Hub». Nothing is mailed for an account that is not a member of
that business, nor for a call that is not the Hub's.
"""

import json
import time

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings

from accounts.models import HubMembership
from accounts.signing import sign, signed_headers
from accounts.tests.conftest import api_post

pytestmark = pytest.mark.django_db

URL = "/internal/support/report"
SECRET = "test-internal-secret"
HUB_ID = "019a2b3c-4d5e-7f60-8a9b-0c1d2e3f4a5b"
BROWSER = "Mozilla/5.0 (iPad; CPU OS 18_0) ERPlora/1.4"


@pytest.fixture(autouse=True)
def _secret(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.SUPPORT_EMAIL = "support@example.com"


@pytest.fixture(autouse=True)
def _fresh_limit():
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def member(ana):
    HubMembership.objects.create(user=ana, hub_slug="bar-pepe", role=HubMembership.Role.MANAGER)
    return ana


def payload(user, **changes) -> dict:
    return {
        "account": str(user.pk),
        "hub": "bar-pepe",
        "hub_id": HUB_ID,
        "page": "/sales/pos",
        "browser": BROWSER,
        "subject": "The printer stops",
        "description": "I sell a ticket and nothing prints.",
        **changes,
    }


def report(client, body: dict | None = None, *, raw: bytes | None = None, timestamp=None, secret=SECRET, headers=None):
    data = raw if raw is not None else json.dumps(body).encode()
    timestamp = int(time.time()) if timestamp is None else timestamp
    signed = headers if headers is not None else signed_headers("POST", URL, data, timestamp, secret)
    return client.post(URL, data, content_type="application/json", headers=signed)


class TestSent:
    def test_a_signed_report_reaches_support_with_the_account_the_business_and_where_it_came_from(self, client, member):
        response = report(client, payload(member))

        assert response.status_code == 200
        assert response.json() == {"reply_to": "ana@example.com"}
        assert "no-store" in response["Cache-Control"]
        [sent] = mail.outbox
        assert sent.to == ["support@example.com"]
        assert sent.reply_to == ["ana@example.com"]
        assert sent.subject == "[Support] The printer stops"
        body = sent.body
        assert "I sell a ticket and nothing prints." in body
        for context in (
            f"Account: ana@example.com ({member.pk})",
            "Businesses: bar-pepe (hub_manager)",
            f"Business: bar-pepe ({HUB_ID})",
            "From: Hub",
            "Page: /sales/pos",
            f"Browser: {BROWSER}",
        ):
            assert context in body

    def test_the_panels_report_says_where_it_came_from_too(self, client, ana):
        client.force_login(ana)

        api_post(client, "/api/accounts/support/report", {"subject": "S", "description": "D"})

        assert "From: Panel" in mail.outbox[0].body
        assert "Business:" not in mail.outbox[0].body

    def test_a_subject_with_line_breaks_stays_one_line(self, client, member):
        report(client, payload(member, subject="Printer\r\nBcc: victim@example.com"))

        assert mail.outbox[0].subject == "[Support] Printer Bcc: victim@example.com"
        assert mail.outbox[0].bcc == []

    def test_the_text_is_never_logged(self, client, member, caplog):
        caplog.set_level("INFO")

        report(client, payload(member, description="My card is 4242 4242 4242 4242"))

        assert "4242" not in caplog.text
        assert "accounts.support_report_sent" in caplog.text

    def test_it_needs_no_csrf_token(self, member):
        from django.test import Client

        response = report(Client(enforce_csrf_checks=True), payload(member))

        assert response.status_code == 200
        assert len(mail.outbox) == 1


class TestNotTheHub:
    def test_without_a_valid_signature_it_is_a_401_and_nothing_is_mailed(self, client, member):
        data = json.dumps(payload(member)).encode()
        now = int(time.time())
        for headers in (
            {},
            {"X-Erplora-Timestamp": str(now), "X-Erplora-Signature": sign(data, now, "another-secret")},
            signed_headers("POST", URL, data, now - 3600, SECRET),
        ):
            response = report(client, raw=data, headers=headers)
            assert response.status_code == 401, headers
            assert response.json()["error"]["code"] == "unauthorized"
        assert mail.outbox == []

    def test_only_post(self, client):
        response = client.get(URL)

        assert response.status_code == 405
        assert response["Allow"] == "POST"


class TestRefused:
    def test_a_body_that_is_no_report_is_a_400(self, client, member):
        for raw in (b"not json", json.dumps(["a"]).encode(), json.dumps({**payload(member), "account": 7}).encode()):
            response = report(client, raw=raw)
            assert response.status_code == 400, raw
            assert response.json()["error"]["code"] == "invalid_request"
        assert mail.outbox == []

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"subject": "   "}, "subject"),
            ({"description": "  "}, "description"),
            ({"subject": "x" * 151}, "subject"),
            ({"description": "x" * 5001}, "description"),
        ],
    )
    def test_what_is_missing_or_too_long_is_a_422_on_its_field(self, client, member, changes, field):
        response = report(client, payload(member, **changes))

        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert mail.outbox == []

    @pytest.mark.parametrize("account", ["019a0000-0000-7000-8000-000000000000", "not-an-id", ""])
    def test_an_account_that_does_not_exist_is_refused_without_a_mail(self, client, member, account):
        response = report(client, payload(member, account=account))

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "accounts.unknown_account"
        assert mail.outbox == []

    def test_an_account_of_another_business_is_refused_without_a_mail(self, client, member):
        olga = get_user_model().objects.create_user(email="olga@example.com", password=None)
        HubMembership.objects.create(user=olga, hub_slug="someone-else", role=HubMembership.Role.OWNER)

        response = report(client, payload(olga))

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "accounts.not_a_member"
        assert mail.outbox == []

    def test_a_deactivated_account_is_refused_without_a_mail(self, client, member):
        member.is_active = False
        member.save(update_fields=["is_active"])

        assert report(client, payload(member)).status_code == 404
        assert mail.outbox == []

    @override_settings(SUPPORT_REPORT_RATELIMIT="2/h")
    def test_the_limit_is_the_panels_one_per_account(self, client, member):
        client.force_login(member)
        assert api_post(client, "/api/accounts/support/report", {"subject": "S", "description": "D"}).status_code == 200
        assert report(client, payload(member)).status_code == 200

        refused = report(client, payload(member))

        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "accounts.too_many_attempts"
        assert len(mail.outbox) == 2

    def test_a_mail_that_cannot_leave_is_a_503_with_the_address_to_write_to(self, client, member, monkeypatch, caplog):
        def fail(*args, **kwargs):
            raise ConnectionError("SES is down")

        monkeypatch.setattr("django.core.mail.message.EmailMessage.send", fail)

        response = report(client, payload(member))

        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "accounts.report_not_sent"
        assert "support@example.com" in error["message"]
        assert "accounts.mail_failed kind=support_report" in caplog.text
