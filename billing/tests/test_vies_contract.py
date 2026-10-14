"""The VIES contract (``architecture/contracts/vies-vat-contract.md`` §10): without a VAT number checked
against VIES there is no reverse charge; when in doubt the VAT is charged.

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_vies_contract.py`` (origin/develop, 34 tests).
Directive 2006/112/EC puts the burden of proof on the issuer, and Stripe applies reverse charge by the
FORMAT of a VAT number (``DE999999999`` came back at 0 € like a real one, saas#1479), so the proof is
ours: a VIES answer with its consultation number.

Every test goes through the door that decides —never by seeding the verdict it then asserts— with only
the network faked (``billing.tests.vies_double``). Adapted: the old door was Stripe's
``checkout.session.completed`` webhook writing an ``Invoice``; in this lot (L2-A) the door is the one
that prices a sale BEFORE it is charged, ``billing.services.sale_quote`` / ``sale_tax_rates`` on the
business's payer, which the L2-B checkout and webhook call. So a refused verdict now means the VAT is
added on top of the net price (121 € charged), and the reconciliation of a sale Stripe already charged
at 0 € (82.64 + 17.36) is proved on ``resolve_vat`` with the door's clearance, as the webhook will use it.

Moved to lot L3-C (they need ``billing.Invoice`` and its PDF): «7. The issued invoice keeps the
consultation number» (3), «The document explains the reconciliation» (4) and the invoice, PDF and
dashboard halves of «The note never lies» (5) and «The note survives OSS» (2).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from billing import queries, services
from billing.models import CompanyConfig, VatCheck
from billing.tests.vies_double import (
    FAKE_VAT,
    MEMBER_STATE_DOWN,
    NOT_REGISTERED,
    REAL_VAT,
    VALID,
    no_network,
    vies_answers,
    vies_is_down,
    vies_says,
)
from billing.vat import resolve_vat
from billing.vies import is_domestic_vat_number

pytestmark = pytest.mark.django_db

PLAN = "service.saas_subscription"
NET = Decimal("100.00")


@pytest.fixture(autouse=True)
def _issuer(issuer_identity):
    return issuer_identity


@pytest.fixture
def german_payer(business_paid_by):
    """A business paid from Berlin; its VAT number is set by each test."""

    def make(vat_number: str):
        return business_paid_by("DE", "10115", tax_id=vat_number)

    return make


def _quote(business):
    return services.sale_quote(business, category_key=PLAN, price=NET)


# --------------------------------------------------------------------------
# 1. A well-formed but nonexistent VAT number is NOT reverse charge
# --------------------------------------------------------------------------


class TestAFakeVatNumberIsNotReverseCharge:
    """The case Stripe lets through: without this test the contract is untested."""

    def test_the_sale_is_not_reverse_charge(self, german_payer):
        with vies_says(**NOT_REGISTERED):
            quote = _quote(german_payer(FAKE_VAT))

        assert quote.treatment != "reverse_charge"

    def test_the_vat_is_charged_on_top_instead_of_left_at_zero(self, german_payer):
        """A Spanish domestic sale at 0 % is not a qualification that exists: below the OSS threshold
        the sale is subject to Spanish VAT, added to the net price before charging."""
        with vies_says(**NOT_REGISTERED):
            business = german_payer(FAKE_VAT)
            quote = _quote(business)
            specs = services.sale_tax_rates(business, category_key=PLAN, price=NET)

        assert (quote.treatment, quote.tax_country, quote.rate) == (
            "domestic",
            "ES",
            Decimal("21.00"),
        )
        assert (quote.base, quote.tax) == (Decimal("100.00"), Decimal("21.00"))
        assert [(spec.country, spec.percentage) for spec in specs] == [
            ("ES", Decimal("21.00"))
        ]

    def test_a_sale_stripe_charged_at_zero_is_reconciled_with_the_doors_verdict(self):
        """What the L2-B webhook does with a sale already charged: Stripe charged 100.00 € with no tax on
        a number never proved, so the collected amount is VAT-inclusive (TJUE C-249/12, Tulică)."""
        with vies_says(**NOT_REGISTERED):
            clearance = services.clear_tax_id_for_stripe(
                FAKE_VAT, customer_country="DE"
            )

        invoice = resolve_vat(
            NET,
            customer_country="DE",
            customer_tax_id=FAKE_VAT,
            customer_tax_id_type="eu_vat",
            customer_tax_id_verified=clearance.verified,
            tax_cents=0,
            tax_included=False,
        )

        assert (invoice.treatment, invoice.tax_country, invoice.rate) == (
            "domestic",
            "ES",
            Decimal("21.00"),
        )
        assert (invoice.base, invoice.tax, invoice.base + invoice.tax) == (
            Decimal("82.64"),
            Decimal("17.36"),
            NET,
        )

    def test_a_real_one_does_get_reverse_charge(self, german_payer):
        """The control: the door must still let the legitimate case through."""
        with vies_says(**VALID):
            quote = _quote(german_payer(REAL_VAT))

        assert quote.treatment == "reverse_charge"
        assert (quote.base, quote.tax) == (Decimal("100.00"), Decimal("0.00"))


# --------------------------------------------------------------------------
# 2. `pending` and `unavailable` behave exactly like `invalid`
# --------------------------------------------------------------------------


class TestNotVerifiedIsNotVerified:
    """VIES goes down often (``MS_UNAVAILABLE``) and that is not «not yet»."""

    def test_an_unavailable_member_state_charges_vat(self, german_payer):
        with vies_says(**MEMBER_STATE_DOWN):
            quote = _quote(german_payer(REAL_VAT))

        assert quote.treatment == "domestic"
        assert quote.tax == Decimal("21.00")

    def test_vies_being_unreachable_charges_vat(self, german_payer):
        with vies_is_down():
            quote = _quote(german_payer(REAL_VAT))

        assert quote.treatment == "domestic"
        assert quote.tax == Decimal("21.00")

    @pytest.mark.parametrize("status", ["pending", "unavailable", "invalid"])
    def test_a_stored_verdict_that_is_not_verified_charges_vat(
        self, german_payer, status
    ):
        """Whatever is on file, only ``verified`` invoices without VAT."""
        VatCheck.objects.create(
            vat_number=REAL_VAT, status=status, consultation_number="WAPIAAAAXstored"
        )

        with vies_says(**NOT_REGISTERED):
            quote = _quote(german_payer(REAL_VAT))

        assert quote.treatment == "domestic"
        assert quote.tax == Decimal("21.00")


# --------------------------------------------------------------------------
# 3. An expired verdict does not block the sale, and the next need asks again
# --------------------------------------------------------------------------


class TestAnExpiredVerdictDoesNotBlockTheSale:
    """A year-old verdict proves nothing about today's operation (§8)."""

    def _stale_verified(self, days=40):
        check = VatCheck.objects.create(
            vat_number=REAL_VAT, status="verified", consultation_number="WAPIAAAAXstale"
        )
        VatCheck.objects.filter(pk=check.pk).update(
            requested_at=timezone.now() - timedelta(days=days)
        )
        return check

    def test_the_sale_is_still_priced_when_vies_cannot_answer(self, german_payer):
        self._stale_verified()

        with vies_is_down():
            quote = _quote(german_payer(REAL_VAT))

        assert quote is not None
        assert quote.base + quote.tax == Decimal("121.00")

    def test_the_next_sale_asks_again(self, german_payer):
        """No queue in this stack (round 11, no ``django.tasks``): the revalidation the old SaaS queued
        is the next need asking the Commission, because only a current proof is reused."""
        self._stale_verified()
        business = german_payer(REAL_VAT)
        with vies_is_down():
            _quote(business)

        with vies_says(**VALID) as post:
            quote = _quote(business)

        post.assert_called_once()
        assert quote.treatment == "reverse_charge"

    def test_an_expired_verdict_no_longer_invoices_without_vat(self, german_payer):
        """``verified`` AND current is the only row of the table that invoices at 0 %."""
        self._stale_verified()

        with vies_is_down():
            assert _quote(german_payer(REAL_VAT)).treatment == "domestic"

    def test_a_fresh_verdict_asks_nobody(self, german_payer):
        """Within the 30 days the verdict is reused: no network on the sale path."""
        VatCheck.objects.create(
            vat_number=REAL_VAT, status="verified", consultation_number="WAPIAAAAXfresh"
        )

        with no_network() as network:
            quote = _quote(german_payer(REAL_VAT))

        network.assert_not_called()
        assert quote.treatment == "reverse_charge"


