"""``manage.py reconcile_platform_invoices``: what the platform hub still owes, retried (``saas-cron``).

The post after the COMMIT is the fast path; this is the net (the same pattern as ``reconcile_hub_states``):
every «issuing» invoice whose wait passed is posted again (idempotent on the Hub by its id), every issued or
rejected one is asked until the AEAT accepts it, and one «issuing» for more than an hour is stuck. Under
the advisory lock ``hashtext('erplora.saas.reconcile_platform_invoices')``: a second run returns at once.
The run ends with an error (the ``task_failed`` alarm) when anything stayed owed, refused, rejected, stuck
or crashed; a pass with nothing to do is clean.
"""

import logging
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from billing.models import Invoice
from billing.services import platform_invoices

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

    def test_the_saas_worker_runs_the_same_pass_under_the_same_lock(self, hub_double, other_session):
        """``services.platform_invoices.reconcile_platform_invoices_exclusively`` is what the command and the
        ``saas-worker`` (every 15 minutes, saas#305) both run: the pass's counts, or ``None`` while another run holds
        the lock."""
        owed()
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})
        other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
        try:
            assert platform_invoices.reconcile_platform_invoices_exclusively() is None
        finally:
            other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
        assert hub_double.calls == []

        counts = platform_invoices.reconcile_platform_invoices_exclusively()

        assert counts is not None and not platform_invoices.platform_run_failed(counts)
        assert len(posts(hub_double)) == 1
        assert other_session.execute(f"SELECT pg_try_advisory_lock({LOCK_KEY})").fetchone()[0] is True
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

    def test_a_pass_the_worker_cuts_short_stops_after_the_invoice_in_course_and_leaves_the_rest_for_the_next(
        self, hub_double
    ):
        """The ``saas-worker`` gives the pass ``go_on`` (saas#305), asked before each invoice: a ``False`` ends it after
        the one in course, ``cut_short`` says the rest goes in the next round (not a failure), and the count of the
        ones stuck is still made."""
        for sequence in (1, 2, 3):
            owed(sequence)
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})
        asked: list[int] = []

        def go_on():
            asked.append(1)
            return len(asked) == 1

        counts = platform_invoices.reconcile_platform_invoices_exclusively(go_on=go_on)

        assert (counts["accepted"] + counts["posted"], counts["cut_short"], counts["stuck"]) == (1, 1, 0)
        assert not platform_invoices.platform_run_failed(counts)
        assert len(posts(hub_double)) == 1
        again = platform_invoices.reconcile_platform_invoices_exclusively()
        assert again["cut_short"] == 0 and len(posts(hub_double)) == 3

    def test_the_lock_is_released_after_a_run(self, hub_double, other_session):
        run()

        taken = other_session.execute(
            f"SELECT pg_try_advisory_lock({LOCK_KEY})"
        ).fetchone()[0]
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")
        assert taken is True


class TestTheMailOfAnIssuedInvoice:
    """The payer's mail that failed when the invoice was issued is sent again by the run, until
    it leaves; one with nobody to send it to is done (nothing to retry)."""

    def test_a_mail_that_failed_is_sent_again(self, hub_double):
        from django.core import mail

        invoice = owed(fiscal_status="accepted", qr=QR, payer_email="pagos@example.com")
        hub_double.answer("GET", r"/pdf$", 200, {"pdf": "the platform hub's"})

        output = run()

        assert "mailed=1" in output
        assert [message.to for message in mail.outbox] == [["pagos@example.com"]]
        invoice.refresh_from_db()
        assert invoice.emailed_at is not None

    @pytest.mark.parametrize("status", [503, 404])
    def test_a_mail_whose_pdf_the_hub_does_not_hand_over_waits_for_it(self, hub_double, status):
        """Never a mail without its invoice: it stays owed, the run says so, and the next one sends it."""
        from django.core import mail

        owed(fiscal_status="accepted", qr=QR, payer_email="pagos@example.com")
        hub_double.answer("GET", r"/pdf$", status, {"error": {"code": "not_found", "message": "No PDF yet."}})

        with pytest.raises(CommandError, match="mail_failed=1"):
            run()
        assert mail.outbox == []
        assert Invoice.objects.get().emailed_at is None

        hub_double.answer("GET", r"/pdf$", 200, {"pdf": "the platform hub's"})
        assert "mailed=1" in run()
        assert len(mail.outbox) == 1

    def test_one_mailed_already_is_not_sent_again(self, hub_double):
        from django.core import mail

        owed(fiscal_status="accepted", qr=QR, payer_email="pagos@example.com", emailed_at=timezone.now())

        run()

        assert mail.outbox == []

    def test_a_mail_that_still_cannot_leave_fails_the_run(self, hub_double, monkeypatch):
        owed(fiscal_status="accepted", qr=QR, payer_email="pagos@example.com")
        hub_double.answer("GET", r"/pdf$", 200, {"pdf": "the platform hub's"})
        monkeypatch.setattr("django.core.mail.EmailMessage.send", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))

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


