"""A silent zero from Stripe does not make a subject sale VAT-free (saas#1478).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_vat_b2c_eu_no_registration.py``
(origin/develop, 13 tests). The zero measured in saas#1478 comes back as ``not_collecting``: below the
€10,000 EU threshold that sale owes Spanish VAT, so a 0 % invoice is a misconfiguration leaking
through. There is no zero we accept on a sale we qualified as subject: the amount collected is
treated as VAT-included (TJUE *Tulică* C-249/12 and C-250/12; art. 78.Cuatro LIVA) and the discrepancy
is reported as a structured ERROR.
"""

from decimal import Decimal

import pytest

from billing import queries
from billing.vat import resolve_vat

pytestmark = pytest.mark.django_db

DISCREPANCY_EVENT = "fiscal.vat.stripe_charged_no_tax_on_subject_sale"


def _resolve(total, **kwargs):
    return resolve_vat(Decimal(total), tax_included=False, **kwargs)


def _german_consumer(**extra):
    """The customer measured in saas#1478: Berlin, no VAT id, Stripe charged 0."""
    return {
        "customer_country": "DE",
        "customer_postal_code": "10115",
        "tax_cents": 0,
        **extra,
    }


def _alerts(caplog):
    return [r for r in caplog.records if getattr(r, "event", "") == DISCREPANCY_EVENT]


class TestAnUnexplainedZeroIsReconciled:
    def test_an_eu_consumer_below_the_threshold_is_invoiced_with_spanish_vat(self):
        """The exact row of saas#1478: €29.99 to a Berlin consumer at 0 %."""
        vat = _resolve("29.99", **_german_consumer())

        assert vat.treatment == "domestic"
        assert vat.tax_country == "ES"
        assert vat.rate == Decimal("21.00")
        assert vat.tax == Decimal("5.20")
        assert vat.base == Decimal("24.79")
        # Sealed for the invoice's note (saas#1479).
        assert vat.vat_included_reconciled is True

    def test_the_total_collected_is_never_altered(self):
        for gross in ["29.99", "54.99", "109.99", "419.99", "0.01"]:
            vat = _resolve(gross, **_german_consumer())

            assert vat.base + vat.tax == Decimal(gross), gross

    def test_a_spanish_consumer_with_no_tax_charged_is_reconciled_too(self):
        vat = _resolve("121.00", customer_country="ES", tax_cents=0)

        assert vat.rate == Decimal("21.00")
        assert vat.tax == Decimal("21.00")
        assert vat.base == Decimal("100.00")

    def test_the_discrepancy_is_reported_as_a_structured_error(self, caplog):
        """A leak nobody can alert on is a leak nobody fixes."""
        with caplog.at_level("ERROR", logger="billing.vat"):
            _resolve("29.99", **_german_consumer())

        record = next(iter(_alerts(caplog)))
        assert record.levelname == "ERROR"
        assert record.customer_country == "DE"
        assert record.treatment == "domestic"
        assert record.expected_rate == "21.00"
        assert record.reconciled is True


class TestNoZeroIsExplainedAway:
    """A VAT id does not buy an exemption by itself: what buys it is the VIES verdict."""

    def _french_business(self, **extra):
        return {
            "customer_country": "FR",
            "customer_tax_id": "FR12345678901",
            "customer_tax_id_type": "eu_vat",
            "tax_cents": 0,
            **extra,
        }

    def test_an_unverified_vat_id_is_reconciled_at_the_spanish_rate(self):
        vat = _resolve("100.00", **self._french_business())

        assert vat.treatment == "domestic"
        assert vat.rate == Decimal("21.00")
        assert vat.base == Decimal("82.64")
        assert vat.tax == Decimal("17.36")

    def test_a_verified_vat_id_is_a_real_reverse_charge_and_raises_no_alert(
        self, caplog
    ):
        with caplog.at_level("ERROR", logger="billing.vat"):
            vat = _resolve(
                "100.00", **self._french_business(customer_tax_id_verified=True)
            )

        assert vat.treatment == "reverse_charge"
        assert vat.tax == Decimal("0.00")
        assert vat.base == Decimal("100.00")
        assert vat.vat_included_reconciled is False
        assert not _alerts(caplog)

    def test_it_is_reported_as_reconciled(self, caplog):
        with caplog.at_level("ERROR", logger="billing.vat"):
            _resolve("100.00", **self._french_business())

        record = next(iter(_alerts(caplog)))
        assert record.reconciled is True
        assert record.customer_country == "FR"


class TestNothingElseMoves:
    def test_a_quota_from_stripe_still_wins(self):
        vat = _resolve("121.00", customer_country="ES", tax_cents=2100)

        assert vat.base == Decimal("100.00")
        assert vat.tax == Decimal("21.00")

    def test_a_reverse_charged_sale_carries_no_quota(self):
        policy = queries.fiscal_policy()
        policy.intra_eu_reverse_charge = True
        policy.save()

        vat = _resolve(
            "100.00",
            customer_country="FR",
            customer_tax_id="FR12345678901",
            customer_tax_id_type="eu_vat",
            customer_tax_id_verified=True,
            tax_cents=0,
        )

        assert vat.treatment == "reverse_charge"
        assert vat.tax == Decimal("0.00")

    def test_a_third_country_carries_no_quota_and_raises_no_alert(self, caplog):
        with caplog.at_level("ERROR", logger="billing.vat"):
            vat = _resolve(
                "29.99",
                customer_country="US",
                customer_postal_code="10001",
                tax_cents=0,
            )

        assert vat.treatment == "not_subject"
        assert vat.tax == Decimal("0.00")
        assert vat.base == Decimal("29.99")
        assert vat.tax_country == ""
        assert vat.vat_included_reconciled is False
        assert not _alerts(caplog)

    def test_an_excluded_territory_raises_no_alert_either(self, caplog):
        with caplog.at_level("ERROR", logger="billing.vat"):
            _resolve(
                "100.00",
                customer_country="ES",
                customer_postal_code="35001",
                tax_cents=0,
            )

        assert not _alerts(caplog)

    def test_an_excluded_territory_carries_no_quota(self):
        vat = _resolve(
            "100.00", customer_country="ES", customer_postal_code="35001", tax_cents=0
        )

        assert vat.treatment == "not_subject"
        assert vat.tax == Decimal("0.00")
        assert vat.base == Decimal("100.00")

    def test_a_gross_price_is_split_as_always(self):
        vat = resolve_vat(Decimal("121.00"), customer_country="ES", tax_cents=0)

        assert vat.base == Decimal("100.00")
        assert vat.tax == Decimal("21.00")
