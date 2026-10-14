"""Buying a plan or a module for a business: ``billing.checkout.start`` and ``billing.checkout.confirm``.

PLAN-SAAS §3.2 and §4 (lot L2-B): ONE Stripe subscription per business, whose items are the plan and the
modules, at net prices plus OUR tax rates. A business without a Stripe subscription (Free) pays in an
Embedded Checkout (``client_secret`` for the modal); one that has it previews the prorated charge, and
the confirmation adds the item, charged at once (``always_invoice``) or not at all
(``error_if_incomplete``).

Ported from ERPlora/saas ``hubs/subscriptions/tests/`` (origin/develop): ``test_billing_location_before_checkout``
(11), ``test_checkout_customer_update`` (3), ``test_our_tax_engine_at_checkout`` (16),
``test_annual_plan_needs_tax_id_before_checkout`` (4), ``test_vies_before_checkout`` (9), the checkout half of
``hubs/main/tests/test_stripe_service.py`` and ``test_plan_change.py`` (``TestChangePlanUpgrade``) and of
``test_stripe_test_clocks.py`` (the customer carries the clock). The rules that hold:

- WHERE the payer is, before charging (saas#1972): the postal code tells the Canary Islands (outside VAT)
  from the mainland; without it, 409 ``billing.billing_location_required`` and Stripe is never called.
- The rate is ours (``billing.TaxRule``, ADR-0478): ``automatic_tax`` is never sent; Stripe gets a
  ``TaxRate`` per item; a territory without a rule is refused (``billing.tax_engine_missing``).
- Over 400 € with VAT the invoice must name the buyer (RD 1619/2012, art. 4): 409 ``billing.tax_id_required``.
- Stripe never collects the VAT number (it reverse charges by its FORMAT, saas#1479): only one VIES proved
  (or a national one) reaches the customer.
- A promo code replaces the trial (ADR-0107); a free business in its Starter trial keeps the days it has
  left when it buys (no second free ride, and none taken away either).
- No real money while the year's OSS total is unknown (billing README, L2-A): a LIVE key refuses with 409
  ``billing.oss_total_unknown``. A business with an unpaid invoice buys nothing (mockups README §6.18).

Dropped with reason: the hosted (redirect) checkout, every «hosted»/«embedded» pair (the panel only opens
the Embedded Checkout), the quantity of a per-hub plan (one business = one subscription), the location
form and its redirects (the payer is ``hubs.billing_profile.update``), the free sign-up through Stripe
(Free never reaches Stripe, ADR-0154) and the HTMX answers of the old view.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from live.errors import InvalidPayload, NotFound, OperationError, PermissionDenied

from billing import services
from billing.models import CheckoutAttempt, FiscalPolicy, PromoCode, TaxRule
from billing.schemas import CheckoutConfirmIn, CheckoutStartIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import (
    card_error,
    connection_error,
    item,
    preview,
    subscription,
)
from billing.tests.vies_double import (
    FAKE_VAT,
    NOT_REGISTERED,
    REAL_VAT,
    VALID,
    no_network,
    vies_is_down,
    vies_says,
)
from hubs.models import Hub, HubMember, Subscription, SubscriptionItem
from hubs.tests.conftest import add_member

pytestmark = pytest.mark.django_db

NOW_TS = int(timezone.now().timestamp())


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def start(user, hub, **selection):
    return services.checkout_start(
        ctx_for(user), CheckoutStartIn(hub_id=hub.id, **selection)
    ).model_dump()


def confirm(user, hub, **selection):
    return services.checkout_confirm(
        ctx_for(user), CheckoutConfirmIn(hub_id=hub.id, **selection)
    ).model_dump()


def session_params(double):
    return double.last("checkout.sessions.create").params


def payer(hub, **fields):
    """The payer's form saved again (read fresh: what the platform wrote meanwhile stays)."""
    from hubs.models import BillingProfile

    profile = BillingProfile.objects.get(pk=hub.billing_profile_id)
    hub.billing_profile = profile
    for field, value in fields.items():
        setattr(profile, field, value)
    profile.save()
    return hub


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()
    return error.value


# --- A free business pays in an Embedded Checkout ----------------------------------------------------


