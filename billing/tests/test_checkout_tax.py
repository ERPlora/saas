"""Buying from a free business: where the payer is decides the tax before anything is charged, and over the
simplified invoice limit the invoice must name the buyer (``billing.checkout.start``).
"""

import pytest

from billing.models import CheckoutAttempt, TaxRule
from billing.tests.checkout_calls import payer, refused, session_params, start

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


# --- Where the payer is, and the tax -----------------------------------------------------------------


class TestWhereThePayerIsFirst:
    @pytest.mark.parametrize(
        "country, postal_code",
        [("", ""), ("ES", ""), ("", "28001"), ("ES", "3500")],
    )
    def test_without_a_whole_location_nothing_is_sold(
        self, shop, owner, stripe_double, country, postal_code
    ):
        payer(shop, billing_country=country, billing_postal_code=postal_code)

        refused(
            "billing.billing_location_required",
            lambda: start(owner, shop, plan="starter"),
        )

        assert stripe_double.calls == []
        assert CheckoutAttempt.objects.count() == 0

    def test_a_canary_buyer_pays_the_net_and_not_a_cent_more(
        self, shop, owner, stripe_double
    ):
        payer(shop, billing_postal_code="35001", billing_city="Las Palmas", tax_id="ESB27593136")

        start(owner, shop, plan="starter")

        assert session_params(stripe_double)["line_items"][0]["tax_rates"] == []
        assert stripe_double.calls_to("tax_rates.create") == []

    def test_the_mainland_pays_21_percent_on_top(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")

        created = stripe_double.last("tax_rates.create").params
        assert (created["percentage"], created["inclusive"], created["country"]) == (
            21.0,
            False,
            "ES",
        )

    @pytest.mark.usefixtures("every_country_sold")
    def test_a_consumer_elsewhere_in_the_eu_pays_spanish_vat_under_the_oss_threshold(
        self, shop, owner, stripe_double
    ):
        payer(shop, billing_country="DE", billing_postal_code="10115")

        start(owner, shop, plan="starter")

        created = stripe_double.last("tax_rates.create").params
        assert (created["percentage"], created["country"]) == (21.0, "ES")

    def test_a_territory_without_a_rule_is_refused(self, shop, owner, stripe_double):
        TaxRule.objects.filter(country_code="ES", region_code="IC").delete()
        payer(shop, billing_postal_code="35001", tax_id="ESB27593136")

        refused(
            "billing.tax_engine_missing", lambda: start(owner, shop, plan="starter")
        )

        assert stripe_double.calls_to("checkout.sessions.create") == []

    @pytest.mark.usefixtures("every_country_sold")
    def test_a_consumer_in_the_uk_is_not_sold_to(self, shop, owner, stripe_double):
        payer(shop, billing_country="GB", billing_postal_code="SW1A 1AA")

        refused(
            "billing.uk_business_required", lambda: start(owner, shop, plan="starter")
        )


class TestOverTheSimplifiedInvoiceLimit:
    def test_an_annual_plan_over_400_euros_needs_the_tax_id(
        self, shop, owner, stripe_double
    ):
        error = refused(
            "billing.tax_id_required",
            lambda: start(owner, shop, plan="standard", interval="year"),
        )

        assert error.status == 409
        assert stripe_double.calls == []

    def test_the_same_plan_monthly_fits_a_simplified_invoice(
        self, shop, owner, stripe_double
    ):
        start(owner, shop, plan="standard")

        assert (
            session_params(stripe_double)["line_items"][0]["price"]
            == "price_standard_month"
        )

    def test_with_the_tax_id_on_file_the_annual_plan_is_sold(
        self, shop, owner, stripe_double
    ):
        payer(shop, tax_id="12345678Z")

        start(owner, shop, plan="standard", interval="year")

        assert (
            session_params(stripe_double)["line_items"][0]["price"]
            == "price_standard_year"
        )

    def test_a_monthly_plan_over_the_limit_needs_it_too(
        self, shop, owner, stripe_double
    ):
        # Max is the one plan over the limit monthly. It is an upgrade (``upgrade_only``: a Free business is
        # refused it before anything is priced, TestUpgradeOnlyPlans), so here it is sold at sign-up: what this
        # checks is the tax id, not which plans a Free business is offered.
        from hubs.models import Plan

        Plan.objects.filter(slug="max").update(upgrade_only=False)

        refused("billing.tax_id_required", lambda: start(owner, shop, plan="max"))
