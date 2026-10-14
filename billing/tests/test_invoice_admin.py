"""ERPlora's invoices in the Django admin: read-only, with «Send again to the platform hub» (lot L3-C).

Ported from ERPlora/saas ``apps/dashboard/billing/tests/test_invoice_admin.py`` (origin/develop, 11 tests): the
business and the fiscal answer are visible in the list, the related rows are fetched up front, the action is
registered, and the recipient of an invoice already issued is frozen. Here every field is frozen: an invoice is
recorded from what Stripe charged and issued by the platform hub, and a record sent to the AEAT is never
modified (it is corrected with a new one, a credit note). Dropped with their reason: the AEAT environment
column and the record's CSV (both are the platform hub's now) and adding a tax id by hand to an unreported
invoice (the payer edits their billing details; the next invoice carries them).
"""

from datetime import date

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model

from billing.models import Invoice, InvoiceLine

pytestmark = pytest.mark.django_db

PLATFORM = r"^/internal/platform/invoices$"


@pytest.fixture
def staff_client(client):
    client.force_login(
        get_user_model().objects.create_superuser(
            email="root@example.com", password="x"
        )
    )
    return client


@pytest.fixture
def invoice(db):
    issued = Invoice.objects.create(
        stripe_invoice_id="in_1",
        business_name="Panadería López",
        payment_status="paid",
        series="ERP",
        sequence=1,
        number="ERP-2026-00001",
        issued_on=date(2026, 10, 1),
        net_cents=2999,
        tax_cents=630,
        total_cents=3629,
        payer_name="Panadería López SL",
        fiscal_status="issuing",
    )
    InvoiceLine.objects.create(
        invoice=issued,
        position=1,
        description="1 × Starter",
        net_cents=2999,
        tax_cents=630,
        total_cents=3629,
    )
    return issued


@pytest.fixture
def invoice_admin():
    return site._registry[Invoice]


class TestTheListing:
    def test_it_loads(self, staff_client, invoice):
        response = staff_client.get("/admin/billing/invoice/")

        assert response.status_code == 200
        assert "ERP-2026-00001" in response.content.decode()

    def test_the_business_and_the_fiscal_answer_are_visible(self, invoice_admin):
        assert {"business_name", "fiscal_status", "payment_status", "number"} <= set(
            invoice_admin.list_display
        )

    def test_related_rows_are_fetched_up_front(self, invoice_admin):
        assert {"hub", "payer_account"} <= set(invoice_admin.list_select_related)

    def test_it_is_searched_by_number_payer_and_stripe(self, invoice_admin):
        assert {"number", "payer_name", "payer_tax_id", "stripe_invoice_id"} <= set(
            invoice_admin.search_fields
        )


class TestNothingIsEditedByHand:
    def test_an_invoice_opens_read_only_with_its_lines(self, staff_client, invoice):
        response = staff_client.get(f"/admin/billing/invoice/{invoice.pk}/change/")

        body = response.content.decode()
        assert response.status_code == 200
        assert "Panadería López SL" in body and "1 × Starter" in body
        assert 'name="_save"' not in body

    def test_nobody_adds_or_deletes_one(self, staff_client, invoice):
        assert staff_client.get("/admin/billing/invoice/add/").status_code == 403
        assert (
            staff_client.post(
                f"/admin/billing/invoice/{invoice.pk}/delete/", {"post": "yes"}
            ).status_code
            == 403
        )
        assert Invoice.objects.filter(pk=invoice.pk).exists()


class TestSendAgain:
    def test_the_action_is_registered(self, invoice_admin, rf):
        request = rf.get("/admin/billing/invoice/")
        request.user = get_user_model().objects.create_superuser(
            email="root2@example.com", password="x"
        )

        assert "send_to_platform" in invoice_admin.get_actions(request)

    def test_it_posts_the_selected_invoices_and_says_how_it_went(
        self, staff_client, invoice, hub_double
    ):
        hub_double.answer(
            "POST",
            PLATFORM,
            200,
            {"status": "accepted", "qr": "https://aeat.example/qr"},
        )

        response = staff_client.post(
            "/admin/billing/invoice/",
            {"action": "send_to_platform", "_selected_action": [str(invoice.pk)]},
            follow=True,
        )

        assert [call.body["number"] for call in hub_double.calls_to("POST")] == [
            "ERP-2026-00001"
        ]
        assert Invoice.objects.get().fiscal_status == "accepted"
        assert "ERP-2026-00001" in response.content.decode()

    def test_the_hub_away_is_said_not_hidden(self, staff_client, invoice, hub_double):
        hub_double.answer("POST", PLATFORM, 503, {})

        response = staff_client.post(
            "/admin/billing/invoice/",
            {"action": "send_to_platform", "_selected_action": [str(invoice.pk)]},
            follow=True,
        )

        messages = [str(message) for message in response.context["messages"]]
        assert any("ERP-2026-00001" in message for message in messages)
        assert Invoice.objects.get().fiscal_status == "issuing"


class TestWhoMaySendAgain:
    """Review of L3-C: posting again and mailing again are writes: they need ``billing.change_invoice``; a staff
    member who only reads invoices sees no action."""

    def reader(self):
        from django.contrib.auth.models import Permission

        user = get_user_model().objects.create_user(email="reader@example.com", password="x", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="view_invoice"))
        return get_user_model().objects.get(pk=user.pk)

    def test_a_reader_has_no_action(self, invoice_admin, rf):
        request = rf.get("/admin/billing/invoice/")
        request.user = self.reader()

        assert not {"send_to_platform", "send_mail_again"} & set(invoice_admin.get_actions(request))

    def test_whoever_may_change_invoices_has_both(self, invoice_admin, rf):
        from django.contrib.auth.models import Permission

        user = self.reader()
        user.user_permissions.add(Permission.objects.get(codename="change_invoice"))
        request = rf.get("/admin/billing/invoice/")
        request.user = get_user_model().objects.get(pk=user.pk)

        assert {"send_to_platform", "send_mail_again"} <= set(invoice_admin.get_actions(request))


class TestSendTheMailAgain:
    def test_it_sends_the_mail_of_an_issued_invoice_even_if_sent_before(self, staff_client, invoice):
        from django.core import mail
        from django.utils import timezone

        Invoice.objects.filter(pk=invoice.pk).update(
            fiscal_status="accepted", payer_email="pagos@example.com", emailed_at=timezone.now()
        )

        response = staff_client.post(
            "/admin/billing/invoice/",
            {"action": "send_mail_again", "_selected_action": [str(invoice.pk)]},
            follow=True,
        )

        assert [message.to for message in mail.outbox] == [["pagos@example.com"]]
        assert "ERP-2026-00001" in response.content.decode()

    def test_one_not_issued_has_no_mail_yet(self, staff_client, invoice):
        from django.core import mail

        Invoice.objects.filter(pk=invoice.pk).update(payer_email="pagos@example.com")

        staff_client.post(
            "/admin/billing/invoice/",
            {"action": "send_mail_again", "_selected_action": [str(invoice.pk)]},
            follow=True,
        )

        assert mail.outbox == []