class TestTheEmbeddedCheckout:
    def test_it_opens_for_the_plan(self, shop, owner, stripe_double):
        answer = start(owner, shop, plan="starter")

        params = session_params(stripe_double)
        assert answer["flow"] == "checkout"
        assert answer["client_secret"].startswith("cs_test_") and answer[
            "session_id"
        ].startswith("cs_test_")
        assert answer["publishable_key"] == "pk_test_double"
        assert answer["preview"] is None
        assert params["ui_mode"] == "embedded_page"
        assert params["mode"] == "subscription"
        assert params["redirect_on_completion"] == "if_required"
        assert "{CHECKOUT_SESSION_ID}" in params["return_url"]
        assert params["line_items"] == [
            {
                "price": "price_starter_month",
                "quantity": 1,
                "tax_rates": [stripe_double.tax_rates[0]["id"]],
            }
        ]

    def test_stripe_tax_and_fixed_payment_methods_are_never_sent(
        self, shop, owner, stripe_double
    ):
        start(owner, shop, plan="starter")

        params = session_params(stripe_double)
        assert "automatic_tax" not in params
        assert "payment_method_types" not in params
        assert "default_tax_rates" not in params.get("subscription_data", {})

    def test_the_address_is_collected_and_the_vat_number_is_not(
        self, shop, owner, stripe_double
    ):
        start(owner, shop, plan="starter")

        params = session_params(stripe_double)
        assert params["billing_address_collection"] == "required"
        assert params["tax_id_collection"] == {"enabled": False}

    def test_the_session_says_what_it_pays_for(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter", interval="year")

        params = session_params(stripe_double)
        assert params["metadata"] == {
            "kind": "hub_plan",
            "hub_id": str(shop.id),
            "plan": "starter",
            "billing_interval": "year",
            "attempt": str(CheckoutAttempt.objects.get().id),
        }
        assert params["subscription_data"]["metadata"] == {"hub_id": str(shop.id)}
        assert params["line_items"][0]["price"] == "price_starter_year"

    def test_a_module_is_bought_alone_on_a_free_business(
        self, shop, owner, inventory, stripe_double
    ):
        start(owner, shop, module="inventory")

        params = session_params(stripe_double)
        assert params["metadata"]["kind"] == "module_purchase"
        assert params["metadata"]["module"] == "inventory"
        assert params["line_items"][0]["price"] == "price_inventory_month"
        # A module has no trial.
        assert "trial_end" not in params["subscription_data"]

    def test_it_is_tagged_for_the_dashboard(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")

        assert (
            session_params(stripe_double)["integration_identifier"]
            == services.INTEGRATION_IDENTIFIER
        )

    def test_the_same_selection_reuses_its_open_session(
        self, shop, owner, stripe_double
    ):
        first = start(owner, shop, plan="starter")
        again = start(owner, shop, plan="starter")

        assert again["client_secret"] == first["client_secret"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == 1

    def test_another_selection_gets_its_own_session(self, shop, owner, stripe_double):
        first = start(owner, shop, plan="starter")
        other = start(owner, shop, plan="starter", interval="year")

        assert other["session_id"] != first["session_id"]
        assert len(stripe_double.calls_to("checkout.sessions.create")) == 2

    def test_a_new_selection_expires_the_other_open_session(self, shop, owner, stripe_double):
        """Two open sessions could both be paid: two subscriptions for one business (review of L2-B)."""
        first = start(owner, shop, plan="starter")
        stripe_double.answer("checkout.sessions.expire", {"id": first["session_id"], "status": "expired"})

        start(owner, shop, plan="standard")

        assert stripe_double.last("checkout.sessions.expire").args == (first["session_id"],)
        assert CheckoutAttempt.objects.get(stripe_session_id=first["session_id"]).status == "expired"

    def test_a_session_stripe_cannot_expire_any_more_does_not_stop_the_new_one(self, shop, owner, stripe_double):
        from billing.tests.stripe_double import invalid_request

        first = start(owner, shop, plan="starter")
        stripe_double.answer("checkout.sessions.expire", invalid_request("checkout_session_not_open", "Not open"))

        assert start(owner, shop, plan="standard")["flow"] == "checkout"
        assert CheckoutAttempt.objects.get(stripe_session_id=first["session_id"]).status == "open"

    def test_a_payer_whose_tax_changed_gets_a_new_session(self, shop, owner, stripe_double):
        first = start(owner, shop, plan="starter")
        payer(shop, billing_postal_code="35001", billing_city="Las Palmas")
        stripe_double.answer("checkout.sessions.expire", {"id": first["session_id"], "status": "expired"})

        again = start(owner, shop, plan="starter")

        assert again["session_id"] != first["session_id"]
        assert session_params(stripe_double)["line_items"][0]["tax_rates"] == []

    def test_a_session_that_expired_is_not_reused(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")
        CheckoutAttempt.objects.update(created_at=timezone.now() - timedelta(hours=24))

        start(owner, shop, plan="starter")

        assert len(stripe_double.calls_to("checkout.sessions.create")) == 2

    def test_the_session_is_created_once_whatever_the_retries(
        self, shop, owner, stripe_double
    ):
        start(owner, shop, plan="starter")

        attempt = CheckoutAttempt.objects.get()
        assert stripe_double.last("checkout.sessions.create").options == {
            "idempotency_key": f"checkout-{attempt.id}"
        }
        assert (attempt.status, attempt.kind, attempt.plan_slug) == (
            "open",
            "plan",
            "starter",
        )


# --- The customer ------------------------------------------------------------------------------------


class TestTheCustomer:
    def test_the_payer_becomes_a_stripe_customer_once(self, shop, owner, stripe_double):
        start(owner, shop, plan="starter")

        created = stripe_double.last("customers.create")
        assert created.params["name"] == "Panadería López SL"
        assert created.params["email"] == "owner@example.com"
        assert created.params["address"] == {
            "line1": "Calle Mayor 1",
            "city": "Madrid",
            "postal_code": "28001",
            "country": "ES",
        }
        assert created.params["preferred_locales"] == ["es"]
        assert created.options["idempotency_key"].startswith(f"customer-{shop.billing_profile.id}-")
        shop.billing_profile.refresh_from_db()
        assert shop.billing_profile.stripe_customer_id == "cus_new"
        params = session_params(stripe_double)
        assert params["customer"] == "cus_new"
        assert params["customer_update"] == {"name": "auto", "address": "auto"}

    def test_a_known_customer_is_brought_up_to_date_not_created_again(
        self, shop, owner, stripe_double
    ):
        payer(shop, stripe_customer_id="cus_known")

        start(owner, shop, plan="starter")

        assert stripe_double.calls_to("customers.create") == []
        assert stripe_double.last("customers.update").args == ("cus_known",)
        assert session_params(stripe_double)["customer"] == "cus_known"

    def test_a_test_clock_travels_to_the_new_customer(self, shop, stripe_double):
        services.ensure_customer(shop, test_clock="clock_123")

        assert (
            stripe_double.last("customers.create").params["test_clock"] == "clock_123"
        )

    def test_without_a_clock_the_customer_does_not_mention_one(
        self, shop, stripe_double
    ):
        services.ensure_customer(shop)

        assert "test_clock" not in stripe_double.last("customers.create").params


class TestOnlyAProvedVatNumberReachesStripe:
    def test_a_number_vies_rejects_never_reaches_stripe(
        self, shop, owner, stripe_double
    ):
        payer(shop, billing_country="DE", billing_postal_code="10115", tax_id=FAKE_VAT)

        with vies_says(**NOT_REGISTERED):
            answer = start(owner, shop, plan="starter")

        assert answer["flow"] == "checkout"
        assert stripe_double.calls_to("customers.tax_ids.create") == []

    def test_a_proved_number_reaches_the_customer(self, shop, owner, stripe_double):
        payer(shop, billing_country="DE", billing_postal_code="10115", tax_id=REAL_VAT)

        with vies_says(**VALID):
            start(owner, shop, plan="starter")

        assert stripe_double.last("customers.tax_ids.create").params == {
            "type": "eu_vat",
            "value": REAL_VAT,
        }

    def test_vies_down_charges_the_vat_and_attaches_nothing(
        self, shop, owner, stripe_double
    ):
        payer(shop, billing_country="DE", billing_postal_code="10115", tax_id=REAL_VAT)

        with vies_is_down():
            start(owner, shop, plan="starter")

        assert stripe_double.calls_to("customers.tax_ids.create") == []
        assert stripe_double.last("tax_rates.create").params["percentage"] == 21.0

    def test_a_national_number_reaches_stripe_without_asking_vies(
        self, shop, owner, stripe_double
    ):
        payer(shop, tax_id="ESB27593136")

        with no_network() as network:
            start(owner, shop, plan="starter")

        network.assert_not_called()
        assert stripe_double.last("customers.tax_ids.create").params == {
            "type": "eu_vat",
            "value": "ESB27593136",
        }

    def test_a_number_already_on_the_customer_is_not_added_twice(
        self, shop, owner, stripe_double
    ):
        payer(shop, tax_id="ESB27593136", stripe_customer_id="cus_known")
        stripe_double.customer_tax_ids["cus_known"] = [
            {"id": "txi_1", "type": "eu_vat", "value": "ESB27593136"}
        ]

        start(owner, shop, plan="starter")

        assert stripe_double.calls_to("customers.tax_ids.create") == []


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
        payer(shop, billing_postal_code="35001", billing_city="Las Palmas")

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

    def test_a_consumer_elsewhere_in_the_eu_pays_spanish_vat_under_the_oss_threshold(
        self, shop, owner, stripe_double
    ):
        payer(shop, billing_country="DE", billing_postal_code="10115")

        start(owner, shop, plan="starter")

        created = stripe_double.last("tax_rates.create").params
        assert (created["percentage"], created["country"]) == (21.0, "ES")

    def test_a_territory_without_a_rule_is_refused(self, shop, owner, stripe_double):
        TaxRule.objects.filter(country_code="ES", region_code="IC").delete()
        payer(shop, billing_postal_code="35001")

        refused(
            "billing.tax_engine_missing", lambda: start(owner, shop, plan="starter")
        )

        assert stripe_double.calls_to("checkout.sessions.create") == []

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
        refused("billing.tax_id_required", lambda: start(owner, shop, plan="max"))


# --- The trial ---------------------------------------------------------------------------------------


class TestTheTrial:
    def test_the_days_left_of_the_sign_up_trial_are_kept(
        self, shop, owner, stripe_double
    ):
        trial_end = Subscription.objects.get(hub=shop).trial_end

        start(owner, shop, plan="starter")

        assert session_params(stripe_double)["subscription_data"]["trial_end"] == int(
            trial_end.timestamp()
        )

    def test_a_trial_about_to_end_is_not_carried(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(
            trial_end=timezone.now() + timedelta(hours=30)
        )

        start(owner, shop, plan="starter")

        assert "trial_end" not in session_params(stripe_double)["subscription_data"]

    def test_a_business_past_its_trial_pays_at_once(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(
            trial_end=timezone.now() - timedelta(days=1)
        )

        start(owner, shop, plan="starter")

        assert "trial_end" not in session_params(stripe_double)["subscription_data"]

    def test_a_promo_code_replaces_the_trial(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(
            trial_end=timezone.now() - timedelta(days=1)
        )
        PromoCode.objects.create(code="canary_2026", trial_days=60)

        start(owner, shop, plan="starter", promo_code=" CANARY_2026 ")

        params = session_params(stripe_double)
        expected = timezone.now() + timedelta(days=60)
        assert abs(params["subscription_data"]["trial_end"] - expected.timestamp()) < 60
        assert params["metadata"]["promo_code"] == "canary_2026"

    def test_the_longer_of_the_two_wins(self, shop, owner, stripe_double):
        PromoCode.objects.create(code="short", trial_days=3)
        trial_end = Subscription.objects.get(hub=shop).trial_end

        start(owner, shop, plan="starter", promo_code="short")

        assert session_params(stripe_double)["subscription_data"]["trial_end"] == int(
            trial_end.timestamp()
        )

    def test_an_invalid_promo_code_never_blocks_the_sale(
        self, shop, owner, stripe_double
    ):
        Subscription.objects.filter(hub=shop).update(trial_end=None)
        PromoCode.objects.create(code="gone", trial_days=30, is_active=False)

        answer = start(owner, shop, plan="starter", promo_code="gone")

        assert answer["flow"] == "checkout"
        params = session_params(stripe_double)
        assert "promo_code" not in params["metadata"]
        assert "trial_end" not in params["subscription_data"]


# --- Who may, and what -------------------------------------------------------------------------------


class TestWhoAndWhat:
    def test_only_the_owner_pays(self, shop, owner, make_user, stripe_double):
        admin = make_user("admin@example.com")
        add_member(shop, admin, HubMember.Role.ADMIN, invited_by=owner)

        with pytest.raises(PermissionDenied):
            start(admin, shop, plan="starter")

        assert stripe_double.calls == []

    def test_a_stranger_does_not_learn_the_business_exists(self, shop, make_user):
        with pytest.raises(NotFound):
            start(make_user("stranger@example.com"), shop, plan="starter")

    def test_a_deleted_business_buys_nothing(self, shop, owner):
        Hub.objects.filter(pk=shop.pk).update(
            status=Hub.Status.DELETING, deletion_requested_at=timezone.now()
        )

        refused("hubs.business_deleted", lambda: start(owner, shop, plan="starter"))

    def test_one_thing_at_a_time(self, shop):
        with pytest.raises(ValueError):
            CheckoutStartIn(hub_id=shop.id)
        with pytest.raises(ValueError):
            CheckoutStartIn(hub_id=shop.id, plan="starter", module="inventory")

    def test_free_is_not_sold(self, shop, owner):
        refused("billing.plan_is_free", lambda: start(owner, shop, plan="free"))

    def test_an_unknown_plan_is_an_invalid_field(self, shop, owner):
        with pytest.raises(InvalidPayload) as error:
            start(owner, shop, plan="platinum")

        assert set(error.value.fields) == {"plan"}

    def test_an_internal_plan_is_not_offered_to_a_customer(self, shop, owner):
        with pytest.raises(InvalidPayload):
            start(owner, shop, plan="payment-test")

    def test_a_plan_without_its_stripe_price_is_not_on_sale(self, shop, owner):
        from hubs.models import Plan

        Plan.objects.filter(slug="starter").update(stripe_price_id_annual="")

        refused(
            "billing.not_on_sale",
            lambda: start(owner, shop, plan="starter", interval="year"),
        )

    def test_an_unknown_or_retired_module_is_an_invalid_field(
        self, shop, owner, inventory
    ):
        inventory.is_active = False
        inventory.save()

        for slug in ("nothing", "inventory"):
            with pytest.raises(InvalidPayload) as error:
                start(owner, shop, module=slug)
            assert set(error.value.fields) == {"module"}

    def test_a_module_the_business_has_is_not_sold_again(self, shop, owner, inventory):
        paid = pay(shop, modules=["inventory"])

        refused("billing.module_owned", lambda: start(owner, paid, module="inventory"))


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
        FiscalPolicy.objects.update(oss_carried_year=timezone.localdate().year)

    def test_a_live_key_is_held_while_invoicing_is_not_switched_on(self, shop, owner, settings, stripe_double,
                                                                   hub_double):
        """Working rules §15: in production nothing is charged without a route that sends the invoice. The model
        existing is not that route: ``PLATFORM_INVOICING_ENABLED`` says the platform hub is wired (review of
        L3-C), and nobody asks the Hub while it is off."""
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

        services.require_payments()
        services.require_payments()

        assert len(hub_double.calls_to("GET", "/health")) == 1

    def test_a_failed_probe_is_asked_again_next_time(self, settings, hub_double):
        from django.core.cache import cache

        cache.clear()
        settings.PLATFORM_INVOICING_ENABLED = True
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 503, {})
        assert services.invoicing_available() is False
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 200, {"status": "ok"})

        assert services.invoicing_available() is True

    def test_a_test_key_is_never_held_for_invoicing(self, shop, owner, settings, stripe_double, offline_hub):
        settings.PLATFORM_INVOICING_ENABLED = False

        assert start(owner, shop, plan="starter")["flow"] == "checkout"

    def test_with_a_live_key_the_oss_total_must_still_be_known(self, shop, owner, settings, stripe_double,
                                                               hub_double):
        settings.STRIPE_SECRET_KEY = "rk_live_double"
        settings.PLATFORM_INVOICING_ENABLED = True
        hub_double.answer("GET", r"^/internal/platform/invoices/health$", 200, {"status": "ok"})
        FiscalPolicy.objects.update(oss_carried_year=None)

        refused("billing.oss_total_unknown", lambda: start(owner, shop, plan="starter"))

        assert stripe_double.calls == []

    def test_a_live_secret_key_is_never_used(self, shop, owner, settings, stripe_double):
        """PLAN-SAAS §4: production holds a RESTRICTED live key (``rk_live_``), never the account's secret."""
        settings.STRIPE_SECRET_KEY = "sk_live_double"

        error = refused("billing.payments_unavailable", lambda: start(owner, shop, plan="starter"))

        assert error.status == 503
        assert stripe_double.calls == []

    def test_a_customer_stripe_already_has_is_found_not_created_twice(self, shop, owner, stripe_double):
        """A checkout that failed after the customer was created rolls back its id: the next one finds it by
        the payer it belongs to (review of L2-B)."""
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


# --- A business that pays already previews and confirms ----------------------------------------------


def paying(shop, stripe_double, **live):
    paid = pay(shop)
    stripe_double.answer(
        "subscriptions.retrieve",
        subscription(
            "sub_1",
            customer="cus_1",
            items=[item("si_plan", "price_starter_month")],
            **live,
        ),
    )
    return paid


class TestTheProratedPreview:
    def test_a_module_is_previewed_on_the_subscription_it_joins(
        self, shop, owner, inventory, stripe_double
    ):
        paid = paying(shop, stripe_double)
        stripe_double.answer(
            "invoices.create_preview", preview(amount_due=1210, tax=210)
        )

        answer = start(owner, paid, module="inventory")

        assert answer["flow"] == "confirm"
        assert (answer["client_secret"], answer["session_id"]) == (None, None)
        sent = stripe_double.last("invoices.create_preview").params
        assert sent["customer"] == "cus_1"
        assert sent["subscription"] == "sub_1"
        details = sent["subscription_details"]
        assert details["items"] == [
            {
                "price": "price_inventory_month",
                "quantity": 1,
                "tax_rates": [stripe_double.tax_rates[0]["id"]],
            }
        ]
        assert details["proration_behavior"] == "always_invoice"
        assert answer["preview"] == {
            "amount_due_cents": 1210,
            "tax_cents": 210,
            "currency": "eur",
            "proration_date": details["proration_date"],
            "charge_starts_at": None,
        }
        assert stripe_double.calls_to("checkout.sessions.create") == []

    def test_a_module_of_an_annual_subscription_is_its_annual_price(
        self, shop, owner, inventory, stripe_double
    ):
        # 299.90 + 100 a year is 483.88 € with VAT: the renewal's invoice must name the buyer.
        payer(shop, tax_id="12345678Z")
        pay(shop, interval="year")
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                items=[item("si_plan", "price_starter_year", interval="year")]
            ),
        )
        stripe_double.answer("invoices.create_preview", preview())

        start(owner, shop, module="inventory")

        assert stripe_double.last("invoices.create_preview").params[
            "subscription_details"
        ]["items"][0]["price"] == ("price_inventory_year")

    def test_a_new_plan_is_previewed_on_the_plan_item(self, shop, owner, stripe_double):
        paid = paying(shop, stripe_double)
        stripe_double.answer(
            "invoices.create_preview", preview(amount_due=3000, tax=520)
        )

        answer = start(owner, paid, plan="standard")

        items = stripe_double.last("invoices.create_preview").params[
            "subscription_details"
        ]["items"]
        assert items == [
            {
                "id": "si_plan",
                "price": "price_standard_month",
                "tax_rates": [stripe_double.tax_rates[0]["id"]],
            }
        ]
        assert answer["preview"]["amount_due_cents"] == 3000


class TestConfirmingAModule:
    def test_the_item_is_added_and_charged_at_once_or_not_at_all(
        self, shop, owner, inventory, stripe_double
    ):
        paid = paying(shop, stripe_double)
        stripe_double.answer(
            "subscription_items.create", item("si_inventory", "price_inventory_month")
        )
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(
                items=[
                    item("si_plan", "price_starter_month"),
                    item("si_inventory", "price_inventory_month"),
                ]
            ),
        )

        answer = confirm(owner, paid, module="inventory", proration_date=NOW_TS)

        sent = stripe_double.last("subscription_items.create")
        assert sent.params == {
            "subscription": "sub_1",
            "price": "price_inventory_month",
            "quantity": 1,
            "tax_rates": [stripe_double.tax_rates[0]["id"]],
            "proration_behavior": "always_invoice",
            "proration_date": NOW_TS,
            "payment_behavior": "error_if_incomplete",
            "metadata": {"hub_id": str(shop.id), "module": "inventory"},
        }
        assert sent.options["idempotency_key"].startswith(
            f"module-{shop.id}-inventory-"
        )
        assert (
            SubscriptionItem.objects.get(
                subscription__hub=shop, module_slug="inventory"
            ).stripe_item_id
            == "si_inventory"
        )
        assert [module["slug"] for module in answer["modules"]] == ["inventory"]
        assert Hub.objects.get(pk=shop.pk).state_version > paid.state_version

    @pytest.mark.parametrize("offset", [120, -2 * 3600])
    def test_a_preview_from_another_moment_is_previewed_again(self, shop, owner, inventory, stripe_double, offset):
        """The proration date chooses what is charged: one in the future charges less (review of L2-B)."""
        paid = paying(shop, stripe_double)
        moment = int(timezone.now().timestamp()) + offset

        refused("billing.preview_expired", lambda: confirm(owner, paid, module="inventory", proration_date=moment))

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_once_charged_a_slow_read_back_is_not_a_failure(self, shop, owner, inventory, stripe_double):
        """The module was added and paid: «nothing was charged» would be a lie; the webhook applies it."""
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", item("si_inventory", "price_inventory_month"))
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(items=[item("si_plan", "price_starter_month")]),
            connection_error(),
        )

        answer = confirm(owner, paid, module="inventory", proration_date=int(timezone.now().timestamp()))

        assert answer["hub_id"] == shop.id

    def test_a_declined_card_adds_nothing(self, shop, owner, inventory, stripe_double):
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", card_error())

        error = refused(
            "billing.card_declined",
            lambda: confirm(
                owner, paid, module="inventory", proration_date=NOW_TS
            ),
        )

        assert error.status == 409
        assert not SubscriptionItem.objects.filter(
            subscription__hub=shop, module_slug="inventory"
        ).exists()

    def test_a_free_business_goes_through_the_checkout(self, shop, owner, inventory):
        refused(
            "billing.checkout_required",
            lambda: confirm(owner, shop, module="inventory", proration_date=NOW_TS),
        )

    def test_a_module_it_has_is_not_added_twice(
        self, shop, owner, inventory, stripe_double
    ):
        paid = pay(shop, modules=["inventory"])

        refused(
            "billing.module_owned",
            lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS),
        )

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_a_renewal_over_the_limit_needs_the_tax_id_before_adding(
        self, shop, owner, inventory, stripe_double
    ):
        # Standard yearly (549.90) is already over 400 € with VAT: adding to it needs the payer named.
        from hubs.models import Plan

        paid = paying(shop, stripe_double)
        Subscription.objects.filter(hub=paid).update(
            billing_interval="year", plan=Plan.objects.get(slug="standard")
        )

        refused(
            "billing.tax_id_required",
            lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS),
        )

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_the_net_price_is_what_the_location_guard_sees(
        self, shop, owner, inventory, stripe_double
    ):
        paid = paying(shop, stripe_double)
        payer(paid, billing_postal_code="")

        refused(
            "billing.billing_location_required",
            lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS),
        )

        assert Decimal(inventory.price_monthly_cents) / 100 == Decimal("10")


