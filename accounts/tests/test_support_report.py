"""ACCOUNTS-F38 · «Report a problem»: ``accounts.support.report`` mails the support mailbox (ACCOUNTS-G117, G01).

Ported from the old SaaS's «Ayuda y soporte › Reportar un problema» (SAAS_DASHBOARD-F219, ``/api/v1/admin/report-issue/``
gone, PLAN-SAAS §6) as PLAN-SAAS §1.1 simplifies it: a form that mails the support mailbox with the account, its
businesses, the browser and where it came from, limited like the contact form, with no issue opened anywhere and
nothing kept. What the old one left behind (its state said so): the account's businesses now go with it, and the mail
carries «Reply-To» the account, so support answers with «Reply».
"""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings

from accounts.models import HubMembership
from accounts.tests.conftest import HOST, api_post

pytestmark = pytest.mark.django_db

REPORT = "/api/accounts/support/report"
BROWSER = "Mozilla/5.0 (Macintosh) Firefox/140.0"


@pytest.fixture
def olga(db):
    return get_user_model().objects.create_user(email="olga@example.com", password=None, first_name="Olga")


def _report(client, **body):
    payload = {"subject": "The printer stops", "description": "I sell a ticket and nothing prints.", **body}
    return api_post(client, REPORT, payload, HTTP_USER_AGENT=BROWSER)


class TestSending:
    def test_the_report_reaches_support_with_the_account_and_where_it_came_from(self, client, ana, settings):
        settings.SUPPORT_EMAIL = "support@example.com"
        HubMembership.objects.create(user=ana, hub_slug="bar-pepe", role=HubMembership.Role.ADMIN)
        client.force_login(ana)

        response = _report(client, page="/dashboard/businesses")

        assert response.status_code == 200
        assert response.json() == {"reply_to": "ana@example.com"}
        [sent] = mail.outbox
        assert sent.to == ["support@example.com"]
        assert sent.reply_to == ["ana@example.com"]
        assert sent.subject == "[Support] The printer stops"
        assert "I sell a ticket and nothing prints." in sent.body
        for context in ("ana@example.com", str(ana.pk), "bar-pepe (hub_admin)", "/dashboard/businesses", BROWSER):
            assert context in sent.body

    def test_without_a_page_or_a_business_it_says_none(self, client, ana):
        client.force_login(ana)

        assert _report(client).status_code == 200

        body = mail.outbox[0].body
        assert "Businesses: none" in body
        assert "Page: unknown" in body

    def test_only_the_callers_businesses_go_with_it(self, client, ana, olga):
        HubMembership.objects.create(user=olga, hub_slug="someone-else", role=HubMembership.Role.OWNER)
        client.force_login(ana)

        _report(client)

        assert "someone-else" not in mail.outbox[0].body
        assert olga.email not in mail.outbox[0].body

    def test_a_subject_with_line_breaks_stays_one_line(self, client, ana):
        client.force_login(ana)

        _report(client, subject="Printer\r\nBcc: victim@example.com")

        assert mail.outbox[0].subject == "[Support] Printer Bcc: victim@example.com"
        assert mail.outbox[0].bcc == []

    def test_nothing_is_kept_and_the_text_is_never_logged(self, client, ana, caplog):
        client.force_login(ana)
        caplog.set_level("INFO")

        _report(client, description="My card is 4242 4242 4242 4242")

        assert "4242" not in caplog.text


class TestRefused:
    def test_an_anonymous_visitor_gets_the_401_and_nothing_is_sent(self, client):
        assert _report(client).status_code == 401
        assert mail.outbox == []

    @pytest.mark.parametrize(
        ("body", "field", "message"),
        [
            ({"subject": "   "}, "subject", "Add a subject."),
            ({"description": "  "}, "description", "Describe the problem, please."),
            ({"subject": "x" * 151}, "subject", None),
            ({"description": "x" * 5001}, "description", None),
        ],
    )
    def test_what_is_missing_or_too_long_is_a_422_on_its_field(self, client, ana, english, body, field, message):
        client.force_login(ana)

        response = _report(client, **body)

        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        if message:
            assert response.json()["error"]["fields"][field] == message
        assert mail.outbox == []

    def test_the_messages_speak_the_accounts_language(self, client, ana):
        ana.language = "es"
        ana.save()
        client.force_login(ana)

        response = _report(client, subject=" ", description=" ")

        assert response.json()["error"]["fields"] == {
            "subject": "Añade un asunto.",
            "description": "Describe el problema, por favor.",
        }

    @override_settings(SUPPORT_REPORT_RATELIMIT="2/h")
    def test_more_reports_than_the_limit_are_refused_for_that_account_only(self, client, ana, olga):
        from django.core.cache import cache

        cache.clear()
        client.force_login(ana)
        assert [_report(client).status_code for _ in range(2)] == [200, 200]

        refused = _report(client)

        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "accounts.too_many_attempts"
        assert len(mail.outbox) == 2
        client.force_login(olga)
        assert _report(client).status_code == 200

    def test_a_mail_that_cannot_leave_is_said_with_the_address_to_write_to(self, client, ana, settings, monkeypatch, caplog):
        settings.SUPPORT_EMAIL = "support@example.com"

        def fail(*args, **kwargs):
            raise ConnectionError("SES is down")

        monkeypatch.setattr("django.core.mail.message.EmailMessage.send", fail)
        client.force_login(ana)

        response = _report(client)

        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "accounts.report_not_sent"
        assert "support@example.com" in error["message"]
        assert "accounts.mail_failed kind=support_report" in caplog.text

