"""The payer's Stripe customer takes the billing details the owner saves (BILLING-F01; registry BILLING-G26).

Ported from ERPlora/saas ``apps/dashboard/organizations`` (``update_billing`` → ``OrganizationStripeService
.sync_billing_info``; fi:saas/orgs-users#informacion-de-facturacion-de-la-organizacion-ver-editar, origin/develop):
saving the billing card updated the Stripe Customer when it existed. Without it the customer keeps the old name,
address and e-mail until the next checkout, so what Stripe itself sends (the page to confirm a renewal the bank
wants authenticated, its receipts) and what the Customer Portal shows go on with the old ones.

Adapted: ERPlora's invoices take the details from erplora.com, never from Stripe (BILLING-F25); the push only keeps
the customer in step, after the COMMIT, and a payer Stripe never saw gets no customer for it (the first checkout
creates it, BILLING-F07/F08). The same parameters as the checkout's ``ensure_customer``.
"""

import logging

import pytest

from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import connection_error, item, subscription
from billing.tests.vies_double import no_network

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def paying(shop, stripe_double):
    """The business paying Starter, its payer already a Stripe customer (``cus_1``)."""
    paid = pay(shop)
    lines = [item("si_plan", "price_starter_month")]
    stripe_double.answer("subscriptions.retrieve", subscription(items=lines))
    stripe_double.answer("subscriptions.update", subscription(items=lines))
    return paid


def save(owner, hub, **details):
    from hubs import services as hub_services
    from hubs.schemas import BillingProfileIn

    values = {
        "billing_name": "Panadería López SL",
        "billing_address": "Calle Triana 1",
        "billing_city": "Las Palmas",
        "billing_postal_code": "35001",
        "billing_country": "ES",
        "billing_email": "facturas@panaderialopez.es",
        **details,
    }
    return hub_services.billing_profile_update(ctx_for(owner), BillingProfileIn(hub_id=hub.id, **values))


class TestSavingTheBillingDetails:
    def test_the_stripe_customer_takes_them_after_the_commit(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        """BILLING-G26: name, address, e-mail and language reach the payer's customer, once committed."""
        paid = paying(shop, stripe_double)

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            save(owner, paid)
        assert stripe_double.calls_to("customers.update") == []
        for callback in callbacks:
            callback()

        sent = stripe_double.last("customers.update")
        assert sent.args[0] == "cus_1"
        assert sent.params["name"] == "Panadería López SL"
        assert sent.params["email"] == "facturas@panaderialopez.es"
        assert sent.params["address"] == {
            "line1": "Calle Triana 1",
            "city": "Las Palmas",
            "postal_code": "35001",
            "country": "ES",
        }
        assert sent.params["preferred_locales"] == ["es"]
        assert sent.params["metadata"] == {"billing_profile_id": str(paid.billing_profile_id)}

    def test_without_an_e_mail_for_the_invoices_the_owner_s_goes(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        paid = paying(shop, stripe_double)

        with django_capture_on_commit_callbacks(execute=True):
            save(owner, paid, billing_email="")

        assert stripe_double.last("customers.update").params["email"] == "owner@example.com"

    def test_a_payer_stripe_never_saw_gets_no_customer_for_it(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        """On Free, nothing paid yet: the first checkout creates the customer with these details."""
        with django_capture_on_commit_callbacks(execute=True):
            save(owner, shop)

        assert not {"customers.create", "customers.update", "customers.search"} & set(stripe_double.paths())

    def test_a_national_tax_id_travels_to_the_customer(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks
    ):
        paid = paying(shop, stripe_double)

        with no_network(), django_capture_on_commit_callbacks(execute=True):
            save(owner, paid, billing_postal_code="28001", billing_city="Madrid", tax_id="ESB27593136")

        created = stripe_double.last("customers.tax_ids.create")
        assert created.args[0] == "cus_1"
        assert created.params == {"type": "eu_vat", "value": "ESB27593136"}

    def test_stripe_failing_keeps_the_save_is_logged_and_still_retaxes(
        self, shop, owner, stripe_double, django_capture_on_commit_callbacks, caplog
    ):
        from hubs.models import BillingProfile

        paid = paying(shop, stripe_double)
        stripe_double.answer("customers.update", connection_error())

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            with django_capture_on_commit_callbacks(execute=True):
                save(owner, paid)

        assert BillingProfile.objects.get(pk=paid.billing_profile_id).billing_city == "Las Palmas"
        assert [r.hub_id for r in caplog.records if getattr(r, "event", "") == "billing.customer_push_failed"] == [
            str(paid.id)
        ]
        # The live subscription is still retaxed for the new place (BILLING-F02): read after the failed push.
        paths = stripe_double.paths()
        assert "subscriptions.retrieve" in paths[paths.index("customers.update") :]
