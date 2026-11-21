"""The reads of tax (``billing.queries.tax``): ``billing.tax.preview``, the rule in force and the fiscal policy.

``billing.tax.preview`` says what a sale to this payer will carry, before anything is charged. A query (READ ONLY):
it never asks VIES nor writes a row, it reads the verdict on file —the one ``billing.vat_check.run`` just logged— and
the rule table. The create-business and billing-profile forms use it to say «€29.99 + 21 % VAT — €36.29» or «reverse
charge: no VAT» before the payment, with the same ``quote_vat`` the checkout will use, so what is announced is what is
charged.

Tax rates are editable DATA, not a constant of the code (the migration's seed is ``test_tax_rules.py``). The
resolution is ``billing.queries.tax_rule`` (only ``billing.services`` and ``billing.queries`` touch the ORM) and the
policy's threshold ``billing.queries.uses_destination_rate``.

The two tests that sum real invoices into the OSS threshold
(``test_crossing_the_threshold_switches_to_destination_rates``,
``test_domestic_and_b2b_sales_do_not_count_towards_the_threshold``) count what this SaaS adds too: the
amounts carried from the old SaaS, unpaid invoices and credit notes. The failing threshold query raises
``DatabaseError`` (the only failure it may swallow) instead of a bare ``RuntimeError``.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import DatabaseError
from django.test import Client
from live.errors import PermissionDenied

from billing import queries
from billing.models import FiscalPolicy, TaxCategory, TaxRule, VatCheck
from billing.schemas.tax import TaxPreviewIn
from billing.tests.conftest import ctx_for
from billing.tests.vies_double import no_network

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
URL = "/api/billing/tax-preview"


def _preview(user, **params):
    return queries.tax_preview(ctx_for(user), TaxPreviewIn(**params)).model_dump()


@pytest.fixture
def category(db):
    return TaxCategory.objects.get(key="service.saas_subscription")


class TestWhatTheSaleCarries:
    def test_a_spanish_consumer_pays_21_on_top_of_the_net_price(self, buyer):
        preview = _preview(
            buyer, country="ES", postal_code="28001", net=Decimal("29.99")
        )

        assert preview == {
            "country": "ES",
            "resolvable": True,
            "treatment": "domestic",
            "tax_country": "ES",
            "rate": Decimal("21.00"),
            "net": Decimal("29.99"),
            "tax": Decimal("6.30"),
            "total": Decimal("36.29"),
            "b2b": False,
            "vat_status": "absent",
            "reverse_charge": False,
        }

    def test_the_canaries_pay_the_net_price(self, buyer):
        preview = _preview(
            buyer, country="ES", postal_code="35001", net=Decimal("29.99")
        )

        assert (preview["treatment"], preview["rate"], preview["total"]) == (
            "not_subject",
            Decimal("0.00"),
            Decimal("29.99"),
        )

    def test_a_european_business_with_a_proof_on_file_is_reverse_charged(self, buyer):
        VatCheck.objects.create(
            vat_number="DE812871812",
            status=VatCheck.VERIFIED,
            consultation_number="WAPIAAAAXok",
        )

        with no_network() as vies:
            preview = _preview(
                buyer,
                country="DE",
                postal_code="10115",
                vat_number="de 812871812",
                net=Decimal("100"),
            )

        vies.assert_not_called()
        assert (preview["treatment"], preview["tax_country"]) == (
            "reverse_charge",
            "DE",
        )
        assert (preview["b2b"], preview["vat_status"], preview["reverse_charge"]) == (
            True,
            "verified",
            True,
        )
        assert (preview["tax"], preview["total"]) == (
            Decimal("0.00"),
            Decimal("100.00"),
        )

    def test_a_number_nobody_checked_yet_pays_vat_and_says_so(self, buyer):
        """The query never asks VIES: the form calls ``billing.vat_check.run`` first."""
        with no_network() as vies:
            preview = _preview(
                buyer,
                country="DE",
                postal_code="10115",
                vat_number="DE812871812",
                net=Decimal("100"),
            )

        vies.assert_not_called()
        assert (
            preview["vat_status"],
            preview["reverse_charge"],
            preview["treatment"],
        ) == ("unchecked", False, "domestic")
        assert preview["total"] == Decimal("121.00")

    @pytest.mark.parametrize("status", [VatCheck.INVALID, VatCheck.UNAVAILABLE])
    def test_a_verdict_that_is_no_proof_pays_vat(self, buyer, status):
        VatCheck.objects.create(vat_number="DE812871812", status=status)

        preview = _preview(
            buyer,
            country="DE",
            postal_code="10115",
            vat_number="DE812871812",
            net=Decimal("100"),
        )

        assert (preview["vat_status"], preview["reverse_charge"]) == (status, False)

    def test_a_spanish_business_is_national(self, buyer):
        preview = _preview(
            buyer,
            country="ES",
            postal_code="28001",
            vat_number="B27593136",
            net=Decimal("100"),
        )

        assert (preview["b2b"], preview["vat_status"], preview["treatment"]) == (
            True,
            "national",
            "domestic",
        )

    def test_a_uk_payer_is_not_subject(self, buyer):
        preview = _preview(
            buyer,
            country="GB",
            postal_code="SW1A 1AA",
            vat_number="GB123456789",
            net=Decimal("100"),
        )

        assert (preview["treatment"], preview["vat_status"], preview["total"]) == (
            "not_subject",
            "outside_vies",
            Decimal("100.00"),
        )

    def test_an_unknown_spanish_place_cannot_be_priced(self, buyer):
        """«3500» is Benidorm without its leading 0, not Las Palmas: no 0 % by a guess."""
        preview = _preview(buyer, country="ES", postal_code="3500", net=Decimal("100"))

        assert (preview["resolvable"], preview["rate"], preview["total"]) == (False, None, None)
        assert _preview(buyer, country="ES", postal_code="03500", net=Decimal("100"))["rate"] == Decimal("21.00")

    def test_a_territory_without_a_rule_cannot_be_sold_to(self, buyer):
        preview = _preview(buyer, country="US", postal_code="10001", net=Decimal("100"))

        assert preview["resolvable"] is False
        assert (
            preview["treatment"],
            preview["rate"],
            preview["tax"],
            preview["total"],
        ) == (None, None, None, None)

    def test_a_module_is_priced_by_its_own_category(self, buyer):
        from datetime import date

        from billing.models import TaxCategory, TaxRule

        TaxRule.objects.create(
            category=TaxCategory.objects.get(key="service.software_license"),
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2020, 1, 1),
        )

        assert _preview(
            buyer,
            country="ES",
            postal_code="28001",
            net=Decimal("100"),
            category="module",
        )["rate"] == Decimal("10.00")
        assert _preview(
            buyer,
            country="ES",
            postal_code="28001",
            net=Decimal("100"),
            category="plan",
        )["rate"] == Decimal("21.00")


class TestTheInput:
    @pytest.mark.parametrize(
        "params",
        [
            {"country": "E"},
            {"country": "ES", "net": "-1"},
            {"country": "ES", "net": "1.001"},
        ],
    )
    def test_a_malformed_question_is_refused(self, params):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TaxPreviewIn(**params)


class TestWhoMayAsk:
    def test_it_needs_the_permission_of_a_signed_in_account(self):
        with pytest.raises(PermissionDenied):
            queries.tax_preview(ctx_for(None), TaxPreviewIn(country="ES"))

    def test_by_its_route(self, buyer):
        client = Client()
        client.force_login(buyer)

        response = client.get(
            URL,
            {"country": "ES", "postal_code": "28001", "net": "29.99"},
            HTTP_HOST=HOST,
        )

        assert response.status_code == 200, response.content
        assert (response.json()["rate"], response.json()["total"]) == ("21.00", "36.29")

    def test_anonymous_is_401(self, client):
        assert client.get(URL, {"country": "ES"}, HTTP_HOST=HOST).status_code == 401


class TestResolution:
    def test_a_rule_for_the_category_beats_the_generic_one(self, category):
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2026, 1, 1),
        )

        assert queries.tax_rule(
            country_code="ES", category_key="service.saas_subscription"
        ).rate_pct == Decimal("10.00")
        assert queries.tax_rule(
            country_code="ES", category_key="service.generic"
        ).rate_pct == Decimal("21.00")

    def test_a_category_without_its_own_rule_falls_back_to_the_generic(self, category):
        assert queries.tax_rule(
            country_code="DE", category_key="service.saas_subscription"
        ).rate_pct == Decimal("19.00")

    def test_the_region_wins_over_the_country_wide_rule(self):
        mainland = queries.tax_rule(
            country_code="ES", region_code="", category_key="service.generic"
        )
        canaries = queries.tax_rule(
            country_code="ES", region_code="IC", category_key="service.generic"
        )

        assert mainland.rate_pct == Decimal("21.00")
        assert canaries.is_subject is False

    def test_a_rule_that_is_not_yet_in_force_does_not_apply(self, category):
        """A change of rate is SCHEDULED; it does not rewrite the past."""
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("23.00"),
            valid_from=date(2027, 1, 1),
        )

        today = queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2026, 8, 2),
        )
        later = queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2027, 3, 1),
        )

        assert today.rate_pct == Decimal("21.00")
        assert later.rate_pct == Decimal("23.00")

    def test_an_expired_rule_does_not_apply(self, category):
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("18.00"),
            valid_from=date(2010, 7, 1),
            valid_to=date(2012, 8, 31),
        )

        assert queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2011, 1, 1),
        ).rate_pct == Decimal("18.00")
        assert queries.tax_rule(
            country_code="ES",
            category_key="service.saas_subscription",
            on_date=date(2026, 8, 2),
        ).rate_pct == Decimal("21.00")

    def test_an_inactive_rule_does_not_apply(self, category):
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2020, 1, 1),
            is_active=False,
        )

        assert queries.tax_rule(
            country_code="ES", category_key="service.saas_subscription"
        ).rate_pct == Decimal("21.00")

    def test_an_unknown_country_has_no_rule(self):
        assert (
            queries.tax_rule(country_code="US", category_key="service.generic") is None
        )

    def test_the_most_recent_rule_in_force_wins(self, category):
        """Two rules in force at once: the one that started later wins."""
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("10.00"),
            valid_from=date(2020, 1, 1),
        )
        TaxRule.objects.create(
            category=category,
            country_code="ES",
            rate_pct=Decimal("12.00"),
            valid_from=date(2024, 1, 1),
        )

        assert queries.tax_rule(
            country_code="ES", category_key="service.saas_subscription"
        ).rate_pct == Decimal("12.00")

    def test_lower_case_codes_find_the_rule(self):
        assert (
            queries.tax_rule(
                country_code="es", region_code="ic", category_key="service.generic"
            ).is_subject
            is False
        )


class TestFiscalPolicy:
    def test_it_is_a_singleton_defaulting_to_spain_without_oss(self):
        policy = queries.fiscal_policy()

        assert FiscalPolicy.objects.count() == 1
        assert policy.pk == FiscalPolicy.objects.get().pk
        assert policy.issuer_country == "ES"
        assert policy.oss_registered is False
        assert policy.oss_threshold == Decimal("10000.00")

    def test_saving_a_second_row_overwrites_the_first(self):
        queries.fiscal_policy()
        FiscalPolicy(issuer_country="PT").save()

        assert FiscalPolicy.objects.count() == 1
        assert queries.fiscal_policy().issuer_country == "PT"

    def test_without_a_row_the_defaults_apply_and_nothing_is_written(self):
        """A READ ONLY query (``billing.tax.preview``) reads the policy: it may not create it."""
        FiscalPolicy.objects.all().delete()

        policy = queries.fiscal_policy()

        assert (
            policy.issuer_country,
            policy.intra_eu_reverse_charge,
            policy.oss_registered,
        ) == ("ES", True, False)
        assert FiscalPolicy.objects.count() == 0

    def test_below_the_threshold_the_issuer_rate_applies(self):
        """€10,000 threshold of cross-border B2C sales: below it, Spanish VAT."""
        assert queries.uses_destination_rate(queries.fiscal_policy()) is False

    def test_registering_in_oss_switches_to_destination_rates(self):
        policy = queries.fiscal_policy()
        policy.oss_registered = True
        policy.save()

        assert queries.uses_destination_rate(queries.fiscal_policy()) is True

    def test_the_sale_being_priced_counts_towards_the_threshold(self):
        """The sale that crosses already goes to destination (art. 59c(2))."""
        policy = queries.fiscal_policy()

        assert queries.uses_destination_rate(policy, pending_cents=1_000_001) is True
        assert queries.uses_destination_rate(policy, pending_cents=1_000_000) is False

    def test_pricing_falls_back_to_the_issuer_rate_when_the_threshold_query_fails(
        self, monkeypatch, caplog
    ):
        """Invoicing must not break on this query: a failed total prices at origin and is logged."""

        def _boom(policy, year):
            raise DatabaseError("database went away")

        monkeypatch.setattr(queries.tax, "cross_border_b2c_cents", _boom)

        assert queries.uses_destination_rate(queries.fiscal_policy()) is False
        assert any(
            "[FISCAL]" in r.getMessage() and r.levelname == "ERROR"
            for r in caplog.records
        )

    def test_acting_on_the_regime_must_not_mistake_a_failed_query_for_origin(
        self, monkeypatch
    ):
        """Whoever ACTS on «the year is back to origin» asks the raising variant: an error is not «below»."""

        def _boom(policy, year):
            raise DatabaseError("database went away")

        monkeypatch.setattr(queries.tax, "cross_border_b2c_cents", _boom)

        with pytest.raises(DatabaseError):
            queries.destination_rate_applies(queries.fiscal_policy())

    def _carry(self, year, *, current=0, previous=0):
        policy = queries.fiscal_policy()
        policy.oss_carried_year = year
        policy.oss_carried_current_cents = current
        policy.oss_carried_previous_cents = previous
        policy.save()
        return policy

    def test_the_amount_carried_from_the_old_saas_counts_this_year(self):
        """What the old SaaS sold this year, typed in the admin, counts towards the year's cross-border B2C
        base."""
        year = date.today().year
        policy = self._carry(year, current=1_000_001)

        assert queries.cross_border_b2c_cents(policy, year) == 1_000_001
        assert queries.uses_destination_rate(policy, year=year) is True

    def test_a_previous_year_above_the_threshold_makes_the_whole_year_destination(self):
        year = date.today().year
        policy = self._carry(year, previous=1_200_000)

        assert queries.cross_border_b2c_cents(policy, year - 1) == 1_200_000
        assert queries.uses_destination_rate(policy, year=year) is True

    def test_amounts_carried_for_another_year_are_not_this_years(self):
        year = date.today().year
        policy = self._carry(year - 2, current=5_000_000, previous=5_000_000)

        assert queries.cross_border_b2c_cents(policy, year) == 0
        assert queries.cross_border_b2c_cents(policy, year - 1) == 0

    def test_after_the_carried_year_the_total_is_this_saas_invoices(self):
        """Year rollover: from the carried year on, the old SaaS sells nothing more, so the
        total is known without anybody editing the policy; the carried «this year» becomes «last year»."""
        year = date.today().year
        policy = self._carry(year, current=1_200_000, previous=300_000)

        assert queries.oss_total_is_known(policy, year + 1) is True
        assert queries.oss_total_is_known(policy, year + 5) is True
        assert queries.oss_total_is_known(policy, year - 1) is False
        assert queries.cross_border_b2c_cents(policy, year + 1) == 0
        # Last year (the carried one) closed above the threshold: the whole new year is destination VAT.
        assert queries.destination_rate_applies(policy, year=year + 1) is True

    def test_the_new_years_invoices_count_on_their_own(self):
        year = date.today().year
        policy = self._carry(year - 1, current=0)
        self._invoice(1, net=500_000)

        assert queries.oss_total_is_known(policy, year) is True
        assert queries.cross_border_b2c_cents(policy, year) == 500_000

    def test_without_invoices_nor_carried_amounts_the_total_is_unknown(self):
        """Zero is not a fact until somebody says it: the admin shows «unknown», not 0."""
        year = date.today().year

        assert queries.oss_total_is_known(queries.fiscal_policy(), year) is False
        assert queries.oss_total_is_known(self._carry(year), year) is True

    def _invoice(self, seq, *, country="DE", net=400_000, verified=False, on=None, **fields):
        from billing.models import Invoice

        on = on or date.today()
        values = {
            "stripe_invoice_id": f"in_{seq}",
            "payment_status": "paid",
            "series": "ERP",
            "number": f"ERP-{on.year}-{seq:05d}",
            "sequence": seq,
            "issued_on": on,
            "net_cents": net,
            "tax_cents": 0,
            "total_cents": net,
            "payer_country": country,
            "payer_tax_id_verified": verified,
        }
        values.update(fields)
        return Invoice.objects.create(**values)

    def test_crossing_the_threshold_switches_to_destination_rates(self):
        """Not registered in the OSS, but above the threshold: the obligation is born all the same."""
        for seq in (1, 2, 3):
            self._invoice(seq)
        policy = queries.fiscal_policy()

        assert queries.cross_border_b2c_cents(policy, date.today().year) == 1_200_000
        assert queries.uses_destination_rate(policy) is True

    def test_domestic_and_b2b_sales_do_not_count_towards_the_threshold(self):
        """The threshold is of B2C sales to OTHER member states: a Spanish one, a VIES-verified business
        (reverse charge) and one outside the EU stay out."""
        self._invoice(1, country="ES", net=2_000_000)
        self._invoice(2, country="FR", net=2_000_000, verified=True, payer_tax_id="FR12345678901")
        self._invoice(3, country="US", net=2_000_000)

        assert queries.cross_border_b2c_cents(queries.fiscal_policy(), date.today().year) == 0

    def test_an_unverified_business_was_taxed_as_a_consumer_and_counts(self):
        self._invoice(1, country="FR", payer_tax_id="FR12345678901", verified=False)

        assert queries.cross_border_b2c_cents(queries.fiscal_policy(), date.today().year) == 400_000

    def test_the_invoices_add_to_what_the_old_saas_carried(self):
        year = date.today().year
        policy = self._carry(year, current=700_000)
        self._invoice(1, net=400_000)

        assert queries.cross_border_b2c_cents(policy, year) == 1_100_000
        assert queries.uses_destination_rate(policy, year=year) is True

    def test_only_the_invoices_of_that_year_count(self):
        year = date.today().year
        self._invoice(1, on=date(year - 1, 6, 1))

        assert queries.cross_border_b2c_cents(queries.fiscal_policy(), year) == 0
        assert queries.cross_border_b2c_cents(queries.fiscal_policy(), year - 1) == 400_000

    def test_what_was_not_collected_does_not_count_and_a_credit_note_takes_its_base_back(self):
        from billing.models import Invoice

        original = self._invoice(1)
        Invoice.objects.create(
            stripe_invoice_id="in_open", payment_status="open", net_cents=900_000, total_cents=900_000,
            payer_country="DE",
        )
        self._invoice(
            2, kind="credit_note", rectifies=original, stripe_source_id="cn_1", series="ERPR",
            number=f"ERPR-{date.today().year}-00001", net=-100_000,
        )

        assert queries.cross_border_b2c_cents(queries.fiscal_policy(), date.today().year) == 300_000

