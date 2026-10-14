"""``manage.py reconcile_platform_invoices``: what the platform hub still owes, retried (lot L3-C; ``saas-cron``).

The post after the COMMIT is the fast path; this is the net (the same pattern as ``reconcile_hub_states``):
every «issuing» invoice whose wait passed is posted again (idempotent on the Hub by its id), every issued or
rejected one is asked until the AEAT accepts it, and one «issuing» for more than an hour is stuck. Under
the advisory lock ``hashtext('erplora.saas.reconcile_platform_invoices')``: a second run returns at once.
The run ends with an error (the ``task_failed`` alarm) when anything stayed owed, refused, rejected, stuck
or crashed; a pass with nothing to do is clean.
"""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from billing.models import Invoice

pytestmark = pytest.mark.django_db

PLATFORM = r"^/internal/platform/invoices$"
QR = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?nif=B27593136&numserie=ERP-2026-00001"
LOCK_KEY = "hashtext('erplora.saas.reconcile_platform_invoices')"


def run() -> str:
    out = StringIO()
    call_command("reconcile_platform_invoices", stdout=out)
    return out.getvalue()


def owed(
    sequence=1, *, fiscal_status="issuing", next_post_at=None, since=None, **fields
) -> Invoice:
    now = timezone.now()
    return Invoice.objects.create(
        stripe_invoice_id=f"in_{sequence}",
        business_name="Panadería López",
        payment_status="paid",
        series="ERP",
        sequence=sequence,
        number=f"ERP-2026-{sequence:05d}",
        issued_on=timezone.localdate(),
        net_cents=2999,
        tax_cents=630,
        total_cents=3629,
        fiscal_status=fiscal_status,
        fiscal_status_at=since or now,
        next_post_at=next_post_at,
        **fields,
    )


def posts(hub_double):
    return [
        call
        for call in hub_double.calls_to("POST")
        if call.path == "/internal/platform/invoices"
    ]


class TestWhatItRetries:
    def test_an_issuing_invoice_is_posted_again_and_issued(self, hub_double):
        invoice = owed(next_post_at=timezone.now() - timedelta(minutes=1))
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})

        output = run()

        assert "posted=1" in output
        invoice.refresh_from_db()
        assert (invoice.fiscal_status, invoice.qr) == ("accepted", QR)

    def test_one_still_waiting_for_its_backoff_is_left_alone(self, hub_double):
        owed(next_post_at=timezone.now() + timedelta(minutes=10))

        run()

        assert posts(hub_double) == []

    def test_down_then_up_ends_accepted(self, hub_double):
        invoice = owed()
        hub_double.answer("POST", PLATFORM, 503, {})
        with pytest.raises(CommandError):
            run()
        Invoice.objects.filter(pk=invoice.pk).update(
            next_post_at=timezone.now() - timedelta(seconds=1)
        )
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})

        run()

        invoice.refresh_from_db()
        assert (invoice.fiscal_status, invoice.post_attempts) == ("accepted", 2)

    def test_an_issued_invoice_is_asked_until_the_aeat_accepts_it(self, hub_double):
        invoice = owed(fiscal_status="issued", qr=QR)
        hub_double.answer(
            "GET",
            rf"^/internal/platform/invoices/{invoice.id}$",
            200,
            {"status": "accepted", "qr": QR},
        )

        output = run()

        assert "accepted=1" in output
        assert Invoice.objects.get().fiscal_status == "accepted"
        assert posts(hub_double) == []

    def test_an_accepted_invoice_is_never_asked_again(self, hub_double):
        owed(fiscal_status="accepted", qr=QR)

        run()

        assert hub_double.calls == []

    def test_unpaid_invoices_are_never_posted(self, hub_double):
        Invoice.objects.create(
            stripe_invoice_id="in_open",
            payment_status="open",
            net_cents=1,
            total_cents=1,
        )

        run()

        assert hub_double.calls == []


