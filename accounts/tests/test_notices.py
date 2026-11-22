"""Account → Preferences → «Mail notices» (ACCOUNTS-F23).

Each switch governs mails the SaaS really sends, and only those: «Business notices» (``hub_alerts``) is the mail
that a business is ready to open (``hubs.emails.send_ready``). What keeps the account safe or its businesses
running has no switch, as GitHub's and Stripe's «you will always get important account mails»: the sign-in codes
and security notices, ERPlora's invoices and failed payments, a deleted business and its recovery date, and
anything that asks the person to act (connecting WhatsApp again). There is no «ERPlora news» switch: ERPlora sends
no such mail, and a switch that governs nothing would mislead the person.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.core import mail

from accounts.models import UserPreferences
from accounts.queries import account_preferences
from accounts.tests.conftest import api_post
from hubs.services import deletion, hub_callbacks
from hubs.schemas.businesses import BusinessDeleteIn
from hubs.schemas.hub_callbacks import MarkReadyIn
from hubs.tests.conftest import create_business, ctx_for, plans  # noqa: F401 - the plans fixture

pytestmark = pytest.mark.django_db

PREFERENCES = "/api/accounts/preferences"


def _business_notices_off(user) -> None:
    UserPreferences.objects.create(user=user, hub_alerts=False)


def _mark_ready(business) -> None:
    hub_callbacks.business_mark_ready(hub_callbacks.system_ctx_for(business.id), MarkReadyIn(id=business.id))


class TestBusinessNotices:
    def test_an_account_that_never_chose_gets_them(self, ana):
        assert account_preferences.receives_business_notices(ana) is True

    def test_the_ready_mail_reaches_an_owner_who_keeps_them(self, ana, plans, django_capture_on_commit_callbacks):  # noqa: F811
        business = create_business(ana, name="Panadería López")
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            _mark_ready(business)

        assert [(message.to, message.subject) for message in mail.outbox] == [
            (["ana@example.com"], "Panadería López ya está listo")
        ]

    def test_an_owner_who_turned_them_off_gets_no_ready_mail_and_the_business_still_opens(
        self, ana, plans, django_capture_on_commit_callbacks  # noqa: F811
    ):
        business = create_business(ana, name="Panadería López")
        _business_notices_off(ana)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            _mark_ready(business)

        assert mail.outbox == []
        business.refresh_from_db()
        assert business.status == "active"

    def test_turning_them_back_on_brings_the_mail_back(self, ana, plans, django_capture_on_commit_callbacks):  # noqa: F811
        business = create_business(ana, name="Panadería López")
        _business_notices_off(ana)
        UserPreferences.objects.filter(user=ana).update(hub_alerts=True)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            _mark_ready(business)

        assert len(mail.outbox) == 1


class TestWhatNoSwitchStops:
    def test_a_deleted_business_is_still_told_with_its_recovery_date(self, ana, plans, django_capture_on_commit_callbacks):  # noqa: F811
        business = create_business(ana, name="Panadería López")
        _business_notices_off(ana)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            deletion.business_delete(ctx_for(ana), BusinessDeleteIn(id=business.id, confirm_name="Panadería López"))

        assert [message.subject for message in mail.outbox] == ["Panadería López se ha eliminado"]

    def test_a_failed_payment_is_still_told(self, ana, plans):  # noqa: F811
        from billing import emails as billing_emails
        from billing.models import PaymentFailure

        business = create_business(ana, name="Panadería López")
        _business_notices_off(ana)
        mail.outbox.clear()

        failure = PaymentFailure(
            reason=PaymentFailure.Reason.PAYMENT_FAILED, invoice_created_at=datetime(2026, 10, 25, tzinfo=UTC)
        )
        billing_emails.send_payment_failed(business, failure, to=ana.email, language="es", amount=Decimal("36.29"))

        assert [message.to for message in mail.outbox] == [["ana@example.com"]]

    def test_a_security_mail_is_still_sent(self, signed_in, ana, django_capture_on_commit_callbacks):
        _business_notices_off(ana)
        mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            response = api_post(signed_in, "/api/accounts/api-keys", {"name": "Contabilidad", "scopes": ["hubs.read"]})

        assert response.status_code == 201
        assert [message.to for message in mail.outbox] == [["ana@example.com"]]


class TestNoSwitchForMailsErploraNeverSends:
    def test_the_preferences_carry_no_news_switch(self, ana):
        assert "marketing_emails" not in account_preferences.preferences_of(ana)

    def test_sending_one_is_refused_on_its_field(self, client, ana):
        client.force_login(ana)

        response = api_post(client, PREFERENCES, {"marketing_emails": True})

        assert response.status_code == 422
        assert "marketing_emails" in response.json()["error"]["fields"]
