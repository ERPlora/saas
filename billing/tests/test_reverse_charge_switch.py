"""Invoicing without VAT needs the ROI registration AND the VAT number checked in VIES.

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_reverse_charge_switch.py`` (origin/develop,
9 tests). The path is closed by default and fails closed: when in doubt, the VAT is charged.

Adapted: ``TestTheWebhookAsksVies`` (2) drove Stripe's ``checkout.session.completed`` webhook, which is
lot L2-B; what it proved —the sale door asks the VIES verdict and believes it— is proved here through
that door, ``billing.services.sale_tax_rates``, which the L2-B checkout and webhook call. Its third class,
``TestTheInvoiceKeepsTheEvidence`` (1), is ``test_invoice_recording.TestTheVatOfEachSale`` (lot L3-C).
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from billing import queries, services
from billing.models import VatCheck
from billing.vat import resolve_vat

pytestmark = pytest.mark.django_db

PLAN = "service.saas_subscription"


def _resolve(total, **kwargs):
    return resolve_vat(Decimal(total), **kwargs)


def _french_business(**extra):
    return {
        "customer_country": "FR",
        "customer_tax_id": "FR12345678901",
        "customer_tax_id_type": "eu_vat",
        **extra,
    }


def _switch_reverse_charge(on: bool):
    policy = queries.fiscal_policy()
    policy.intra_eu_reverse_charge = on
    policy.save()
    return policy


class TestTheSwitch:
    def test_it_is_on_because_the_roi_registration_is_granted(self):
        """ERPlora is in the ROI since 08-08-2026 (ESB27593136) (saas#1479)."""
        assert queries.fiscal_policy().intra_eu_reverse_charge is True

    def test_off_means_a_french_business_pays_spanish_vat(self):
        _switch_reverse_charge(False)

        result = _resolve("121.00", **_french_business(customer_tax_id_verified=True))

        assert result.treatment == "domestic"
        assert result.rate == Decimal("21.00")
        assert result.tax == Decimal("21.00")
        assert result.tax_country == "ES"

    def test_on_and_verified_means_reverse_charge(self):
        _switch_reverse_charge(True)

        result = _resolve("100.00", **_french_business(customer_tax_id_verified=True))

        assert result.treatment == "reverse_charge"
        assert result.tax == Decimal("0.00")
        assert result.base == Decimal("100.00")


class TestItFailsClosed:
    def test_an_unverified_vat_id_still_pays_spanish_vat(self):
        _switch_reverse_charge(True)

        result = _resolve("121.00", **_french_business(customer_tax_id_verified=False))

        assert result.treatment == "domestic"
        assert result.tax == Decimal("21.00")

    def test_not_saying_anything_counts_as_unverified(self):
        """The parameter's default cannot be «I trust it»."""
        _switch_reverse_charge(True)

        assert _resolve("121.00", **_french_business()).treatment == "domestic"

    def test_a_spanish_business_is_never_reverse_charge(self):
        """Even though Stripe types its NIF as ``eu_vat``, which it does."""
        _switch_reverse_charge(True)

        result = _resolve(
            "121.00",
            customer_country="ES",
            customer_tax_id="B27593136",
            customer_tax_id_type="eu_vat",
            customer_tax_id_verified=True,
        )

        assert result.treatment == "domestic"
        assert result.tax == Decimal("21.00")


class TestTheSaleDoorAsksVies:
    """The switch is worth nothing if the door that prices a sale does not ask the verdict."""

    def _run(self, business, verified: bool):
        check = VatCheck(
            vat_number="FR12345678901",
            status=VatCheck.VERIFIED if verified else VatCheck.INVALID,
            consultation_number="WAPIAAAAXswitch",
        )
        with patch("billing.services.verify_customer_vat", return_value=check) as asked:
            specs = services.sale_tax_rates(
                business, category_key=PLAN, price=Decimal("100.00")
            )
        return specs, asked

    def test_a_verified_business_gets_reverse_charge(self, business_paid_by):
        _switch_reverse_charge(True)
        business = business_paid_by("FR", "75001", tax_id="FR12345678901")

        specs, asked = self._run(business, verified=True)

        asked.assert_called_once()
        assert (asked.call_args.args, asked.call_args.kwargs["customer_country"]) == (("FR12345678901",), "FR")
        assert specs == [], "reverse charge: nothing on top of the net price"

    def test_an_unverified_vat_number_pays_spanish_vat(self, business_paid_by):
        _switch_reverse_charge(True)
        business = business_paid_by("FR", "75001", tax_id="FR12345678901")

        specs, _ = self._run(business, verified=False)

        assert [(spec.country, spec.percentage) for spec in specs] == [
            ("ES", Decimal("21.00"))
        ]
