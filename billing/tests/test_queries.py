"""``billing.tax.preview``: what a sale to this payer will carry, before anything is charged.

A query (READ ONLY): it never asks VIES nor writes a row, it reads the verdict on file —the one
``billing.vat_check.run`` just logged— and the rule table. The create-business and billing-profile forms
use it to say «€29.99 + 21 % VAT — €36.29» or «reverse charge: no VAT» before the payment, with the
same ``quote_vat`` the checkout will use, so what is announced is what is charged.
"""

from decimal import Decimal

import pytest
from django.test import Client
from live.errors import PermissionDenied

from billing import queries
from billing.models import VatCheck
from billing.schemas import TaxPreviewIn
from billing.tests.conftest import ctx_for
from billing.tests.vies_double import no_network

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
URL = "/api/billing/tax-preview"


def _preview(user, **params):
    return queries.tax_preview(ctx_for(user), TaxPreviewIn(**params)).model_dump()


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
        """«3500» is Benidorm without its leading 0, not Las Palmas: no 0 % by a guess (finding 1)."""
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