# --- Who pays is the payer, not the role (review of L2-B) ----------------------------------------------


def transferred(hub, old_owner, make_user):
    """The business after an accepted transfer: a new owner, the payer still the previous owner's."""
    from hubs.models import HubMember

    new_owner = make_user("new-owner@example.com", language="es")
    HubMember.objects.filter(hub=hub, user=old_owner).delete()
    now = timezone.now()
    HubMember.objects.create(hub=hub, user=new_owner, role=HubMember.Role.OWNER, joined_at=now, accepted_at=now)
    return new_owner


class TestThePayerPays:
    def test_a_new_owner_does_not_buy_with_the_previous_owners_payer(self, shop, owner, make_user, stripe_double):
        new_owner = transferred(shop, owner, make_user)

        error = refused("billing.payer_required", lambda: start(new_owner, shop, plan="starter"))

        assert error.status == 409
        assert stripe_double.calls == []

    def test_once_the_new_owner_says_who_pays_a_free_business_is_bought(self, shop, owner, make_user, stripe_double):
        from hubs import services as hub_services
        from hubs.schemas import BillingProfileIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        new_owner = transferred(shop, owner, make_user)
        hub_services.billing_profile_update(
            hub_ctx(new_owner),
            BillingProfileIn(hub_id=shop.id, billing_name="Nuevo SL", billing_country="ES", billing_postal_code="28002"),
        )

        assert start(new_owner, Hub.objects.get(pk=shop.pk), plan="starter")["flow"] == "checkout"
        assert stripe_double.last("customers.create").params["name"] == "Nuevo SL"

    def test_a_subscription_still_paid_by_the_previous_owner_is_not_touched(self, shop, owner, make_user,
                                                                           inventory, stripe_double):
        from hubs import services as hub_services
        from hubs.schemas import BillingProfileIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        paid = pay(shop)
        new_owner = transferred(paid, owner, make_user)
        hub_services.billing_profile_update(
            hub_ctx(new_owner),
            BillingProfileIn(hub_id=paid.id, billing_name="Nuevo SL", billing_country="ES", billing_postal_code="28002"),
        )

        refused("billing.payer_required", lambda: start(new_owner, paid, module="inventory"))
        refused("billing.payer_required", lambda: confirm(new_owner, paid, module="inventory", proration_date=NOW_TS))

        assert stripe_double.calls == []


