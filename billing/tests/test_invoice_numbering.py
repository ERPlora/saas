"""The numbers of ERPlora's invoices: correlative per series and year, no gap, no duplicate (lot L3-C).

The counter is one row per series (``billing.InvoiceCounter``: the year and the last number), locked in the
transaction that records the invoice (CLAUDE.md, «Fiscal»: ``fiscal_counter``, never a Postgres sequence,
which leaves holes when a transaction rolls back). Its row lock serialises two invoices at once: the second
waits for the first to commit or roll back. The issue date is read AFTER the lock is held, so a later number
never carries an earlier date (review of L3-C), and a new year starts the series again at 1.

Rewritten from ERPlora/saas ``Invoice.generate_invoice_number`` (``YYYYMMDD-NNNN``, a ``select_for_update`` of
the day's last invoice) and ``test_invoice_environment`` (its own series per kind): the series are now
``ERP-<year>-<5 digits>`` for invoices and ``ERPR-<year>-<5 digits>`` for rectifying ones (their own series,
RD 1619/2012 art. 15.5). The AEAT test environment is the platform hub's, not a series.
"""

import threading
from datetime import date

import pytest
from django.db import connection, connections, transaction

from billing import services
from billing.models import Invoice, InvoiceCounter

pytestmark = pytest.mark.django_db


@pytest.fixture
def clock(monkeypatch):
    """The day the invoices are issued, set by the test."""
    today = {"value": date(2026, 10, 14)}
    monkeypatch.setattr(services, "invoice_today", lambda: today["value"])
    return today


def number(kind=Invoice.Kind.INVOICE):
    with transaction.atomic():
        return services.issue_number(kind)


class TestTheSeries:
    def test_the_first_invoice_of_a_year_is_number_one(self, clock):
        assert number() == ("ERP", 1, "ERP-2026-00001", date(2026, 10, 14))

    def test_the_next_one_follows(self, clock):
        number()

        assert number()[:3] == ("ERP", 2, "ERP-2026-00002")

    def test_a_new_year_starts_again(self, clock):
        clock["value"] = date(2026, 12, 31)
        number()
        clock["value"] = date(2027, 1, 1)

        assert number() == ("ERP", 1, "ERP-2027-00001", date(2027, 1, 1))

    def test_rectifying_invoices_have_their_own_series(self, clock):
        number()

        assert number(Invoice.Kind.CREDIT_NOTE)[:3] == ("ERPR", 1, "ERPR-2026-00001")
        assert number()[:3] == ("ERP", 2, "ERP-2026-00002")

    def test_the_counter_is_a_row_not_a_sequence(self, clock):
        number()

        counter = InvoiceCounter.objects.get(series="ERP")
        assert (counter.year, counter.last_number) == (2026, 1)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_class WHERE relkind = 'S' AND relname ILIKE %s",
                ["%invoice%"],
            )
            assert cursor.fetchone()[0] == 0


class TestNoGap:
    def test_a_number_given_in_a_transaction_that_rolls_back_is_given_again(
        self, clock
    ):
        with pytest.raises(RuntimeError), transaction.atomic():
            services.issue_number(Invoice.Kind.INVOICE)
            raise RuntimeError("the webhook failed after numbering")

        assert number()[:3] == ("ERP", 1, "ERP-2026-00001")


@pytest.mark.django_db(transaction=True)
def test_outside_a_transaction_no_number_is_given():
    """A number only exists with its invoice: given alone it would be a hole the day the invoice fails."""
    with pytest.raises(RuntimeError):
        services.issue_number(Invoice.Kind.INVOICE)

    assert not InvoiceCounter.objects.filter(last_number__gt=0).exists()


def _in_thread(target, results, name):
    def run():
        try:
            results[name] = target()
        except BaseException as error:  # noqa: BLE001 - reported to the test
            results[name] = error
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    return thread


@pytest.mark.django_db(transaction=True)
def test_the_second_waits_for_the_first_and_takes_the_number_it_gave_back(clock):
    """Positive control of the lock: while the first transaction holds its number the second one waits (it
    has not finished after a while); the first rolls back, and the second gets number 1, not 2."""
    numbered, release = threading.Event(), threading.Event()
    results: dict = {}

    def first():
        with transaction.atomic():
            taken = services.issue_number(Invoice.Kind.INVOICE)
            numbered.set()
            release.wait(timeout=10)
            transaction.set_rollback(True)
            return taken

    def second():
        numbered.wait(timeout=10)
        with transaction.atomic():
            return services.issue_number(Invoice.Kind.INVOICE)

    one = _in_thread(first, results, "first")
    two = _in_thread(second, results, "second")
    assert numbered.wait(timeout=10)
    two.join(timeout=0.5)

    assert two.is_alive(), "the second numbered while the first held the counter"
    release.set()
    one.join(timeout=10)
    two.join(timeout=10)
    assert results["first"][1] == 1
    assert results["second"][1] == 1


@pytest.mark.django_db(transaction=True)
def test_the_issue_date_is_read_once_the_lock_is_held(clock):
    """The second invoice waits across midnight of the 31st: it is the first of the new year, dated then, not
    the next of the old one dated before the first."""
    clock["value"] = date(2026, 12, 31)
    numbered, release = threading.Event(), threading.Event()
    results: dict = {}

    def first():
        with transaction.atomic():
            taken = services.issue_number(Invoice.Kind.INVOICE)
            numbered.set()
            release.wait(timeout=10)
            return taken

    def second():
        numbered.wait(timeout=10)
        with transaction.atomic():
            return services.issue_number(Invoice.Kind.INVOICE)

    one = _in_thread(first, results, "first")
    two = _in_thread(second, results, "second")
    assert numbered.wait(timeout=10)
    two.join(timeout=0.5)
    clock["value"] = date(2027, 1, 1)
    release.set()
    one.join(timeout=10)
    two.join(timeout=10)

    assert results["first"] == ("ERP", 1, "ERP-2026-00001", date(2026, 12, 31))
    assert results["second"] == ("ERP", 1, "ERP-2027-00001", date(2027, 1, 1))


@pytest.mark.django_db(transaction=True)
def test_two_invoices_at_once_take_consecutive_numbers(clock):
    start = threading.Barrier(2)
    results: dict = {}

    def issue():
        start.wait(timeout=5)
        with transaction.atomic():
            return services.issue_number(Invoice.Kind.INVOICE)[1]

    threads = [_in_thread(issue, results, name) for name in ("a", "b")]
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(results.values()) == [1, 2]