def said(caplog):
    return [record.getMessage() for record in caplog.records if record.name == "billing.services"]


def going_on(times):
    """The worker's ``go_on``: yes to the first ``times`` questions."""
    answers = iter([True] * times)
    return lambda: next(answers, False)


class TestWhatItPosts:
    def test_they_are_posted_by_series_day_and_number(self, hub_double):
        today = timezone.localdate()
        for sequence, series, day in ((1, "ERPR", today), (3, "ERP", today), (2, "ERP", today), (4, "ERP", today - timedelta(days=1))):
            Invoice.objects.filter(pk=owed(sequence).pk).update(series=series, issued_on=day)
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})

        run()

        assert [call.body["number"] for call in posts(hub_double)] == [
            "ERP-2026-00004",
            "ERP-2026-00002",
            "ERP-2026-00003",
            "ERP-2026-00001",
        ]

    def test_one_is_due_at_the_very_moment_its_wait_ends(self, hub_double):
        at = timezone.now() + timedelta(hours=3)
        owed(1, next_post_at=at)
        owed(2, next_post_at=at + timedelta(microseconds=1))
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})

        counts = platform_invoices.reconcile_platform_invoices(now=at)

        assert counts["posted"] == 1
        assert [call.body["number"] for call in posts(hub_double)] == ["ERP-2026-00001"]

    @pytest.mark.parametrize("fiscal_status", ["issuing", "issued", "rejected", "accepted"])
    def test_an_invoice_not_collected_is_left_alone_whatever_its_fiscal_status(self, hub_double, mailoutbox, fiscal_status):
        Invoice.objects.create(
            stripe_invoice_id="in_open",
            payment_status="open",
            net_cents=1,
            total_cents=1,
            fiscal_status=fiscal_status,
            fiscal_status_at=timezone.now() - timedelta(hours=2),
            payer_email="pagos@example.com",
        )

        output = run()

        assert "stuck=0" in output
        assert hub_double.calls == []
        assert mailoutbox == []

    def test_one_whose_post_crashes_is_an_error_and_the_next_one_is_posted(self, hub_double, monkeypatch, caplog):
        crashing = owed(1)
        owed(2)
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})
        post = platform_invoices.hub_client.post_platform_invoice

        def crash(payload):
            if payload["id"] == str(crashing.id):
                raise RuntimeError("broken")
            return post(payload)

        monkeypatch.setattr(platform_invoices.hub_client, "post_platform_invoice", crash)

        with caplog.at_level(logging.ERROR, logger="billing.services"), pytest.raises(CommandError, match="errors=1"):
            run()

        assert [call.body["number"] for call in posts(hub_double)] == ["ERP-2026-00002"]
        assert said(caplog) == [f"[INVOICE] Posting invoice {crashing.id} crashed"]
        assert caplog.records[0].exc_info

    def test_one_whose_post_crashed_is_not_counted_as_posted(self, hub_double, monkeypatch):
        owed()

        def crash(payload):
            raise RuntimeError("broken")

        monkeypatch.setattr(platform_invoices.hub_client, "post_platform_invoice", crash)

        counts = platform_invoices.reconcile_platform_invoices()

        assert (counts["posted"], counts["errors"], set(counts)) == (0, 1, set(platform_invoices.PLATFORM_COUNTS))

    def test_one_that_is_gone_meanwhile_is_not_counted(self, hub_double, monkeypatch):
        owed(1)
        gone = owed(2)
        hub_double.answer("POST", PLATFORM, 200, {"status": "accepted", "qr": QR})
        post = platform_invoices.hub_client.post_platform_invoice

        def gone_meanwhile(payload):
            Invoice.objects.filter(pk=gone.pk).update(payment_status="void", number="")
            return post(payload)

        monkeypatch.setattr(platform_invoices.hub_client, "post_platform_invoice", gone_meanwhile)

        counts = platform_invoices.reconcile_platform_invoices()

        assert (counts["posted"], set(counts)) == (1, set(platform_invoices.PLATFORM_COUNTS))