# --- Retries, limits and trials (review of L2-B) -----------------------------------------------------


class TestRetriesAndLimits:
    def test_a_retry_after_the_card_changed_is_charged_again(self, shop, owner, inventory, stripe_double):
        """Stripe keeps the answer of an idempotency key, the decline included: each confirmation is its own."""
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", card_error(), item("si_inventory", "price_inventory_month"))

        refused("billing.card_declined", lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS))
        answer = confirm(owner, paid, module="inventory", proration_date=NOW_TS)

        keys = [call.options["idempotency_key"] for call in stripe_double.calls_to("subscription_items.create")]
        assert keys[0] != keys[1]
        assert answer["hub_id"] == shop.id

    def test_a_charge_stripe_did_not_confirm_never_says_nothing_was_charged(self, shop, owner, inventory, stripe_double):
        paid = paying(shop, stripe_double)
        stripe_double.answer("subscription_items.create", connection_error())

        error = refused(
            "billing.stripe_unavailable", lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS)
        )

        assert error.status == 503
        assert "Nothing was charged" not in error.message

    def test_a_subscription_holds_twenty_items_at_most(self, shop, owner, inventory, stripe_double):
        paid = pay(shop)
        lines = [item("si_plan", "price_starter_month")] + [item(f"si_{n}", f"price_other_{n}") for n in range(19)]
        stripe_double.answer("subscriptions.retrieve", subscription(items=lines))

        refused("billing.too_many_items", lambda: confirm(owner, paid, module="inventory", proration_date=NOW_TS))

        assert stripe_double.calls_to("subscription_items.create") == []

    def test_a_module_added_during_a_paid_trial_says_when_it_starts_charging(self, shop, owner, inventory,
                                                                          stripe_double):
        trial_end = int((timezone.now() + timedelta(days=9)).timestamp())
        paid = pay(shop, status="trialing")
        stripe_double.answer(
            "subscriptions.retrieve",
            subscription(status="trialing", trial=(NOW_TS, trial_end), items=[item("si_plan", "price_starter_month")]),
        )
        stripe_double.answer("invoices.create_preview", preview(amount_due=0, tax=0))

        answer = start(owner, paid, module="inventory")

        assert answer["preview"]["amount_due_cents"] == 0
        assert answer["preview"]["charge_starts_at"] == trial_end


