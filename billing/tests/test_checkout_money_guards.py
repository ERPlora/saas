"""When no money moves on a purchase: Stripe missing or silent, a live key without the route that sends the invoice
or without the year's OSS total, a live secret key and a business with an unpaid invoice; and a Stripe customer that
is found again rather than created twice.
"""

import pytest
from django.utils import timezone

from billing.models import FiscalPolicy
from billing.services import payment_gates
from billing.tests.checkout_calls import refused, session_params, start
from billing.tests.conftest import pay
from billing.tests.stripe_double import connection_error

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


# --- Guards of money ---------------------------------------------------------------------------------


class TestNoMoneyMovesWhen:
    def test_stripe_is_not_configured(self, shop, owner, settings):
        settings.STRIPE_SECRET_KEY = ""

        error = refused(
            "billing.payments_unavailable", lambda: start(owner, shop, plan="starter")
        )

        assert error.status == 503

    def test_stripe_does_not_answer(self, shop, owner, stripe_double):
        stripe_double.answer("checkout.sessions.create", connection_error())

        error = refused(
            "billing.stripe_unavailable", lambda: start(owner, shop, plan="starter")
        )

        assert error.status == 503

    def live_and_oss_known(self, settings):
        from django.core.cache import cache

        cache.clear()  # the platform hub's last health answer
        settings.STRIPE_SECRET_KEY = "rk_live_double"
        settings.STRIPE_PUBLISHABLE_KEY = "pk_live_double"
        settings.STRIPE_EXPECTED_MODE = "live"
        FiscalPolicy.objects.update(oss_carried_year=timezone.localdate().year)

    def test_a_live_key_is_held_while_invoicing_is_not_switched_on(self, shop, owner, settings, stripe_double,
                                                                   hub_double):
        """In production nothing is charged without a route that sends the invoice. The model
        existing is not that route: ``PLATFORM_INVOICING_ENABLED`` says the platform hub is wired,
        and nobody asks the Hub while it is off."""
        self.live_and_oss_known(settings)
        settings.PLATFORM_INVOICING_ENABLED = False

        error = refused("billing.invoicing_unavailable", lambda: start(owner, shop, plan="starter"))

        assert error.status == 409
        assert stripe_double.calls == []
        assert hub_double.calls == []

    def test_switched_on_with_the_platform_hub_down_it_is_held(self, shop, owner, settings, stripe_double,
                                                             hub_double):
        self.live_and_oss_known(settings)
        settings.PLATFORM_INVOICING_ENABLED = True
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 503, {})

        refused("billing.invoicing_unavailable", lambda: start(owner, shop, plan="starter"))

        assert stripe_double.calls == []

    def test_switched_on_with_the_platform_hub_answering_it_sells(self, shop, owner, settings, stripe_double,
                                                                hub_double):
        self.live_and_oss_known(settings)
        settings.PLATFORM_INVOICING_ENABLED = True
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 200, {"status": "ok"})

        assert start(owner, shop, plan="starter")["flow"] == "checkout"
        assert [call.path for call in hub_double.calls_to("GET")] == ["/internal/platform/invoices/health"]

    def test_the_probe_is_kept_a_while(self, shop, owner, settings, stripe_double, hub_double):
        from django.core.cache import cache

        cache.clear()
        self.live_and_oss_known(settings)
        settings.PLATFORM_INVOICING_ENABLED = True
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 200, {"status": "ok"})

        payment_gates.require_payments()
        payment_gates.require_payments()

        assert len(hub_double.calls_to("GET", "/health")) == 1

    def test_a_failed_probe_is_asked_again_next_time(self, settings, hub_double):
        from django.core.cache import cache

        cache.clear()
        settings.PLATFORM_INVOICING_ENABLED = True
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 503, {})
        assert payment_gates.invoicing_available() is False
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 200, {"status": "ok"})

        assert payment_gates.invoicing_available() is True

    def test_a_test_key_is_never_held_for_invoicing(self, shop, owner, settings, stripe_double, offline_hub):
        settings.PLATFORM_INVOICING_ENABLED = False

        assert start(owner, shop, plan="starter")["flow"] == "checkout"

    def test_with_a_live_key_the_oss_total_must_still_be_known(self, shop, owner, settings, stripe_double,
                                                               hub_double):
        settings.STRIPE_SECRET_KEY = "rk_live_double"
        settings.STRIPE_PUBLISHABLE_KEY = "pk_live_double"
        settings.STRIPE_EXPECTED_MODE = "live"
        settings.PLATFORM_INVOICING_ENABLED = True
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 200, {"status": "ok"})
        FiscalPolicy.objects.update(oss_carried_year=None)

        refused("billing.oss_total_unknown", lambda: start(owner, shop, plan="starter"))

        assert stripe_double.calls == []

    def test_a_live_secret_key_is_never_used(self, shop, owner, settings, stripe_double):
        """Production holds a RESTRICTED live key (``rk_live_``), never the account's secret."""
        settings.STRIPE_SECRET_KEY = "sk_live_double"
        settings.STRIPE_PUBLISHABLE_KEY = "pk_live_double"
        settings.STRIPE_EXPECTED_MODE = "live"

        error = refused("billing.payments_unavailable", lambda: start(owner, shop, plan="starter"))

        assert error.status == 503
        assert stripe_double.calls == []

    def test_a_customer_stripe_already_has_is_found_not_created_twice(self, shop, owner, stripe_double):
        """A checkout that failed after the customer was created rolls back its id: the next one finds it by
        the payer it belongs to."""
        stripe_double.answer(
            "customers.search",
            {"object": "search_result", "data": [{"id": "cus_orphan", "object": "customer"}], "has_more": False},
        )

        start(owner, shop, plan="starter")

        assert stripe_double.last("customers.search").params == {
            "query": f"metadata['billing_profile_id']:'{shop.billing_profile_id}'"
        }
        assert stripe_double.calls_to("customers.create") == []
        assert session_params(stripe_double)["customer"] == "cus_orphan"

    def test_a_customer_created_again_with_other_details_is_not_refused(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")
        from hubs.models import BillingProfile

        BillingProfile.objects.filter(pk=shop.billing_profile_id).update(stripe_customer_id="", billing_city="Getafe")

        start(owner, shop, plan="standard")

        keys = [call.options["idempotency_key"] for call in stripe_double.calls_to("customers.create")]
        assert len(keys) == 2 and keys[0] != keys[1]

    def test_a_test_key_moves_no_real_money_and_is_not_held(
        self, shop, owner, stripe_double
    ):
        FiscalPolicy.objects.update(oss_carried_year=None)

        assert start(owner, shop, plan="starter")["flow"] == "checkout"

    @pytest.mark.parametrize("status", ["past_due", "unpaid"])
    def test_an_invoice_is_unpaid(self, shop, owner, inventory, stripe_double, status):
        paid = pay(shop, status=status)

        refused(
            "billing.invoice_unpaid", lambda: start(owner, paid, module="inventory")
        )

        assert stripe_double.calls == []
