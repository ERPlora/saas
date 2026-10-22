"""billing's write side outside the routes: the clearance of a VAT number and the hook hubs will call.

``clear_tax_id_for_stripe`` is the seller's door (contract §9, saas#1621): whoever puts a tax id on a
Stripe customer or prices a sale asks it, never ``VatCheck`` raw. ``validate_vat_for_profile`` is what
``hubs.billing_profile.update`` calls in lot L2-B instead of its form-only ``validate_tax_id``: the
number written as ERPlora invoices it, plus its VIES verdict. Both never block: without a proven
verdict the customer pays the VAT, which is recoverable.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import DatabaseError

from billing import queries, services
from billing.models import VatCheck
from billing.tests.stripe_double import connection_error, invalid_request
from billing.tests.vies_double import (
    FAKE_VAT,
    NOT_REGISTERED,
    REAL_VAT,
    VALID,
    no_network,
    vies_says,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _issuer(issuer_identity):
    return issuer_identity


class TestTheClearance:
    def test_no_number_is_absent(self):
        with no_network() as vies:
            clearance = services.clear_tax_id_for_stripe("  ")

        vies.assert_not_called()
        assert (
            clearance.status,
            clearance.may_travel_to_stripe,
            clearance.verified,
        ) == ("absent", False, False)

    def test_a_proved_number_travels_and_grants_reverse_charge(self):
        with vies_says(**VALID):
            clearance = services.clear_tax_id_for_stripe(
                REAL_VAT, customer_country="DE"
            )

        assert (
            clearance.status,
            clearance.may_travel_to_stripe,
            clearance.verified,
        ) == ("verified", True, True)
        assert clearance.check.consultation_number == VALID["requestIdentifier"]

    def test_a_number_vies_does_not_know_stays_here(self):
        with vies_says(**NOT_REGISTERED):
            clearance = services.clear_tax_id_for_stripe(
                FAKE_VAT, customer_country="DE"
            )

        assert (clearance.status, clearance.may_travel_to_stripe) == ("invalid", False)

    def test_a_national_number_travels_without_asking(self):
        with no_network() as vies:
            clearance = services.clear_tax_id_for_stripe(
                "ESB12345678", customer_country="ES"
            )

        vies.assert_not_called()
        assert (
            clearance.status,
            clearance.may_travel_to_stripe,
            clearance.verified,
        ) == ("national", True, False)

    def test_a_uk_number_travels_as_identification(self):
        with no_network() as vies:
            clearance = services.clear_tax_id_for_stripe("GB123456789")

        vies.assert_not_called()
        assert (
            clearance.status,
            clearance.may_travel_to_stripe,
            clearance.verified,
        ) == ("outside_vies", True, False)

    def test_a_log_that_cannot_be_written_is_unavailable_and_said(self, caplog):
        """The sale is not blocked by our own database: it pays VAT, and the reason is logged."""
        with (
            vies_says(**VALID),
            patch.object(VatCheck, "save", side_effect=DatabaseError("db down")),
        ):
            clearance = services.clear_tax_id_for_stripe(
                REAL_VAT, customer_country="DE"
            )

        assert (clearance.status, clearance.may_travel_to_stripe) == (
            "unavailable",
            False,
        )
        assert any(
            r.levelname == "ERROR" and "[VIES]" in r.getMessage()
            for r in caplog.records
        )


class TestTheProfileHook:
    def test_a_european_number_is_written_with_its_prefix_and_verdict(self):
        with vies_says(**VALID) as vies:
            result = services.validate_vat_for_profile("DE", " 812 871 812 ")

        assert vies.call_args.kwargs["json"]["countryCode"] == "DE"
        assert result.vat_number == "DE812871812"
        assert (result.status, result.reverse_charge) == ("verified", True)
        assert (result.name, result.address) == (VALID["name"], VALID["address"])
        assert result.consultation_number == VALID["requestIdentifier"]
        assert result.checked_at is not None

    def test_greece_gets_its_vies_prefix(self):
        with vies_says(**VALID) as vies:
            assert (
                services.validate_vat_for_profile("GR", "094014201").vat_number
                == "EL094014201"
            )

        assert vies.call_args.kwargs["json"]["countryCode"] == "EL"

    def test_a_spanish_nif_stays_as_typed_and_is_not_asked_about(self):
        with no_network() as vies:
            result = services.validate_vat_for_profile("ES", "b-2759.3136")

        vies.assert_not_called()
        assert (result.vat_number, result.status, result.reverse_charge) == (
            "B27593136",
            "national",
            False,
        )

    def test_no_number_is_a_consumer(self):
        with no_network() as vies:
            result = services.validate_vat_for_profile("FR", "")

        vies.assert_not_called()
        assert (result.vat_number, result.status) == ("", "absent")

    @pytest.mark.parametrize(
        "country, vat_number",
        [
            ("", "812871812"),
            ("DE", "ZZ812871812"),
            ("DE", "DE8"),
            ("ES", "B2759313"),
            ("US", "123456789"),
        ],
        ids=[
            "no prefix nor country",
            "unknown prefix",
            "too short",
            "spanish too short",
            "no vies country",
        ],
    )
    def test_a_shape_that_cannot_be_a_vat_number_is_refused_before_asking(
        self, country, vat_number
    ):
        with no_network() as vies, pytest.raises(services.MalformedVatNumber):
            services.validate_vat_for_profile(country, vat_number)

        vies.assert_not_called()
        assert VatCheck.objects.count() == 0


class TestTheAdminOverrideDoor:
    """The override needs a door for a person, with its reason (ported from test_vies.TestTheAdminDoor)."""

    @pytest.fixture
    def vat_admin(self):
        from django.contrib.admin.sites import site

        return site._registry[VatCheck]

    def _request(self, make_user):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        request = RequestFactory().post("/admin/billing/vatcheck/add/")
        request.user = make_user("admin-vies@example.com")
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_the_log_is_registered_and_cannot_be_rewritten(self, vat_admin):
        """A query is not edited nor deleted: that would forge the proof."""
        assert vat_admin.has_delete_permission(None) is False
        assert vat_admin.has_change_permission(None) is False

    def test_adding_one_by_hand_is_an_override_with_author_and_reason(
        self, vat_admin, make_user
    ):
        from unittest.mock import Mock

        request = self._request(make_user)
        draft = VatCheck(vat_number="fr 12345678901")
        form = Mock(
            cleaned_data={
                "override_reason": "Incorporated on 2026-08-20, not in VIES yet"
            }
        )

        vat_admin.save_model(request, draft, form, change=False)

        stored = queries.latest_vat_check("FR12345678901")
        assert stored.status == "verified"
        assert stored.override_by == "admin-vies@example.com"
        assert stored.override_reason == "Incorporated on 2026-08-20, not in VIES yet"
        assert stored.grants_reverse_charge is True
        assert draft.pk == stored.pk


class TestTheOperationNeedsAnAccount:
    def test_a_system_context_cannot_spend_a_persons_vies_budget(self):
        """The budget and the event are the account's: the platform itself has no account to charge."""
        from live.context import Scope, system_context
        from live.errors import Unauthorized

        from billing.schemas import VatCheckIn

        with no_network() as vies, pytest.raises(Unauthorized):
            services.vat_check_run(system_context(Scope("user", "system")), VatCheckIn(vat_number=REAL_VAT))

        vies.assert_not_called()