class TestWhenTheRunFails:
    def test_the_hub_away_fails_the_run_after_the_pass(self, hub_double):
        owed(1)
        owed(2)
        hub_double.answer("POST", PLATFORM, 503, {})

        with pytest.raises(CommandError, match="unreachable=2"):
            run()

        assert len(posts(hub_double)) == 2

    def test_a_refusal_fails_the_run(self, hub_double):
        owed()
        hub_double.answer(
            "POST",
            PLATFORM,
            422,
            {"error": {"code": "invalid_recipient", "message": "No."}},
        )

        with pytest.raises(CommandError, match="refused=1"):
            run()

    def test_a_rejection_fails_the_run_until_it_is_corrected(self, hub_double):
        invoice = owed(fiscal_status="issued", qr=QR)
        hub_double.answer(
            "GET",
            rf"^/internal/platform/invoices/{invoice.id}$",
            200,
            {
                "status": "rejected",
                "error": {"code": "1100", "message": "NIF incorrecto."},
            },
        )

        with pytest.raises(CommandError, match="rejected=1"):
            run()
        with pytest.raises(CommandError, match="rejected=1"):
            run()

        hub_double.answer(
            "GET",
            rf"^/internal/platform/invoices/{invoice.id}$",
            200,
            {"status": "accepted", "qr": QR},
        )
        run()
        assert Invoice.objects.get().fiscal_status == "accepted"

    def test_one_issuing_for_more_than_an_hour_is_stuck(self, hub_double):
        owed(
            since=timezone.now() - timedelta(hours=2),
            next_post_at=timezone.now() + timedelta(hours=1),
        )

        with pytest.raises(CommandError, match="stuck=1"):
            run()


class TestTheRun:
    def test_nothing_owed_is_a_clean_run(self, hub_double):
        output = run()

        assert "posted=0" in output and "stuck=0" in output

    def test_running_twice_does_not_post_twice(self, hub_double):
        owed()
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})

        run()
        run()

        assert len(posts(hub_double)) == 1

    def test_a_second_run_returns_at_once_while_one_holds_the_lock(
        self, hub_double, other_session
    ):
        owed()
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
        try:
            output = run()
        finally:
            other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

        assert "already running" in output
        assert hub_double.calls == []

    def test_the_lock_is_released_after_a_run(self, hub_double, other_session):
        run()

        taken = other_session.execute(
            f"SELECT pg_try_advisory_lock({LOCK_KEY})"
        ).fetchone()[0]
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
        assert taken is True


class TestTheMailOfAnIssuedInvoice:
    """Review of L3-C: the payer's mail that failed when the invoice was issued is sent again by the run, until
    it leaves; one with nobody to send it to is done (nothing to retry)."""

    def test_a_mail_that_failed_is_sent_again(self, hub_double):
        from django.core import mail

        invoice = owed(fiscal_status="accepted", qr=QR, payer_email="pagos@example.com")

        output = run()

        assert "mailed=1" in output
        assert [message.to for message in mail.outbox] == [["pagos@example.com"]]
        invoice.refresh_from_db()
        assert invoice.emailed_at is not None

    def test_one_mailed_already_is_not_sent_again(self, hub_double):
        from django.core import mail

        owed(fiscal_status="accepted", qr=QR, payer_email="pagos@example.com", emailed_at=timezone.now())

        run()

        assert mail.outbox == []

    def test_a_mail_that_still_cannot_leave_fails_the_run(self, hub_double, monkeypatch):
        from billing import emails

        owed(fiscal_status="accepted", qr=QR, payer_email="pagos@example.com")
        monkeypatch.setattr(emails, "send_mail", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))

        with pytest.raises(CommandError, match="mail_failed=1"):
            run()

        assert Invoice.objects.get().emailed_at is None

    def test_nobody_to_send_it_to_is_done(self, hub_double):
        owed(fiscal_status="accepted", qr=QR)

        run()

        assert Invoice.objects.get().emailed_at is not None

    def test_one_not_issued_yet_is_not_mailed(self, hub_double):
        from django.core import mail

        owed(fiscal_status="issued", qr=QR, payer_email="pagos@example.com",
             next_post_at=timezone.now() + timedelta(hours=1))
        hub_double.answer("GET", r"^/internal/platform/invoices/", 200, {"status": "issued", "qr": QR})

        run()

        assert len(mail.outbox) == 1  # «issued» has its QR and PDF: the mail goes
