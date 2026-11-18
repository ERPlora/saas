"""The number of ERPlora's invoices: each kind of document has its series, numbered without gaps inside the
transaction that records it."""

import uuid
from datetime import date

from django.db import connection
from django.utils import timezone

from billing.models import Invoice, InvoiceCounter


#: The series of each kind of document: a rectifying invoice has its own (RD 1619/2012, art. 15.5).
INVOICE_SERIES = {Invoice.Kind.INVOICE: "ERP", Invoice.Kind.CREDIT_NOTE: "ERPR"}


def invoice_today() -> date:
    """The issue date of an invoice numbered now (the tests set it)."""
    return timezone.localdate()


def issue_number(kind: str) -> tuple[str, int, str, date]:
    """The next number of ``kind``'s series and its issue date: ``(series, sequence, "ERP-2026-00123", date)``.

    ``fiscal_counter``: the series' row is locked in the transaction that records the
    invoice, and only then the date is read, so a number that waited for another one never carries an earlier
    date; a new year starts at 1. A second invoice waits for the first one's COMMIT, and a
    ROLLBACK gives the number back: no gap, no duplicate (a Postgres sequence would leave a hole). Refused
    outside a transaction: a number given alone is a hole the day its invoice fails.
    """
    if connection.get_autocommit():
        raise RuntimeError("An invoice number is only given inside the transaction that records its invoice")
    series = INVOICE_SERIES[kind]
    table = InvoiceCounter._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table} (id, series, year, last_number) VALUES (%s, %s, 0, 0) ON CONFLICT (series) DO NOTHING",
            [uuid.uuid7(), series],
        )
        cursor.execute(f"SELECT year, last_number FROM {table} WHERE series = %s FOR UPDATE", [series])
        year, last_number = cursor.fetchone()
        on = invoice_today()
        sequence = last_number + 1 if year == on.year else 1
        cursor.execute(
            f"UPDATE {table} SET year = %s, last_number = %s WHERE series = %s RETURNING last_number",
            [on.year, sequence, series],
        )
        sequence = cursor.fetchone()[0]
    return series, sequence, f"{series}-{on.year}-{sequence:05d}", on