# --------------------------------------------------------------------------
# 4. The query identifies the requester, and the consultation number is kept
# --------------------------------------------------------------------------


class TestTheQueryIdentifiesTheRequester:
    def test_our_own_vat_number_travels_in_the_query(self):
        with vies_says(**VALID) as post:
            services.check_vat_number(REAL_VAT)

        body = post.call_args.kwargs["json"]
        assert (body["countryCode"], body["vatNumber"]) == ("DE", "812871812")
        assert (body["requesterMemberStateCode"], body["requesterNumber"]) == (
            "ES",
            "B27593136",
        )

    def test_the_consultation_number_is_persisted(self):
        with vies_answers(
            VALID,
            requestIdentifier="WAPIAAAAXproof",
            name="Hetzner",
            address="Industriestr. 25",
        ):
            services.check_vat_number(REAL_VAT)

        stored = VatCheck.objects.get(vat_number=REAL_VAT)
        assert stored.consultation_number == "WAPIAAAAXproof"
        assert stored.status == "verified"
        assert stored.returned_name == "Hetzner"
        assert stored.returned_address == "Industriestr. 25"

    def test_without_a_requester_nothing_is_asked(self):
        """An anonymous query brings back no proof, so it is not made at all."""
        CompanyConfig.objects.all().delete()

        with no_network() as network:
            check = services.check_vat_number(REAL_VAT)

        network.assert_not_called()
        assert check.status == "unavailable"
        assert VatCheck.objects.get(vat_number=REAL_VAT).status == "unavailable"


