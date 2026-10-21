"""The payer of an account that deleted itself (ACCOUNTS-F27; GDPR art. 17, with its 17(3)(b) exception).

The invoices ERPlora issued keep their own copy of the payer (Commercial Code art. 30, 6 years; General Tax
Law art. 66, 4): that copy is what the law asks to keep. The payer record itself (``hubs.BillingProfile``:
legal name, tax ID, address, billing email) and its Stripe customer are not: they go with the account, as
Stripe advises for a deletion request (docs.stripe.com/privacy/deletion-requests).

Only what can still be charged holds them, because the invoice issued at that payment must carry the payer:
a subscription Stripe still bills (a deleted business stops paying at the next ``sweep_unpaid``) or an
invoice not paid yet. Then the payer stays until it is paid or cancelled, and at most ``PAYER_RETENTION``
after the account left (``forget_after``, the purge date): on that day what is still unpaid is voided in
Stripe and the payer goes. ``sweep_unpaid`` (hourly) does what the deletion itself could not.
"""

import time
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from accounts.tests.conftest import AUTHENTICATION_RECORDS, HOST
from billing.tests.conftest import pay
from billing.tests.stripe_double import connection_error, event, invalid_request, invoice, listing, signed, subscription
from hubs.models import BillingProfile, Hub, HubMember

pytestmark = pytest.mark.django_db

DELETE_ACCOUNT = "/api/accounts/profile/delete"
TAX_ID = "B12345678"


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    stripe_double.answer("invoice_payments.list", listing([]))
    stripe_double.answer("subscriptions.cancel", subscription(status="canceled"))
    stripe_double.answer("customers.delete", {"id": "cus_1", "object": "customer", "deleted": True})
    return stripe_double


@pytest.fixture
def running(shop):
    """The business of ``owner`` paying Starter monthly (``sub_1``), its payer with a tax ID and a customer."""
    BillingProfile.objects.filter(pk=shop.billing_profile_id).update(
        tax_id=TAX_ID, billing_email="cuentas@panaderia.example", stripe_customer_id="cus_1"
    )
    paid = pay(shop)
    Hub.objects.filter(pk=paid.pk).update(status=Hub.Status.ACTIVE, ready_at=timezone.now(), pending_hub_call="")
    return Hub.objects.select_related("billing_profile").get(pk=paid.pk)


def deliver(payload):
    body, header = signed(payload)
    response = Client().post(
        "/webhooks/stripe/", body, content_type="application/json", HTTP_STRIPE_SIGNATURE=header, HTTP_HOST=HOST
    )
    assert response.status_code == 200, response.content
    return response.json()["status"]


def unpaid(stripe_double, invoice_id="in_2"):
    """A renewal that failed: listed «Not collected», without a number (``invoice.payment_failed``)."""
    from billing.tests.stripe_double import invoice_payment, payment_intent

    stripe_double.answer("subscriptions.retrieve", subscription(status="past_due"))
    stripe_double.answer("invoice_payments.list", listing([invoice_payment("pi_1", invoice_id=invoice_id)]))
    stripe_double.answer("payment_intents.retrieve", payment_intent("pi_1"))
    assert deliver(event("invoice.payment_failed", invoice(invoice_id))) == "processed"
    stripe_double.answer("invoice_payments.list", listing([]))


def late_payment(hub, invoice_id):
    """The unpaid invoice, paid by its link once the subscription has ended: it carries the ``hub_id`` the
    checkout put on the subscription (``subscription_data.metadata``), which is how Stripe sends it."""
    paid = invoice(invoice_id, status="paid")
    paid["parent"]["subscription_details"]["metadata"] = {"hub_id": str(hub.id)}
    return paid


def delete_business(hub):
    from hubs import services as hub_services
    from hubs.schemas import BusinessDeleteIn
    from hubs.tests.conftest import ctx_for as hub_ctx

    owner = HubMember.objects.get(hub=hub, role=HubMember.Role.OWNER).user
    hub_services.business_delete(hub_ctx(owner), BusinessDeleteIn(id=hub.id, confirm_name=hub.name))


def delete_account(user, capture):
    """«Delete account» of Account › Profile, signed in a moment ago, with what runs after its COMMIT."""
    client = Client()
    client.force_login(user)
    session = client.session
    session[AUTHENTICATION_RECORDS] = [{"method": "password", "at": time.time(), "email": user.email}]
    session.save()
    with capture(execute=True):
        response = client.post(DELETE_ACCOUNT, {}, content_type="application/json", HTTP_HOST=HOST)
    assert response.status_code == 200, response.content


def sweep():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("sweep_unpaid", stdout=out)
    return out.getvalue()


def ended(business, stripe_double):
    """Deleted, and its Stripe subscription already ended by ``sweep_unpaid``: nothing more is billed (and Stripe
    answers it ``canceled`` from then on)."""
    delete_business(business)
    sweep()
    stripe_double.answer("subscriptions.retrieve", subscription(status="canceled"))


def kept(profile_id) -> bool:
    return BillingProfile.objects.filter(pk=profile_id).exists()