class TestWhatItAsks:
    def asked(self, hub_double):
        return [call.path for call in hub_double.calls_to("GET")]

    def test_one_the_aeat_has_not_answered_yet_waits(self, hub_double):
        owed(fiscal_status="issued", qr=QR, emailed_at=timezone.now())
        hub_double.answer("GET", r"^/internal/platform/invoices/", 200, {"status": "issued", "qr": QR})

        output = run()

        assert "accepted=0 waiting=1" in output

    @pytest.mark.parametrize("status, outcome", [(503, "unreachable=1 refused=0"), (404, "unreachable=0 refused=1")])
    def test_one_the_hub_does_not_answer_for_fails_the_run(self, hub_double, status, outcome):
        owed(fiscal_status="issued", qr=QR, emailed_at=timezone.now())
        hub_double.answer("GET", r"^/internal/platform/invoices/", status, {"error": {"code": "not_found", "message": "No."}})

        with pytest.raises(CommandError, match=f"accepted=0 waiting=0 mailed=0 {outcome}"):
            run()

    def test_one_whose_question_crashes_is_an_error_and_the_next_one_is_asked(self, hub_double, monkeypatch, caplog):
        crashing = owed(1, fiscal_status="issued", qr=QR, emailed_at=timezone.now())
        owed(2, fiscal_status="issued", qr=QR, emailed_at=timezone.now())
        hub_double.answer("GET", r"^/internal/platform/invoices/", 200, {"status": "accepted", "qr": QR})
        ask = platform_invoices.hub_client.get_platform_invoice

        def crash(invoice_id):
            if invoice_id == str(crashing.id):
                raise RuntimeError("broken")
            return ask(invoice_id)

        monkeypatch.setattr(platform_invoices.hub_client, "get_platform_invoice", crash)

        with caplog.at_level(logging.ERROR, logger="billing.services"):
            counts = platform_invoices.reconcile_platform_invoices()

        assert (counts["accepted"], counts["waiting"], counts["errors"]) == (1, 0, 1)
        assert said(caplog) == [f"[INVOICE] Asking about invoice {crashing.id} crashed"]
        assert caplog.records[0].exc_info

    def test_one_issued_long_ago_is_not_stuck(self, hub_double):
        owed(fiscal_status="issued", qr=QR, emailed_at=timezone.now(), since=timezone.now() - timedelta(hours=2))
        hub_double.answer("GET", r"^/internal/platform/invoices/", 200, {"status": "issued", "qr": QR})

        assert "stuck=0" in run()

    def test_one_is_stuck_at_the_very_hour(self, hub_double):
        at = timezone.now() + timedelta(hours=3)
        for sequence, since in ((1, at - timedelta(hours=1)), (2, at - timedelta(minutes=59))):
            owed(sequence, since=since, next_post_at=at + timedelta(minutes=1))

        assert platform_invoices.reconcile_platform_invoices(now=at)["stuck"] == 1


class TestWhatItMails:
    def test_one_still_issuing_has_nothing_to_mail(self, hub_double, mailoutbox):
        owed(payer_email="pagos@example.com")
        hub_double.answer("POST", PLATFORM, 503, {})

        with pytest.raises(CommandError, match="mailed=0 unreachable=1"):
            run()

        assert mailoutbox == []
        assert Invoice.objects.get().emailed_at is None

    def test_one_with_nobody_to_send_it_to_is_not_counted_as_mailed(self, hub_double):
        owed(fiscal_status="accepted", qr=QR)

        output = run()

        assert "mailed=0" in output and "mail_failed=0" in output


class TestAPassCutShort:
    """The worker stops it between two invoices, whatever it was doing with them: the rest is for the next pass."""

    def test_while_asking_it_asks_no_more_and_mails_nothing(self, hub_double, mailoutbox):
        for sequence in (1, 2):
            owed(sequence, fiscal_status="issued", qr=QR, payer_email="pagos@example.com")
        hub_double.answer("GET", r"^/internal/platform/invoices/[^/]+$", 200, {"status": "issued", "qr": QR})

        counts = platform_invoices.reconcile_platform_invoices(go_on=going_on(1))

        assert (counts["waiting"], counts["cut_short"]) == (1, 1)
        assert len(hub_double.calls_to("GET")) == 1
        assert mailoutbox == []

    def test_while_mailing_it_mails_no_more(self, hub_double, mailoutbox):
        for sequence in (1, 2):
            owed(sequence, fiscal_status="accepted", qr=QR, payer_email="pagos@example.com")
        hub_double.answer("GET", r"/pdf$", 200, {"pdf": "the platform hub's"})

        counts = platform_invoices.reconcile_platform_invoices(go_on=going_on(1))

        assert (counts["mailed"], counts["cut_short"], len(mailoutbox)) == (1, 1, 1)

    def test_the_stuck_ones_are_counted_all_the_same(self, hub_double):
        owed(since=timezone.now() - timedelta(hours=2))

        counts = platform_invoices.reconcile_platform_invoices(go_on=going_on(0))

        assert (counts["stuck"], counts["cut_short"]) == (1, 1)
        assert hub_double.calls == []

    def test_once_told_to_stop_it_does_not_ask_again(self, hub_double):
        owed(1)
        owed(2, fiscal_status="issued", qr=QR)
        owed(3, fiscal_status="accepted", qr=QR)
        questions = []

        def stop():
            questions.append(1)
            return False

        platform_invoices.reconcile_platform_invoices(go_on=stop)

        assert len(questions) == 1
