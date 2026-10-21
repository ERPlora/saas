"""The team's notices of the OSS threshold (BILLING-F06, saas#2297, saas#2299).

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_oss_threshold_warning.py``,
``test_oss_crossing_alert.py`` and ``test_oss_regime_change_trail.py`` (origin/develop). Destination VAT
switches on by itself when the year's cross-border B2C sales pass the threshold, but registering in the OSS
(form 035) is paperwork that takes days: the team's mailbox (``SUPPORT_EMAIL``) is told when a charged sale
takes the year past 80 % of the threshold, and again when one crosses it (or at the first charged sale of a
year that starts in destination because the previous one closed above). Each notice once per year and kind:
the row is the dedupe, persistent on purpose. The mail leaves after the COMMIT; one that could not leave is
sent again by the daily ``retax_subscriptions``.

Adapted: one model (``billing.OssNotice``, kind ``near`` or ``crossed``) instead of two; the hook is the paid
invoice of this SaaS (``_record_paid``), not a ``post_save`` signal.
"""

import logging
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from billing import emails
from billing.models import FiscalPolicy, Invoice, OssNotice
from billing.tests.test_invoice_recording import deliver, paid, payer, running  # noqa: F401 - fixtures
from billing.tests.stripe_double import invoice_line, subscription

pytestmark = pytest.mark.django_db

YEAR = timezone.localdate().year
#: Each charged sale of the tests is one plan line of 29.99 € net: 2999 cents towards the threshold.
SALE = 2999


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    stripe_double.answer("subscriptions.retrieve", subscription())
    return stripe_double


@pytest.fixture
def berlin(running, settings):
    """A consumer in Berlin pays the business; the threshold is 100 € (10 000 cents) and the old SaaS left
    ``carried`` cents this year (``FiscalPolicy``, as the admin loads them)."""
    settings.SUPPORT_EMAIL = "team@example.com"
    payer(running, billing_country="DE", billing_postal_code="10115")
    FiscalPolicy.objects.update(
        oss_threshold=Decimal("100.00"),
        oss_carried_year=YEAR,
        oss_carried_current_cents=0,
        oss_carried_previous_cents=0,
    )
    return running


def carried(this_year: int = 0, last_year: int = 0) -> None:
    FiscalPolicy.objects.update(oss_carried_current_cents=this_year, oss_carried_previous_cents=last_year)


def charge(invoice_id: str, *, commit=None) -> Invoice:
    if commit is not None:
        with commit(execute=True):
            deliver(paid(invoice_id))
    else:
        deliver(paid(invoice_id))
    return Invoice.objects.get(stripe_invoice_id=invoice_id)


def notices(**filters) -> list[OssNotice]:
    return list(OssNotice.objects.filter(**filters).order_by("recorded_at"))


def oss_mails(mailoutbox) -> list:
    return [mail for mail in mailoutbox if mail.extra_headers.get("X-ERPlora-Notice", "").startswith("billing.oss_")]


class TestEightyPercent:
    def test_the_charge_that_passes_80_percent_tells_the_team_once(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks, caplog
    ):
        carried(this_year=5100)

        with caplog.at_level(logging.WARNING, logger="billing.services"):
            sale = charge("in_near", commit=django_capture_on_commit_callbacks)

        [notice] = notices()
        assert (notice.year, notice.kind, notice.invoice_id) == (YEAR, OssNotice.Kind.NEAR, sale.pk)
        assert (notice.accumulated_cents, notice.threshold_cents) == (5100 + SALE, 10_000)
        assert notice.mailed_at is not None
        [mail] = oss_mails(mailoutbox)
        assert mail.to == ["team@example.com"]
        assert mail.extra_headers["X-ERPlora-Notice"] == "billing.oss_near"
        assert sale.number in mail.body
        assert "80 %" in mail.subject
        assert any(getattr(r, "event", "") == "billing.oss_near" for r in caplog.records)

    def test_the_mail_waits_for_the_commit(self, berlin, mailoutbox, django_capture_on_commit_callbacks):
        carried(this_year=5100)

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            deliver(paid("in_near"))
        assert oss_mails(mailoutbox) == []
        for callback in callbacks:
            callback()

        assert len(oss_mails(mailoutbox)) == 1

    def test_reaching_exactly_80_percent_tells_nothing(self, berlin, mailoutbox, django_capture_on_commit_callbacks):
        carried(this_year=8000 - SALE)

        charge("in_exact", commit=django_capture_on_commit_callbacks)

        assert notices() == []
        assert oss_mails(mailoutbox) == []

    def test_later_sales_of_the_year_tell_nothing_more(self, berlin, mailoutbox, django_capture_on_commit_callbacks):
        # A threshold of 200 €: the first sale passes 80 % (160.99 €), the second stays under it (190.98 €).
        FiscalPolicy.objects.update(oss_threshold=Decimal("200.00"))
        carried(this_year=13_100)
        first = charge("in_1", commit=django_capture_on_commit_callbacks)
        charge("in_2", commit=django_capture_on_commit_callbacks)

        assert [n.invoice_id for n in notices(kind=OssNotice.Kind.NEAR)] == [first.pk]
        assert len(oss_mails(mailoutbox)) == 1

    def test_the_threshold_in_force_is_the_one_recorded(self, berlin, mailoutbox, django_capture_on_commit_callbacks):
        FiscalPolicy.objects.update(oss_threshold=Decimal("50.00"))
        carried(this_year=1100)

        charge("in_near", commit=django_capture_on_commit_callbacks)

        assert notices()[0].threshold_cents == 5000