class TestNothingCanStillBeCharged:
    def test_the_payer_goes_with_the_account_and_its_stripe_customer_too(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        profile_id = running.billing_profile_id
        assert deliver(event("invoice.paid", invoice("in_1", status="paid"))) == "processed"
        ended(running, stripe_double)

        delete_account(owner, django_capture_on_commit_callbacks)

        assert not kept(profile_id)
        assert [call.args for call in stripe_double.calls_to("customers.delete")] == [("cus_1",)]
        assert Hub.objects.get(pk=running.pk).billing_profile_id is None

    def test_the_issued_invoice_keeps_its_own_copy_of_the_payer(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        from billing.models import Invoice

        deliver(event("invoice.paid", invoice("in_1", status="paid")))
        ended(running, stripe_double)

        delete_account(owner, django_capture_on_commit_callbacks)

        issued = Invoice.objects.get(stripe_invoice_id="in_1")
        assert (issued.payer_name, issued.payer_tax_id, issued.payer_address) == (
            "Panadería López SL",
            TAX_ID,
            "Calle Mayor 1",
        )
        assert (issued.billing_profile_id, issued.payer_account_id) == (None, None)

    def test_a_payer_that_never_paid_goes_without_asking_stripe(
        self, shop, owner, stripe_double, settings, django_capture_on_commit_callbacks
    ):
        profile_id = shop.billing_profile_id
        delete_business(shop)
        settings.STRIPE_SECRET_KEY = ""

        delete_account(owner, django_capture_on_commit_callbacks)

        assert not kept(profile_id)
        assert stripe_double.calls_to("customers.delete") == []

    def test_a_customer_stripe_no_longer_has_counts_as_gone(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        profile_id = running.billing_profile_id
        ended(running, stripe_double)
        stripe_double.answer("customers.delete", invalid_request(message="No such customer: 'cus_1'"))

        delete_account(owner, django_capture_on_commit_callbacks)

        assert not kept(profile_id)


class TestWhatCanStillBeChargedHoldsIt:
    def test_a_subscription_stripe_still_bills_holds_it_until_the_sweep_ends_it(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        profile_id = running.billing_profile_id
        delete_business(running)

        delete_account(owner, django_capture_on_commit_callbacks)

        assert kept(profile_id)
        assert stripe_double.calls_to("customers.delete") == []

        output = sweep()

        assert not kept(profile_id)
        assert [call.args for call in stripe_double.calls_to("customers.delete")] == [("cus_1",)]
        assert "payers_forgotten=1" in output

    def test_an_unpaid_invoice_holds_it_until_it_is_paid_and_issued_with_it(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        from billing.models import Invoice

        profile_id = running.billing_profile_id
        unpaid(stripe_double)
        ended(running, stripe_double)

        delete_account(owner, django_capture_on_commit_callbacks)

        assert kept(profile_id)
        held = BillingProfile.objects.get(pk=profile_id)
        assert held.owner_id is None
        assert timedelta(days=89) < held.forget_after - timezone.now() <= timedelta(days=90)
        sweep()
        assert kept(profile_id)

        assert deliver(event("invoice.paid", late_payment(running, "in_2"))) == "processed"
        issued = Invoice.objects.get(stripe_invoice_id="in_2")
        assert (issued.payment_status, issued.payer_tax_id) == (Invoice.PaymentStatus.PAID, TAX_ID)

        sweep()

        assert not kept(profile_id)
        assert [call.args for call in stripe_double.calls_to("customers.delete")] == [("cus_1",)]

    def test_on_its_purge_date_what_is_still_unpaid_is_voided_and_the_payer_goes(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        from billing.models import Invoice

        profile_id = running.billing_profile_id
        unpaid(stripe_double)
        ended(running, stripe_double)
        delete_account(owner, django_capture_on_commit_callbacks)
        BillingProfile.objects.filter(pk=profile_id).update(forget_after=timezone.now() - timedelta(seconds=1))
        stripe_double.answer("invoices.void_invoice", invoice("in_2", status="void"))

        sweep()

        assert [call.args for call in stripe_double.calls_to("invoices.void_invoice")] == [("in_2",)]
        assert Invoice.objects.get(stripe_invoice_id="in_2").payment_status == Invoice.PaymentStatus.VOID
        assert not kept(profile_id)
        assert [call.args for call in stripe_double.calls_to("customers.delete")] == [("cus_1",)]

    def test_before_its_purge_date_nothing_unpaid_is_voided(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        profile_id = running.billing_profile_id
        unpaid(stripe_double)
        ended(running, stripe_double)
        delete_account(owner, django_capture_on_commit_callbacks)

        sweep()

        assert stripe_double.calls_to("invoices.void_invoice") == []
        assert kept(profile_id)


class TestAFailureIsRetried:
    def test_stripe_failing_keeps_the_payer_and_the_sweep_fails_until_it_goes(
        self, running, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        from django.core.management import CommandError

        profile_id = running.billing_profile_id
        ended(running, stripe_double)
        stripe_double.answer("customers.delete", connection_error())

        delete_account(owner, django_capture_on_commit_callbacks)

        assert kept(profile_id)
        with pytest.raises(CommandError, match="errors=1"):
            sweep()
        assert kept(profile_id)

        stripe_double.answer("customers.delete", {"id": "cus_1", "object": "customer", "deleted": True})
        sweep()

        assert not kept(profile_id)


class TestOnlyTheDepartedPayer:
    def test_the_payers_of_other_accounts_are_never_touched(
        self, running, owner, make_user, stripe_double, django_capture_on_commit_callbacks
    ):
        from hubs.tests.conftest import create_business

        other = create_business(make_user("bea@example.com"), name="Bodega de Bea")
        BillingProfile.objects.filter(pk=other.billing_profile_id).update(tax_id="B87654321", stripe_customer_id="cus_bea")
        ended(running, stripe_double)

        delete_account(owner, django_capture_on_commit_callbacks)
        output = sweep()

        assert "payers_forgotten=0" in output
        theirs = BillingProfile.objects.get(pk=other.billing_profile_id)
        assert (theirs.owner.email, theirs.tax_id, theirs.forget_after) == ("bea@example.com", "B87654321", None)
        assert [call.args for call in stripe_double.calls_to("customers.delete")] == [("cus_1",)]
