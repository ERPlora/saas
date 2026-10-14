"""Every country the forms offer has to be sellable with the seeded table (saas#2110).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_every_billing_country_resolves.py``
(origin/develop, 5 tests). The form's list and the table that prices the sale were two lists nobody kept
in step: a country added to a form without its rule fails here, before it refuses a customer's checkout.

Adapted: the lists are ``billing.vat.BILLING_COUNTRIES`` and the countries a business may be created in
(``hubs.schemas.COUNTRIES``). The old ``test_a_uk_payer_on_file_keeps_the_audit_green`` drove the
tax-rule audit (``audit_tax_rules``), which is not ported in this lot; its fact —a UK payer on file
prices— is the first test of ``TestUnitedKingdom`` through the sale door.
"""

from decimal import Decimal

import pytest

from billing import queries, services
from billing.vat import BILLING_COUNTRIES, NOT_SUBJECT, quote_vat

pytestmark = pytest.mark.django_db

PLAN = "service.saas_subscription"


def _quote(country: str, postal_code: str = "", **kwargs):
    """A Spanish sale is priced with its 5-digit postal code (Madrid by default): without it the place is
    unknown and the sale is not priced (review of L2-A, finding 1)."""
    postal_code = postal_code or ("28001" if country == "ES" else "")
    return quote_vat(
        Decimal("100.00"),
        customer_country=country,
        customer_postal_code=postal_code,
        category_key=PLAN,
        **kwargs,
    )


def test_every_country_the_billing_form_offers_resolves_a_rate():
    assert [country for country in BILLING_COUNTRIES if _quote(country) is None] == []


def test_every_country_a_business_may_be_created_in_resolves_a_rate():
    from hubs.schemas import COUNTRIES

    assert sorted(country for country in COUNTRIES if _quote(country) is None) == []


class TestUnitedKingdom:
    """Post-Brexit the UK is a third country: a service supplied there from Spain is outside the scope
    of Spanish VAT (art. 69.Uno.1º LIVA for a business, art. 69.Dos for a private customer). Net price,
    no tax, declared not subject (N2), like the Canary Islands."""

    def test_a_uk_business_on_file_is_sold_at_the_net_price(self, business_paid_by):
        uk = business_paid_by("GB", "SW1A 1AA", tax_id="GB123456789")

        quote = services.sale_quote(uk, category_key=PLAN, price=Decimal("100.00"))

        assert quote.treatment == NOT_SUBJECT
        assert (quote.base, quote.tax) == (Decimal("100.00"), Decimal("0.00"))
        assert (
            services.sale_tax_rates(uk, category_key=PLAN, price=Decimal("100.00"))
            == []
        )

    def test_a_uk_consumer_is_not_sold_to(self, business_paid_by):
        """A UK consumer owes 20 % UK VAT that only a supplier registered with HMRC may charge, so the
        terms sell to UK businesses only: without the payer's UK VAT number the sale is refused (saas#2205)."""
        from live.errors import Conflict

        consumer = business_paid_by("GB", "SW1A 1AA")

        with pytest.raises(Conflict) as refused:
            services.sale_tax_rates(consumer, category_key=PLAN, price=Decimal("100.00"))

        assert refused.value.code == "billing.uk_business_required"
        assert services.sale_tax_rates(consumer, category_key=PLAN, price=Decimal("0.00")) == []

    def test_a_uk_payer_is_not_subject(self):
        quote = _quote("GB", "SW1A 1AA")

        assert quote is not None
        assert quote.treatment == NOT_SUBJECT
        assert quote.tax == Decimal("0.00")
        assert quote.base == Decimal("100.00")

    def test_a_uk_business_with_its_vat_number_is_not_subject_either(self):
        """A GB VAT number is not an EU one: it never takes the intra-EU reverse charge."""
        quote = _quote(
            "GB",
            "SW1A 1AA",
            customer_tax_id="GB123456789",
            customer_tax_id_type="gb_vat",
            customer_tax_id_verified=True,
        )

        assert quote is not None
        assert quote.treatment == NOT_SUBJECT
        assert quote.tax == Decimal("0.00")

    def test_the_rule_is_in_the_table_not_in_a_backstop(self):
        """Editable in the admin and schedulable, like every other territory we sell to."""
        rule = queries.tax_rule(
            country_code="GB", region_code="", category_key="service.generic"
        )

        assert rule is not None
        assert rule.is_subject is False