# --- BILLING-F28: the Stripe prices pasted on a plan are the plan's -----------------------------------


def stripe_price(price_id="price_month", **fields):
    return {
        "id": price_id,
        "object": "price",
        "active": True,
        "currency": "eur",
        "unit_amount": 2999,
        "tax_behavior": "exclusive",
        "product": "prod_starter",
        "recurring": {"interval": "month", "interval_count": 1},
        **fields,
    }


@pytest.mark.django_db
class TestThePricesOfAPlan:
    """Pasted in the admin, a price is checked in Stripe before the plan sells with it: it exists in this mode
    (a test id in production is not found), it is active, in euros, every month or every year as its field says,
    the plan's amount, and NET (``exclusive``: our VAT goes on top). Nothing pasted, nothing asked."""

    def check(self, stripe_double, **pasted):
        return services.plan_price_problems(
            prices={"stripe_price_id": "", "stripe_price_id_annual": "", **pasted},
            amounts={"price_monthly": Decimal("29.99"), "price_annual": Decimal("299.90")},
            product="prod_starter",
        )

    def test_prices_that_are_the_plans_pass(self, stripe_double):
        stripe_double.answer(
            "prices.retrieve",
            stripe_price(),
            stripe_price("price_year", unit_amount=29990, recurring={"interval": "year", "interval_count": 1}),
        )

        assert self.check(stripe_double, stripe_price_id="price_month", stripe_price_id_annual="price_year") == {}

    def test_nothing_pasted_asks_nothing(self, stripe_double):
        assert self.check(stripe_double) == {}
        assert stripe_double.calls == []

    @pytest.mark.parametrize(
        "fields",
        [
            {"active": False},
            {"currency": "usd"},
            {"unit_amount": 2900},
            {"tax_behavior": "inclusive"},
            {"tax_behavior": "unspecified"},
            {"recurring": {"interval": "year", "interval_count": 1}},
            {"recurring": None},
            {"product": "prod_other"},
        ],
    )
    def test_a_price_that_would_charge_otherwise_is_refused(self, stripe_double, fields):
        stripe_double.answer("prices.retrieve", stripe_price(**fields))

        assert list(self.check(stripe_double, stripe_price_id="price_month")) == ["stripe_price_id"]

    def test_a_price_stripe_does_not_have_is_refused(self, stripe_double):
        stripe_double.answer("prices.retrieve", invalid_request("No such price: 'price_test_x'"))

        assert list(self.check(stripe_double, stripe_price_id="price_test_x")) == ["stripe_price_id"]

    def test_stripe_not_answering_is_said_not_taken_for_a_yes(self, stripe_double):
        stripe_double.answer("prices.retrieve", connection_error())

        with pytest.raises(services.PriceCheckUnavailable):
            self.check(stripe_double, stripe_price_id="price_month")

    def test_without_stripe_the_prices_are_not_checked(self, stripe_double, settings):
        settings.STRIPE_SECRET_KEY = ""

        with pytest.raises(services.PriceCheckUnavailable):
            self.check(stripe_double, stripe_price_id="price_month")
        assert stripe_double.calls == []

    def test_stripe_not_answering_and_stripe_not_configured_are_told_apart(self, stripe_double, settings):
        """Not configured (development) is saved with a warning; not answering is not saved (BILLING-F28)."""
        stripe_double.answer("prices.retrieve", connection_error())
        with pytest.raises(services.PriceCheckFailed):
            self.check(stripe_double, stripe_price_id="price_month")

        settings.STRIPE_SECRET_KEY = ""
        with pytest.raises(services.PriceCheckSkipped):
            self.check(stripe_double, stripe_price_id="price_month")