class TestTheCrossing:
    def test_a_single_sale_that_jumps_past_the_threshold_tells_the_crossing_only(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        carried(this_year=7100)

        sale = charge("in_cross", commit=django_capture_on_commit_callbacks)

        [notice] = notices()
        assert (notice.kind, notice.reason) == (OssNotice.Kind.CROSSED, OssNotice.Reason.CURRENT_YEAR)
        assert (notice.accumulated_cents, notice.effective_from) == (7100 + SALE, sale.issued_on)
        [mail] = oss_mails(mailoutbox)
        assert mail.extra_headers["X-ERPlora-Notice"] == "billing.oss_crossed"
        assert sale.number in mail.body
        assert "100.99" in mail.body and "100.00" in mail.body

    def test_after_the_80_percent_warning_the_crossing_is_told_too(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        carried(this_year=5100)
        charge("in_1", commit=django_capture_on_commit_callbacks)
        crossing = charge("in_2", commit=django_capture_on_commit_callbacks)

        assert [n.kind for n in notices()] == [OssNotice.Kind.NEAR, OssNotice.Kind.CROSSED]
        assert len(oss_mails(mailoutbox)) == 2
        assert crossing.number in oss_mails(mailoutbox)[1].body

    def test_reaching_exactly_the_threshold_is_only_the_80_percent_warning(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        """Destination VAT starts once the threshold is passed (``queries.destination_rate_applies``), so landing
        on it is not the crossing yet."""
        carried(this_year=10_000 - SALE)

        charge("in_exact", commit=django_capture_on_commit_callbacks)

        assert [n.kind for n in notices()] == [OssNotice.Kind.NEAR]
        assert [m.extra_headers["X-ERPlora-Notice"] for m in oss_mails(mailoutbox)] == ["billing.oss_near"]

    def test_a_previous_year_that_closed_exactly_at_the_threshold_is_not_a_crossing(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        carried(last_year=10_000)

        charge("in_first", commit=django_capture_on_commit_callbacks)

        assert notices() == []
        assert oss_mails(mailoutbox) == []

    def test_a_year_that_starts_in_destination_is_told_at_its_first_charged_sale(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        carried(last_year=12_000)

        first = charge("in_first", commit=django_capture_on_commit_callbacks)

        [notice] = notices()
        assert (notice.kind, notice.reason, notice.invoice_id) == (
            OssNotice.Kind.CROSSED,
            OssNotice.Reason.PREVIOUS_YEAR,
            first.pk,
        )
        assert (notice.accumulated_cents, notice.effective_from) == (12_000, date(YEAR, 1, 1))
        assert str(YEAR - 1) in oss_mails(mailoutbox)[0].body

    def test_later_sales_above_the_threshold_tell_nothing_more(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        carried(this_year=7100)
        crossing = charge("in_1", commit=django_capture_on_commit_callbacks)
        charge("in_2", commit=django_capture_on_commit_callbacks)

        assert [n.invoice_id for n in notices()] == [crossing.pk]
        assert len(oss_mails(mailoutbox)) == 1

    def test_a_charge_that_lost_the_race_tells_nothing(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks, monkeypatch, caplog
    ):
        """Two charges at once: the other wrote the year's row first (the unique constraint), so this one
        neither writes nor mails."""
        from billing import services

        carried(this_year=7100)
        winner = charge("in_winner", commit=django_capture_on_commit_callbacks)
        mailoutbox.clear()
        real = services._oss_noticed
        # The loser read «not crossed yet» before the winner committed; the 80 % check sees the crossing.
        monkeypatch.setattr(
            services, "_oss_noticed", lambda year, kinds: False if list(kinds) == [OssNotice.Kind.CROSSED] else real(year, kinds)
        )

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="billing.services"):
            charge("in_loser", commit=django_capture_on_commit_callbacks)

        assert [n.invoice_id for n in notices(kind=OssNotice.Kind.CROSSED)] == [winner.pk]
        assert oss_mails(mailoutbox) == []
        assert [r for r in caplog.records if getattr(r, "event", "").startswith("billing.oss_")] == []


class TestNothingToTell:
    def test_a_voluntary_oss_registration_has_nothing_to_prepare(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        FiscalPolicy.objects.update(oss_registered=True)
        carried(this_year=7100)

        charge("in_1", commit=django_capture_on_commit_callbacks)

        assert notices() == []
        assert oss_mails(mailoutbox) == []

    def test_a_domestic_sale_never_counts(self, running, mailoutbox, django_capture_on_commit_callbacks):
        FiscalPolicy.objects.update(
            oss_threshold=Decimal("100.00"), oss_carried_year=YEAR, oss_carried_current_cents=9_000
        )

        charge("in_madrid", commit=django_capture_on_commit_callbacks)

        assert notices() == []

    def test_a_business_with_a_verified_eu_vat_number_never_counts(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks
    ):
        from billing.tests.vies_double import VALID, vies_says

        # The year is past 80 % already (no notice yet): a sale that does not count must not be the one that tells.
        payer(berlin, billing_postal_code="91710", tax_id="DE812871812")
        carried(this_year=8500)

        with vies_says(**VALID), django_capture_on_commit_callbacks(execute=True):
            deliver(paid("in_b2b", amount_due=2999, tax=0))

        assert Invoice.objects.get(stripe_invoice_id="in_b2b").payer_tax_id_verified is True

        assert notices() == []


class TestChargingNeverBreaks:
    def test_a_failure_noting_the_threshold_keeps_the_invoice_and_says_so(self, berlin, monkeypatch, caplog):
        from django.db import DatabaseError

        from billing import queries

        carried(this_year=5100)

        def broken(policy, year):
            raise DatabaseError("sum failed")

        # Pricing takes a failed sum as origin (``uses_destination_rate``); the notice must not break the charge.
        monkeypatch.setattr(queries, "cross_border_b2c_cents", broken)
        with caplog.at_level(logging.ERROR, logger="billing.services"):
            deliver(paid("in_1", lines=[invoice_line()]))

        assert Invoice.objects.filter(stripe_invoice_id="in_1", payment_status=Invoice.PaymentStatus.PAID).exists()
        assert any(getattr(r, "event", "") == "billing.oss_notice_failed" for r in caplog.records)

    def test_a_mail_that_could_not_leave_is_sent_by_the_daily_pass(
        self, berlin, mailoutbox, django_capture_on_commit_callbacks, monkeypatch, stripe_double
    ):
        carried(this_year=5100)
        stripe_double.answer("subscriptions.update", subscription())
        real = emails.EmailMessage.send

        def down(self, *args, **kwargs):
            raise OSError("smtp down")

        monkeypatch.setattr(emails.EmailMessage, "send", down)
        charge("in_near", commit=django_capture_on_commit_callbacks)
        assert notices()[0].mailed_at is None

        with pytest.raises(CommandError) as failure:
            call_command("retax_subscriptions")
        assert "notices_failed=1" in str(failure.value)

        monkeypatch.setattr(emails.EmailMessage, "send", real)
        call_command("retax_subscriptions")

        assert notices()[0].mailed_at is not None
        assert len(oss_mails(mailoutbox)) == 1


class TestTheAdmin:
    def test_the_notices_are_read_only(self, client, berlin, django_capture_on_commit_callbacks):
        from django.contrib.auth import get_user_model

        carried(this_year=5100)
        charge("in_near", commit=django_capture_on_commit_callbacks)
        client.force_login(get_user_model().objects.create_superuser(email="root@example.com", password="x"))
        notice = notices()[0]

        assert client.get("/admin/billing/ossnotice/").status_code == 200
        assert client.get(f"/admin/billing/ossnotice/{notice.pk}/change/").status_code == 200
        assert client.get("/admin/billing/ossnotice/add/").status_code == 403
        assert client.post(f"/admin/billing/ossnotice/{notice.pk}/delete/", {"post": "yes"}).status_code == 403


class TestTheMailAmounts:
    def test_the_amounts_are_exact_cents_never_a_float(self, berlin, mailoutbox, django_capture_on_commit_callbacks, settings):
        """Money is cents or ``Decimal``, never a float: a float of a large amount drifts by a cent."""
        carried(this_year=5100)
        sale = charge("in_near", commit=django_capture_on_commit_callbacks)
        notice = OssNotice.objects.create(
            year=YEAR + 1, kind=OssNotice.Kind.NEAR, invoice=sale, accumulated_cents=10**16 + 1, threshold_cents=10**16
        )

        emails.send_oss_notice(notice)

        body = mailoutbox[-1].body
        assert "100,000,000,000,000.01 €" in body
        assert "100,000,000,000,000.02" not in body