# --------------------------------------------------------------------------
# 5. The manual override demands a reason and an author, and is recorded
# --------------------------------------------------------------------------


class TestTheManualOverride:
    """For the company incorporated last week that is not in VIES yet (§7)."""

    def test_it_demands_a_reason_and_an_author(self):
        with pytest.raises(ValueError):
            services.record_manual_override(REAL_VAT, by="", reason="Brand new company")
        with pytest.raises(ValueError):
            services.record_manual_override(
                REAL_VAT, by="ioan@erplora.com", reason="  "
            )

    def test_it_is_recorded_with_who_and_why(self):
        services.record_manual_override(
            REAL_VAT,
            by="ioan@erplora.com",
            reason="Incorporated on 2026-08-20, not in VIES yet",
        )

        stored = VatCheck.objects.get(vat_number=REAL_VAT)
        assert stored.status == "verified"
        assert stored.override_by == "ioan@erplora.com"
        assert stored.override_reason == "Incorporated on 2026-08-20, not in VIES yet"
        assert stored.override_at is not None

    def test_an_override_does_invoice_without_vat(self, german_payer):
        services.record_manual_override(
            REAL_VAT, by="ioan@erplora.com", reason="Incorporated on 2026-08-20"
        )

        with no_network() as network:
            quote = _quote(german_payer(REAL_VAT))

        network.assert_not_called()
        assert quote.treatment == "reverse_charge"


# --------------------------------------------------------------------------
# 6. A domestic VAT number is never reverse charge
# --------------------------------------------------------------------------


class TestADomesticVatNumberIsNeverReverseCharge:
    """Even though Stripe types a Spanish NIF as ``eu_vat``, which it does."""

    def test_spanish_vat_is_charged_even_if_valid_in_vies(self):
        result = resolve_vat(
            Decimal("121.00"),
            customer_country="ES",
            customer_tax_id="ESB27593136",
            customer_tax_id_type="eu_vat",
            customer_tax_id_verified=True,
        )

        assert (result.treatment, result.tax_country) == ("domestic", "ES")
        assert (result.rate, result.tax) == (Decimal("21.00"), Decimal("21.00"))

    def test_a_spanish_customer_is_not_even_queried(self):
        """No VIES query for a national customer: there is nothing to prove."""
        with no_network() as network:
            check = services.verify_customer_vat("ESB27593136", customer_country="ES")

        network.assert_not_called()
        assert check is None


# --------------------------------------------------------------------------
# The reconciliation is a fact of the breakdown, and «we could not verify it» is decided
# against the ISSUER's country (the halves of «the note never lies» that need no invoice)
# --------------------------------------------------------------------------


class TestTheBreakdownSealsTheReconciliation:
    def test_the_breakdown_seals_whether_it_reconciled(self):
        """What decides the invoice's note is a fact of the breakdown, not a deduction."""
        charged = resolve_vat(
            Decimal("121.00"),
            customer_country="ES",
            customer_tax_id="ESB12345678",
            customer_tax_id_type="eu_vat",
            tax_cents=2100,
            tax_included=False,
        )
        reconciled = resolve_vat(
            NET,
            customer_country="DE",
            customer_tax_id=FAKE_VAT,
            customer_tax_id_type="eu_vat",
            tax_cents=0,
            tax_included=False,
        )

        assert charged.vat_included_reconciled is False
        assert reconciled.vat_included_reconciled is True

    def test_under_oss_the_sale_is_sealed_in_the_customers_jurisdiction(self):
        """With OSS the jurisdiction is the customer's (DE, 19 %), and the reconciled amounts follow it."""
        policy = queries.fiscal_policy()
        policy.oss_registered = True
        policy.save()

        result = resolve_vat(
            NET,
            customer_country="DE",
            customer_tax_id=FAKE_VAT,
            customer_tax_id_type="eu_vat",
            tax_cents=0,
            tax_included=False,
        )

        assert (result.treatment, result.tax_country) == ("oss", "DE")
        assert result.vat_included_reconciled is True
        assert (result.base, result.tax) == (Decimal("84.03"), Decimal("15.97"))

    def test_whether_a_number_needed_a_verdict_is_decided_against_the_issuer(self):
        """Under OSS ``tax_country`` IS the customer's, so comparing the prefix with it made the note
        vanish on the very sale that needs it (saas#1633); the issuer's country never moves."""
        policy = queries.fiscal_policy()
        policy.oss_registered = True
        policy.save()

        assert is_domestic_vat_number(FAKE_VAT, issuer_country="ES") is False
        assert is_domestic_vat_number("ESB12345678", issuer_country="ES") is True
        assert (
            is_domestic_vat_number(
                "B12345678", customer_country="ES", issuer_country="ES"
            )
            is True
        )
        assert is_domestic_vat_number("12345678", issuer_country="ES") is False