class TestAPlanOnTopOfModules:
    """A Free business that bought modules alone pays a subscription without a plan item: buying the plan
    keeps the days left of its sign-up trial and honours a promo code, as the checkout does (review of L2-B)."""

    def modules_only(self, shop, stripe_double, inventory):
        paid = pay(shop, plan="free", modules=["inventory"])
        stripe_double.answer(
            "subscriptions.retrieve", subscription(items=[item("si_inventory", "price_inventory_month")])
        )
        return paid

    def test_the_preview_and_the_change_carry_the_trial_left(self, shop, owner, inventory, stripe_double):
        from billing import services as billing_services
        from billing.schemas import PlanChangeIn

        trial_end = Subscription.objects.get(hub=shop).trial_end
        paid = self.modules_only(shop, stripe_double, inventory)
        stripe_double.answer("invoices.create_preview", preview(amount_due=0, tax=0))
        stripe_double.answer("subscriptions.update", subscription(items=[item("si_inventory", "price_inventory_month"),
                                                                         item("si_plan", "price_starter_month")]))

        start(owner, paid, plan="starter")
        billing_services.plan_change(
            ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", proration_date=NOW_TS)
        )

        details = stripe_double.last("invoices.create_preview").params["subscription_details"]
        sent = stripe_double.last("subscriptions.update").params
        assert details["trial_end"] == sent["trial_end"] == int(trial_end.timestamp())
        assert details["proration_behavior"] == sent["proration_behavior"] == "none"

    def test_a_promo_code_is_honoured(self, shop, owner, inventory, stripe_double):
        from billing import services as billing_services
        from billing.schemas import PlanChangeIn

        Subscription.objects.filter(hub=shop).update(trial_end=timezone.now() - timedelta(days=1))
        PromoCode.objects.create(code="canary_2026", trial_days=60)
        paid = self.modules_only(shop, stripe_double, inventory)
        stripe_double.answer("subscriptions.update", subscription())

        billing_services.plan_change(
            ctx_for(owner),
            PlanChangeIn(hub_id=paid.id, plan="starter", proration_date=NOW_TS, promo_code="Canary_2026"),
        )

        sent = stripe_double.last("subscriptions.update").params
        assert abs(sent["trial_end"] - (timezone.now() + timedelta(days=60)).timestamp()) < 60
        assert PromoCode.objects.get().redemption_count == 1