@pytest.mark.django_db
class TestThePricesOfAModule:
    """APPS-F04: the Stripe prices pasted on a paid module pass the same checks as a plan's (BILLING-F28), against
    the module's own fields and its amounts in cents, so the Store never paints one price while Stripe charges
    another."""

    def check(self, stripe_double, **pasted):
        return services.module_price_problems(
            prices={"stripe_price_id_monthly": "", "stripe_price_id_annual": "", **pasted},
            amounts={"price_monthly_cents": 2999, "price_annual_cents": 29990},
            product="prod_starter",
        )

    def test_prices_that_are_the_modules_pass(self, stripe_double):
        stripe_double.answer(
            "prices.retrieve",
            stripe_price(),
            stripe_price("price_year", unit_amount=29990, recurring={"interval": "year", "interval_count": 1}),
        )

        assert self.check(stripe_double, stripe_price_id_monthly="price_month", stripe_price_id_annual="price_year") == {}

    def test_nothing_pasted_asks_nothing(self, stripe_double):
        assert self.check(stripe_double) == {}
        assert stripe_double.calls == []

    @pytest.mark.parametrize(
        ("fields", "pasted", "field"),
        [
            ({"currency": "usd"}, "stripe_price_id_monthly", "stripe_price_id_monthly"),
            ({"tax_behavior": "inclusive"}, "stripe_price_id_monthly", "stripe_price_id_monthly"),
            ({"product": "prod_other"}, "stripe_price_id_monthly", "stripe_price_id_monthly"),
            ({"unit_amount": 29990}, "stripe_price_id_annual", "stripe_price_id_annual"),
        ],
    )
    def test_a_price_that_would_charge_otherwise_is_refused_under_its_field(self, stripe_double, fields, pasted, field):
        stripe_double.answer("prices.retrieve", stripe_price(**fields))

        assert list(self.check(stripe_double, **{pasted: "price_x"})) == [field]

    def test_another_amount_names_the_module_and_both_amounts(self, stripe_double):
        stripe_double.answer("prices.retrieve", stripe_price(unit_amount=900))

        (problem,) = self.check(stripe_double, stripe_price_id_monthly="price_month").values()

        assert "module" in problem and "plan" not in problem
        assert "9.00" in problem and "29.99" in problem

    def test_stripe_not_answering_is_said_not_taken_for_a_yes(self, stripe_double):
        stripe_double.answer("prices.retrieve", connection_error())

        with pytest.raises(services.PriceCheckFailed):
            self.check(stripe_double, stripe_price_id_monthly="price_month")

    def test_without_stripe_the_prices_are_not_checked(self, stripe_double, settings):
        settings.STRIPE_SECRET_KEY = ""

        with pytest.raises(services.PriceCheckSkipped):
            self.check(stripe_double, stripe_price_id_monthly="price_month")
        assert stripe_double.calls == []
