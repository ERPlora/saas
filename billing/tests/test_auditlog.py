"""ACCOUNTS-F36 · The audit trail of the billing models (django-auditlog; PLAN-SAAS §1.1: «en los modelos de cuenta,
cobro y fiscal»).

Ported from ERPlora/saas ``apps/dashboard/billing/auditlog.py`` and ``tests/unit/test_auditlog_coverage.py`` (#970):
who changed what ERPlora charges and how (the VAT rules, ERPlora's company data, the promo codes) and what Stripe did
to a business's money (a checkout, an unpaid renewal, an invoice and its VeriFactu state, a downgrade waiting), with
only the logged fields serialized (#957). Changed: the old one had ``Subscription``, ``Payout`` and
``StripeConnectAccount`` here; the subscription is ``hubs``' now (``hubs/tests/test_auditlog.py``) and there is no
marketplace. Never written: a Stripe credential (an Embedded Checkout's client secret), the links that open a Stripe
invoice to whoever holds them, and the fields that move by themselves (a counter, the VeriFactu sending queue, an
``updated_at``).
"""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from billing.models import (
    CheckoutAttempt,
    CompanyConfig,
    FiscalPolicy,
    Invoice,
    InvoiceCounter,
    InvoiceLine,
    OssNotice,
    PaymentFailure,
    PlanChangeSchedule,
    PromoCode,
    PromoRedemption,
    TaxCategory,
    TaxRule,
    VatCheck,
    WebhookEvent,
)

pytestmark = pytest.mark.django_db

AUDITED = {
    TaxCategory,
    TaxRule,
    FiscalPolicy,
    CompanyConfig,
    PromoCode,
    PromoRedemption,
    CheckoutAttempt,
    PaymentFailure,
    Invoice,
    InvoiceLine,
    PlanChangeSchedule,
}

# Left out, each with its reason: a log, a queue or a counter of its own, never a change somebody makes.
NOT_AUDITED = {
    VatCheck: "the log of the VIES queries itself: every query, a manual override too, is a new row never edited",
    WebhookEvent: "the queue of Stripe's deliveries (a claim, its lease, its attempts), pruned by purge_webhook_events",
    InvoiceCounter: "a counter that moves with every invoice issued",
    OssNotice: "the once-a-year dedupe of a notice to the team's mailbox and the queue of its mail",
}

SECRET = "cs_test_secret_never_logged"
STRIPE_LINK = "https://invoice.stripe.com/i/acct_never_logged"


def _entries_for(instance):
    return LogEntry.objects.get_for_object(instance)


def _fields_written(entry) -> set[str]:
    """The fields an entry keeps: what changed and its serialized copy of the row."""
    return set(entry.changes_dict) | set(entry.serialized_data["fields"])


def _everything_written(instance) -> str:
    return " ".join(
        f"{entry.object_repr} {entry.changes} {entry.changes_text} {entry.serialized_data}"
        for entry in _entries_for(instance)
    )


def _invoice(sequence: int = 1, **fields) -> Invoice:
    return Invoice.objects.create(
        **{
            "stripe_invoice_id": f"in_audit_{sequence}",
            "business_name": "Panadería López",
            "payment_status": "paid",
            "series": "ERP",
            "sequence": sequence,
            "number": f"ERP-2026-{sequence:05d}",
            "issued_on": date(2026, 10, 1),
            "net_cents": 2999,
            "tax_cents": 630,
            "total_cents": 3629,
            "payer_name": "Panadería López SL",
            "hosted_invoice_url": STRIPE_LINK,
            **fields,
        }
    )


class TestWhatIsAudited:
    def test_every_billing_model_is_audited_or_left_out_with_its_reason(self):
        """A new billing model has to choose: registered, or here with why not."""
        billing_models = set(apps.get_app_config("billing").get_models())

        assert billing_models == AUDITED | set(NOT_AUDITED)
        assert {model for model in billing_models if auditlog.contains(model)} == AUDITED

    def test_every_registration_serializes_only_the_logged_fields(self):
        """#957: without ``serialize_auditlog_fields_only`` the serialized copy carries the excluded fields."""
        for model in AUDITED:
            assert auditlog.get_serialize_options(model)["serialize_auditlog_fields_only"] is True, model