class TestAPromoCodeOncePerBusinessAndPayer:
    def redeemed(self, hub, code="canary_2026", customer="cus_1"):
        from billing.models import PromoRedemption

        promo = PromoCode.objects.get_or_create(code=code, defaults={"trial_days": 60})[0]
        PromoRedemption.objects.create(promo=promo, hub=hub, stripe_customer_id=customer, stripe_session_id="cs_old")
        return promo

    def test_the_same_business_does_not_use_it_twice(self, shop, owner, stripe_double):
        Subscription.objects.filter(hub=shop).update(trial_end=None)
        self.redeemed(shop)

        start(owner, shop, plan="starter", promo_code="canary_2026")

        params = session_params(stripe_double)
        assert "promo_code" not in params["metadata"]
        assert "trial_end" not in params["subscription_data"]

    def test_the_same_payer_does_not_use_it_for_another_business(self, shop, owner, stripe_double, plans):
        from hubs.tests.conftest import create_business

        Subscription.objects.filter(hub=shop).update(trial_end=None)
        payer(shop, stripe_customer_id="cus_1")
        other = pay(create_business(make_free_owner(), name="Otro"), sub_id="sub_x")
        self.redeemed(other, customer="cus_1")

        start(owner, shop, plan="starter", promo_code="canary_2026")

        assert "promo_code" not in session_params(stripe_double)["metadata"]


def make_free_owner():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email="other-owner@example.com", password=None)