class TestWhatIsWritten:
    def test_a_vat_rule_changed_by_the_staff_is_logged_with_its_rate(self):
        category = TaxCategory.objects.create(key="service.audit_test", name="Audit test")
        rule = TaxRule.objects.create(category=category, country_code="ES", rate_pct=Decimal("21.00"), valid_from=date(2026, 1, 1))

        rule.rate_pct = Decimal("23.00")
        rule.save()

        entry = _entries_for(rule).get(action=LogEntry.Action.UPDATE)
        assert entry.changes_dict["rate_pct"] == ["21.00", "23.00"]
        assert "updated_at" not in _fields_written(entry)
        assert "updated_at" not in _fields_written(_entries_for(category).get())

    def test_the_company_data_on_the_invoices_is_logged(self, issuer_identity):
        issuer_identity.legal_name = "ERPlora Solutions SL"
        issuer_identity.save()

        entry = _entries_for(issuer_identity).filter(action=LogEntry.Action.UPDATE).latest("timestamp")
        assert entry.changes_dict["legal_name"][1] == "ERPlora Solutions SL"
        assert "updated_at" not in _fields_written(entry)

    def test_the_fiscal_policy_is_logged_and_its_oss_accumulators_are_not(self):
        policy = FiscalPolicy.objects.first() or FiscalPolicy.objects.create()
        policy.intra_eu_reverse_charge = not policy.intra_eu_reverse_charge
        policy.save()
        logged = _entries_for(policy).count()

        policy.oss_carried_current_cents += 10_000
        policy.save()

        entry = _entries_for(policy).latest("timestamp")
        assert "intra_eu_reverse_charge" in entry.changes_dict
        assert _entries_for(policy).count() == logged
        moving = {"oss_carried_year", "oss_carried_current_cents", "oss_carried_previous_cents", "updated_at"}
        assert not moving & _fields_written(entry)

    def test_a_promo_code_is_logged_and_its_redemption_count_is_not(self, shop):
        promo = PromoCode.objects.create(code="audit_2026", trial_days=30)

        promo.redemption_count = 1
        promo.save()
        redemption = PromoRedemption.objects.create(promo=promo, hub=shop, stripe_customer_id="cus_1", stripe_session_id="cs_1")

        assert list(_entries_for(promo).values_list("action", flat=True)) == [LogEntry.Action.CREATE]
        assert not {"redemption_count", "updated_at"} & _fields_written(_entries_for(promo).get())
        assert _entries_for(redemption).get().changes_dict["hub"][1] == str(shop.pk)

    def test_a_checkout_is_logged_without_its_client_secret(self, shop):
        attempt = CheckoutAttempt.objects.create(
            hub=shop, kind="plan", plan_slug="starter", selection="x", stripe_session_id="cs_test_1", client_secret=SECRET
        )

        attempt.status = CheckoutAttempt.Status.COMPLETED
        attempt.save()

        entry = _entries_for(attempt).get(action=LogEntry.Action.UPDATE)
        assert entry.changes_dict["status"] == ["open", "completed"]
        assert not {"client_secret", "updated_at"} & _fields_written(_entries_for(attempt).get(action=LogEntry.Action.CREATE))
        assert SECRET not in _everything_written(attempt)

    def test_an_unpaid_renewal_is_logged_without_the_link_to_its_stripe_invoice(self, shop):
        failure = PaymentFailure.objects.create(
            hub=shop,
            stripe_invoice_id="in_audit_1",
            reason="card_declined",
            invoice_created_at=timezone.now(),
            hosted_invoice_url=STRIPE_LINK,
        )

        failure.resolved_at = timezone.now()
        failure.save()

        assert "resolved_at" in _entries_for(failure).get(action=LogEntry.Action.UPDATE).changes_dict
        assert "hosted_invoice_url" not in _fields_written(_entries_for(failure).get(action=LogEntry.Action.CREATE))
        assert STRIPE_LINK not in _everything_written(failure)

    def test_an_invoice_and_its_verifactu_state_are_logged_and_its_sending_queue_is_not(self):
        invoice = _invoice(fiscal_status="issuing")
        line = InvoiceLine.objects.create(
            invoice=invoice, position=1, description="1 × Starter", net_cents=2999, tax_cents=630, total_cents=3629
        )

        invoice.post_attempts, invoice.next_post_at, invoice.last_post_error = 1, timezone.now(), "timeout"
        invoice.save()
        queued = _entries_for(invoice).count()
        invoice.fiscal_status = "accepted"
        invoice.save()

        assert queued == 1
        entry = _entries_for(invoice).get(action=LogEntry.Action.UPDATE)
        assert entry.changes_dict["fiscal_status"] == ["issuing", "accepted"]
        moving = {"hosted_invoice_url", "post_attempts", "next_post_at", "last_post_error", "updated_at"}
        assert not moving & _fields_written(_entries_for(invoice).get(action=LogEntry.Action.CREATE))
        assert not moving & _fields_written(entry)
        assert STRIPE_LINK not in _everything_written(invoice)
        assert _entries_for(line).get().changes_dict["description"][1] == "1 × Starter"

    def test_a_downgrade_waiting_in_stripe_is_logged(self, shop):
        schedule = PlanChangeSchedule.objects.create(
            hub=shop, stripe_schedule_id="sub_sched_1", plan_slug="starter", interval="month", starts_at=timezone.now()
        )

        pk = schedule.pk  # delete() empties it
        schedule.delete()

        entries = LogEntry.objects.get_for_model(PlanChangeSchedule).filter(object_pk=str(pk))
        assert list(entries.values_list("action", flat=True)) == [LogEntry.Action.DELETE, LogEntry.Action.CREATE]


class TestAFiscalRecordIsOnlyRead:
    def test_logging_an_invoice_writes_only_the_log_entry(self):
        """A record sent to the AEAT is never modified (CLAUDE.md, Fiscal): the trail reads the invoice and writes its
        own table, nothing else."""
        invoice = _invoice(fiscal_status="issuing")
        invoice.fiscal_status = "accepted"

        with CaptureQueriesContext(connection) as queries:
            invoice.save()

        writes = [query["sql"].split()[:3] for query in queries if query["sql"].split()[0] in {"INSERT", "UPDATE", "DELETE"}]
        # The entry is written on pre_save, before the invoice's own UPDATE.
        assert sorted(writes) == [["INSERT", "INTO", '"auditlog_logentry"'], ["UPDATE", '"billing_invoice"', "SET"]]


class TestThePruning:
    def test_cleanup_old_logs_prunes_the_billing_entries_too(self):
        """The same table as the account's: ``cleanup_old_logs`` keeps 90 days of these as well (ACCOUNTS-F37)."""
        old, recent = _invoice(1), _invoice(2)
        _entries_for(old).update(timestamp=timezone.now() - timedelta(days=91))

        call_command("cleanup_old_logs", stdout=StringIO())

        assert (_entries_for(old).exists(), _entries_for(recent).exists()) == (False, True)
